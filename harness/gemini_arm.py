#!/usr/bin/env python3
"""
Gemini-Flash arm runner — the SECOND MODEL FAMILY executor for E1.

The Claude arms ran as Claude Code sub-agents; Gemini cannot, so this is a
manual tool-use loop over `gemini-2.5-flash`. EVERYTHING else is reused and
frozen (prereg-v1): the arm prompts, the inlined prose framework, the trap
suite, reference.py, and the extract_tp4 classifier are model-agnostic — only
the executor changes. That is deliberate: swapping the model while holding the
instrument fixed is the whole point of a second-family replication.

CLAUDE.md #1 is the load-bearing invariant here: the `raw_query` we log is the
EXACT string Gemini emitted and we executed — never reconstructed from its
prose. The gap between what it says and what it ran is the finding; if we let
narration stand in for execution we have measured nothing. So a directive the
model emits but that we could not parse/execute is logged as an UNPARSED marker,
never quietly turned into a plausible query.

Output: runs/gem_<arm>_<seed>.jsonl in the SAME trace schema the classifier
reads: {"turn","kind":"tool_call","tool","raw_query", ...},
{"kind":"text","content"}, {"kind":"final_ranking","entities":[...]}.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness import gateway  # noqa: E402  (frozen read path; org header, no JWT)
from harness.reference import oracle_ranking, MODEL_ID, DISEASE  # noqa: E402

MODEL = "gemini-2.5-flash"
ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
            f"{MODEL}:generateContent")
FRAMEWORK_MD = (ROOT / "frameworks" / "target_prioritization.md").read_text()
SPEC_JSON = (ROOT / "frameworks" / "executable_model_spec.json").read_text()
REPORT_ID = os.environ.get("SOD_REPORT_ID", "")       # the module's computed-scores report

# Per-arm access. Mirrors the Claude arms' PROMPT-level data access exactly.
#   A1 = none (prose + priors only), A2 = raw Cypher, A3 = Cypher + platform
#   tools, A4 = retrieve the executable module's precomputed ranking.
ARM_ACCESS = {
    "A1": {"cypher": False, "tools": []},
    "A2": {"cypher": True, "tools": []},
    "A3": {"cypher": True, "tools": ["graph_schema", "entity_search",
                                     "graph_query"]},
    "A4": {"cypher": True, "tools": ["list_models",
                                     "get_model", "enumerate_reports",
                                     "get_scores", "entity_rank"]},
}

MAX_TOOL_CALLS = 80          # backstop only. Reasoning models (v4-pro) emit large
                             # query batches per turn and are thorough; 45 cut off
                             # A2 mid-gather before it could RANK. Raise the cap;
                             # it is a runaway-guard, not a measurement parameter.
MAX_TURNS = 60
RESULT_CAP = 12000           # chars of tool output fed back per call (envelope)


# --------------------------------------------------------------------------
# Gemini transport — stdlib urllib only (no new dependency; CLAUDE.md style).
# Free-tier flash is rate-limited (~10 RPM); back off on 429 and pace calls so a
# 12-session matrix does not die halfway and get silently dropped.
# --------------------------------------------------------------------------
def _load_key(name: str) -> str:
    envp = ROOT / ".env.local"
    if envp.exists():
        for line in envp.read_text().splitlines():
            line = line.strip()
            if line.startswith(name):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    k = os.environ.get(name)
    if not k:
        raise SystemExit(f"no {name} in .env.local or env")
    return k


# Provider is chosen at runtime (--provider). Keys loaded lazily so a Gemini run
# does not require a DeepSeek key present, and vice-versa.
PROVIDER = "gemini"
_KEYS: Dict[str, str] = {}


def _key(name: str) -> str:
    if name not in _KEYS:
        _KEYS[name] = _load_key(name)
    return _KEYS[name]


_LAST_CALL = [0.0]
MIN_GAP = 5.0                # seconds between calls -> <=12 RPM, safe for flash
DEEPSEEK_MAX_TOKENS = 48000  # total output budget incl. reasoning trace (v4-pro)


def call_model(system: str, history: List[Dict[str, Any]], seed: int,
               temperature: float = 0.7) -> str:
    """Provider-agnostic single call. history is [{"role":"user"|"model","text":..}].
    The loop, parser, tools and logging are all provider-agnostic; only the
    transport differs — which is the whole point of a second/third family: hold
    the instrument fixed, swap the model."""
    if PROVIDER == "deepseek":
        return deepseek(system, history, seed, temperature)
    return gemini(system, history, seed, temperature)


def deepseek(system: str, history: List[Dict[str, Any]], seed: int,
             temperature: float = 0.7) -> str:
    """One DeepSeek chat-completions call (OpenAI-compatible). role map:
    model->assistant; system prepended as a system message."""
    messages = [{"role": "system", "content": system}]
    for h in history:
        messages.append({"role": "assistant" if h["role"] == "model" else "user",
                         "content": h["text"]})
    # DeepSeek's max_tokens is the TOTAL output budget INCLUDING the reasoning
    # trace. A reasoning model (v4-pro) can spend 8k+ tokens thinking before it
    # writes a single visible token, so a small cap returns finish_reason=length
    # with EMPTY content (this silently killed A1, whose one-shot task reasons the
    # most). Give reasoning + answer room.
    body = {"model": MODEL, "messages": messages, "temperature": temperature,
            "max_tokens": DEEPSEEK_MAX_TOKENS, "seed": seed}
    data = json.dumps(body).encode()
    url = "https://api.deepseek.com/chat/completions"
    backoff = 8.0
    for attempt in range(6):
        gap = MIN_GAP - (time.time() - _LAST_CALL[0])
        if gap > 0:
            time.sleep(gap)
        req = urllib.request.Request(
            url, data=data,
            headers={"content-type": "application/json",
                     "authorization": f"Bearer {_key('DEEPSEEK_API_KEY')}"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                _LAST_CALL[0] = time.time()
                payload = json.loads(r.read().decode())
            ch = payload.get("choices", [])
            if not ch:
                return f"[[NO_CHOICE {json.dumps(payload)[:200]}]]"
            return (ch[0].get("message", {}).get("content", "") or "").strip()
        except urllib.error.HTTPError as e:
            _LAST_CALL[0] = time.time()
            code = e.code
            detail = e.read().decode()[:300]
            if code in (429, 500, 503):
                print(f"    [deepseek {code}] backoff {backoff:.0f}s "
                      f"(attempt {attempt+1}/6)", flush=True)
                time.sleep(backoff)
                backoff = min(backoff * 2, 120)
                continue
            raise RuntimeError(f"deepseek HTTP {code}: {detail}")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            print(f"    [deepseek net err] {e}; retry in {backoff:.0f}s", flush=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 120)
    raise RuntimeError("deepseek: exhausted retries")


def gemini(system: str, history: List[Dict[str, Any]], seed: int,
           temperature: float = 0.7) -> str:
    """One generateContent call. history is a list of {"role","text"}."""
    contents = [{"role": h["role"], "parts": [{"text": h["text"]}]}
                for h in history]
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 8192,
            "seed": seed,
        },
    }
    data = json.dumps(body).encode()
    # Build the endpoint from the (possibly overridden) MODEL each call, so
    # --model gemini-2.5-pro just works without editing the module.
    endpoint = ("https://generativelanguage.googleapis.com/v1beta/models/"
                f"{MODEL}:generateContent")
    url = f"{endpoint}?key={_key('GEMINI_API_KEY')}"
    backoff = 12.0
    for attempt in range(6):
        gap = MIN_GAP - (time.time() - _LAST_CALL[0])
        if gap > 0:
            time.sleep(gap)
        req = urllib.request.Request(url, data=data,
                                     headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                _LAST_CALL[0] = time.time()
                payload = json.loads(r.read().decode())
            return _extract_text(payload)
        except urllib.error.HTTPError as e:
            _LAST_CALL[0] = time.time()
            code = e.code
            detail = e.read().decode()[:300]
            if code in (429, 500, 503):
                # honour server retry hint if present, else exp backoff
                wait = backoff
                m = re.search(r'"retryDelay":\s*"(\d+)s"', detail)
                if m:
                    wait = max(wait, float(m.group(1)) + 1)
                print(f"    [gemini {code}] backoff {wait:.0f}s "
                      f"(attempt {attempt+1}/6)", flush=True)
                time.sleep(wait)
                backoff = min(backoff * 2, 120)
                continue
            raise RuntimeError(f"gemini HTTP {code}: {detail}")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            print(f"    [gemini net err] {e}; retry in {backoff:.0f}s", flush=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 120)
    raise RuntimeError("gemini: exhausted retries")


def _extract_text(payload: Dict[str, Any]) -> str:
    cands = payload.get("candidates", [])
    if not cands:
        # safety block / empty — surface it, don't pretend it answered
        return f"[[NO_CANDIDATE {json.dumps(payload)[:200]}]]"
    parts = cands[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts if "text" in p).strip()


# --------------------------------------------------------------------------
# Tool layer — gateway-backed, no MCP/JWT. Each tool returns exactly what the
# platform MCP tool of that name would return (schema, live rows, or the
# module's PRECOMPUTED ranking), so an A4 arm that retrieves get_scores
# is genuinely retrieving the executable model's output, not re-deriving it.
# --------------------------------------------------------------------------
# Directional patterns for the domain subgraph a real graph_schema exposes.
# These rel types are ALL already named (in backticks) in the frozen A2 prompt;
# the tool only adds their DIRECTION, which a schema-visualization tool
# legitimately returns and which a competent agent would otherwise discover with
# one probe query. Giving A3 (which has this tool) the directions — while A2 (raw
# Cypher, no tools) does not — is what lets us test whether tool access rescues a
# weaker model, rather than confounding "prose arm" with "couldn't guess an edge
# direction". Sampled once and cached.
_SCHEMA_RELS = [
    "differentially expresses", "analyzes celltype", "studies condition",
    "studies disease", "acts on", "using the drug", "has association",
    "risk of trait", "of trait", "participates in", "occurs when decreasing",
    "occurs when increasing", "upregulates", "downregulates", "HAS_SCORE_EDGE",
]
_SCHEMA_CACHE: Dict[str, Any] = {}


def tool_graph_schema(_args: Dict) -> Any:
    if _SCHEMA_CACHE:
        return _SCHEMA_CACHE
    labels = gateway.execute_query("CALL db.labels() YIELD label RETURN label")
    rels = gateway.execute_query(
        "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")
    generic = {"Object", "Resource", "Entity", "Thing", "NamedThing"}

    def _spec(labels_list):
        specific = [l for l in (labels_list or []) if l not in generic]
        return specific[0] if specific else (labels_list[0] if labels_list else "?")

    patterns = []
    for rt in _SCHEMA_RELS:
        try:
            row = gateway.execute_query(
                f"MATCH (a)-[:`{rt}`]->(b) RETURN labels(a) AS f, "
                f"labels(b) AS t LIMIT 1")
            if row:
                patterns.append(
                    f"(:{_spec(row[0]['f'])})-[:`{rt}`]->(:{_spec(row[0]['t'])})")
        except Exception:
            pass
    _SCHEMA_CACHE.update({
        "nodeLabels": [r["label"] for r in labels],
        "relationshipTypes": [r["relationshipType"] for r in rels],
        "domainRelationshipPatterns": patterns,
    })
    return _SCHEMA_CACHE


def tool_entity_search(args: Dict) -> Any:
    query = str(args.get("query", "")).replace("'", "")
    label = str(args.get("label", "")).replace("`", "")
    lab = f":`{label}`" if label else ""
    cy = (f"MATCH (n{lab}) WHERE toLower(coalesce(n.displayName,n.symbol,'')) "
          f"CONTAINS toLower('{query}') "
          f"RETURN labels(n) AS labels, coalesce(n.displayName,n.symbol) AS name "
          f"LIMIT 20")
    return gateway.execute_query(cy)


def tool_graph_query(args: Dict) -> Any:
    cy = args.get("query") or args.get("cypher") or ""
    if not cy:
        return {"error": "no query provided"}
    return gateway.execute_query(cy)


def tool_get_model(_args: Dict) -> Any:
    # The module's own spec — what get_model returns. This is the
    # executable framework; A4 reports the criteria/weights IT specifies.
    return json.loads(SPEC_JSON)


def _computed_ranking(top: int = 40) -> List[Dict]:
    return oracle_ranking(top)


def tool_list_models(_args: Dict) -> Any:
    return [{"id": MODEL_ID, "name": "DISEASE_OF_INTEREST Target Prioritization 4",
             "returnsEntityType": "Disease", "anchorConcept": "Gene"}]


def tool_enumerate_reports(_args: Dict) -> Any:
    return [{"reportId": REPORT_ID, "moduleId": MODEL_ID,
             "disease": DISEASE, "status": "Succeeded"}]


def tool_get_scores(args: Dict) -> Any:
    top = int(args.get("top", args.get("limit", 40)) or 40)
    return {"reportId": args.get("reportId", REPORT_ID), "moduleId": MODEL_ID,
            "disease": DISEASE, "scores": _computed_ranking(min(top, 60))}


def tool_entity_rank(args: Dict) -> Any:
    sym = str(args.get("entity", args.get("symbol", "")))
    full = oracle_ranking(12000)
    for e in full:
        if e["gene"] == sym:
            return {"entity": sym, "rank": e["rank"], "score": e["score"],
                    "outOf": len(full)}
    return {"entity": sym, "rank": None, "note": "not in computed universe"}


TOOLS = {
    "graph_schema": tool_graph_schema,
    "entity_search": tool_entity_search,
    "graph_query": tool_graph_query,
    "list_models": tool_list_models,
    "get_model": tool_get_model,
    "enumerate_reports": tool_enumerate_reports,
    "get_scores": tool_get_scores,
    "entity_rank": tool_entity_rank,
}


# --------------------------------------------------------------------------
# Directive parsing. The model replies with directive lines; we scan for the
# markers, in order of appearance, and act. RANK is terminal.
# --------------------------------------------------------------------------
# The colon is OPTIONAL and matching is case-insensitive: Flash frequently copies
# the frozen prompt's shell-style examples (`tool <name> '<json>'`, `cypher
# "<CYPHER>"`) instead of the `TOOL:`/`CYPHER:` protocol, dropping the colon. A
# strict `KEYWORD:` regex silently reclassified those as narration and killed the
# session (A3 seed 1). `\b` after the keyword prevents matching `Ranking`/`Tools`
# in prose; requiring the keyword to open the line keeps false positives rare.
MARKERS = ("CYPHER:", "TOOL:", "SAY:", "RANK:")
_MARK_RE = re.compile(r"^(?:`{3,}\w*\s*)?(CYPHER|TOOL|SAY|RANK)\b[ \t]*:?[ \t]*",
                      re.M | re.I)


def parse_directives(text: str) -> List[Tuple[str, str]]:
    """Return [(KIND, payload)] in order. Payload = text from after the marker
    (keyword + optional colon/space consumed) up to the next marker or EOF, code
    fences stripped. CYPHER/TOOL payloads are reduced to a SINGLE line and
    scrubbed of echoed result rows — Flash routinely appends a hallucinated
    `[{...}]` result array or an explanation after its query, and letting that
    into the executed string both breaks the query and (worse) blurs execution
    with narration, the one thing CLAUDE.md #1 forbids."""
    hits = [(m.group(1).upper(), m.start(1), m.end()) for m in _MARK_RE.finditer(text)]
    out: List[Tuple[str, str]] = []
    for i, (kind, start, payload_start) in enumerate(hits):
        end = hits[i + 1][1] if i + 1 < len(hits) else len(text)
        payload = text[payload_start:end]
        payload = re.sub(r"`{3,}\w*", "", payload).strip()
        if kind in ("CYPHER", "TOOL"):
            payload = _first_command_line(payload)
        out.append((kind, payload))
    return out


def _first_command_line(payload: str) -> str:
    """The command is one line; drop everything after it, and cut any echoed
    result array (`[{`, `[ {`) the model pasted onto the same line."""
    line = ""
    for ln in payload.splitlines():
        if ln.strip():
            line = ln.strip()
            break
    line = re.split(r"\[\s*\{", line)[0].strip()      # kill a pasted result array
    line = re.split(r"\s*(?://|--)\s", line)[0].strip()  # kill a trailing comment
    return line


def parse_rank(payload: str) -> Optional[List[str]]:
    lb = payload.find("[")
    if lb < 0:
        return None
    depth = 0
    for i in range(lb, len(payload)):
        if payload[i] == "[":
            depth += 1
        elif payload[i] == "]":
            depth -= 1
            if depth == 0:
                blob = payload[lb:i + 1]
                for loader in (json.loads, ast.literal_eval):
                    try:
                        v = loader(blob)
                        if isinstance(v, list):
                            return [str(x).strip() for x in v if str(x).strip()]
                    except Exception:
                        pass
                return None
    return None


def _envelope(result: Any) -> str:
    s = json.dumps(result, default=str)
    if len(s) <= RESULT_CAP:
        return s
    # Keep it valid JSON: truncate rows, not mid-token (arm_cli envelope fix).
    if isinstance(result, list):
        head = result[:50]
        return json.dumps({"_truncated": True, "shown": len(head),
                           "total": len(result), "rows": head}, default=str)[:RESULT_CAP]
    return json.dumps({"_truncated": True,
                       "head": s[:RESULT_CAP - 60]})


# --------------------------------------------------------------------------
# System prompt: frozen arm prompt + reply-protocol override + inlined framework.
# --------------------------------------------------------------------------
def build_system(arm: str) -> str:
    base = (ROOT / "harness" / "prompts" / f"{arm}.txt").read_text()
    access = ARM_ACCESS[arm]
    lines = [base.strip(), "",
             "=" * 70,
             "HOW TO INTERACT (this REPLACES the '{WRAPPER} <subcommand>' shell "
             "syntax above — you have no shell; you emit directive lines and I "
             "run them):",
             "In each reply, output one or more directive lines. I execute them "
             "and return results; then you continue. Allowed directives:"]
    if access["cypher"]:
        lines.append("  CYPHER: <one-line read-only Cypher>   — I run it, return JSON rows.")
    if access["tools"]:
        lines.append("  TOOL: <name> <json-args>              — platform tool; "
                     f"available: {', '.join(access['tools'])}.")
    lines += [
        "  SAY: <text>                           — recorded as your exact "
        "per-criterion binding note (state threshold/weight/sign).",
        "  RANK: [\"GENE1\",\"GENE2\", ...]          — your FINAL top-30 gene "
        "symbols, best first. This ENDS the session; emit it exactly once.",
        "",
        "CRITICAL RULES — follow exactly:",
        "  • Emit ONE query per message: at most one CYPHER (or one TOOL) line.",
        "  • Put the ENTIRE Cypher on ONE physical line, ending at the newline. "
        "Nothing after it on that line.",
        "  • NEVER write, echo, predict, or invent query results. I run the query "
        "and give you the real rows; if you paste a fake `[{...}]` result it is "
        "discarded and your query will fail. Wait for my rows before continuing.",
        "  • Do NOT wrap directives in code fences (no ```).",
        "  • Schema note: relationship types are multi-word and MUST be "
        "backticked, e.g. `-[:\\`differentially expresses\\`]->`, "
        "`-[:\\`risk of trait\\`]->`. Use elementId(n) (not id(n)).",
        "  • Emit SAY notes for each criterion as you finalize its binding.",
    ]
    if not access["cypher"] and not access["tools"]:
        lines.append("  • You have NO data access — no CYPHER, no TOOL. Apply the "
                     "framework from its text and your own knowledge; be explicit "
                     "about which criteria you could not evaluate without data.")
    else:
        lines.append("  • Explore with small probe queries first (filter to "
                     "DISEASE_OF_INTEREST, LIMIT while exploring), then compute a composite "
                     "and RANK the top 30.")
    lines += ["", "=" * 70, "FRAMEWORK DOCUMENT (this is the prose skills file "
              "referenced above; read it in full before acting):", "",
              FRAMEWORK_MD]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# The session loop.
# --------------------------------------------------------------------------
def run_session(arm: str, seed: int, out_path: Path) -> Dict[str, Any]:
    access = ARM_ACCESS[arm]
    system = build_system(arm)
    history: List[Dict[str, str]] = [
        {"role": "user", "text": "Begin. Read the framework, then work the task. "
         "Emit directive lines (SAY/CYPHER/TOOL) and finish with RANK."}]
    # Append+flush every record as it happens: a rate-limit death mid-session
    # leaves a partial-but-valid trace, and progress is watchable. Nothing is
    # reconstructed after the fact (CLAUDE.md #1) — we only persist what ran.
    fh = open(out_path, "w")

    def emit(rec: Dict[str, Any]) -> None:
        fh.write(json.dumps(rec) + "\n")
        fh.flush()

    log: List[Dict[str, Any]] = []

    def record(rec: Dict[str, Any]) -> None:
        log.append(rec)
        emit(rec)

    turn = 0
    tool_calls = 0
    unparsed = 0
    ranking: List[str] = []
    done = False
    ranked_empty = False
    rank_parse_fails = 0
    no_directive_strikes = 0

    while turn < MAX_TURNS and tool_calls < MAX_TOOL_CALLS and not done:
        turn += 1
        reply = call_model(system, history, seed=seed)
        history.append({"role": "model", "text": reply})
        directives = parse_directives(reply)

        # A RANK is terminal ONLY if the same reply has no pending CYPHER/TOOL.
        # A reasoning model routinely lays out its whole plan in one turn —
        # including a PROVISIONAL RANK from priors — before it has executed any
        # query. Honouring that RANK terminates on turn 1 with a priors-only list
        # the model never actually derived from data (exactly the A1 failure, but
        # mislabelled as A3). So if the reply also asks to query, we run the
        # queries and drop the premature RANK, letting the model re-rank once it
        # has seen real rows. Provider-agnostic; Gemini emitted one directive per
        # turn so this leaves the completed Gemini data unchanged.
        # Only count a query the arm can ACTUALLY run: for A1 (no data access) a
        # spurious CYPHER/TOOL attempt is rejected and returns nothing, so it must
        # NOT suppress the RANK — else A1 (which legitimately ranks from priors)
        # never terminates.
        has_pending_query = (
            (access["cypher"] and any(k == "CYPHER" for k, _ in directives)) or
            (access["tools"] and any(k == "TOOL" for k, _ in directives)))
        rank_dir = next((p for (k, p) in directives if k == "RANK"), None)
        if rank_dir is not None and not has_pending_query:
            parsed = parse_rank(rank_dir)
            if parsed is None:
                rank_parse_fails += 1
                unparsed += 1
                if rank_parse_fails >= 3:
                    record({"turn": turn, "kind": "final_ranking", "entities": []})
                    ranked_empty = True
                    done = True
                    break
                history.append({"role": "user", "text": "Your RANK line did not "
                                "parse as a JSON array of gene symbols. Re-emit: "
                                'RANK: ["SYM1","SYM2", ...] with double quotes.'})
                continue
            ranking = parsed
            ranked_empty = len(parsed) == 0
            record({"turn": turn, "kind": "final_ranking", "entities": ranking})
            done = True
            break

        if not directives:
            no_directive_strikes += 1
            # record the model's prose as narration (disclosure signal) anyway
            record({"turn": turn, "kind": "text", "content": reply})
            if no_directive_strikes >= 3:
                break
            history.append({"role": "user", "text": "I saw no directive line. "
                            "Reply with SAY:/CYPHER:/TOOL:/RANK: lines only."})
            continue
        no_directive_strikes = 0

        feedback: List[str] = []
        for kind, payload in directives:
            if kind == "SAY":
                record({"turn": turn, "kind": "text", "content": payload})
                continue
            if kind == "CYPHER":
                if not access["cypher"]:
                    feedback.append("CYPHER not permitted for this arm.")
                    continue
                cy = payload.strip().strip("`").strip()
                cy = " ".join(cy.splitlines()).strip()
                # Flash copies the shell example `cypher "<CYPHER>"` and wraps the
                # query in a matched quote pair — strip ONE surrounding pair only
                # (a real Cypher read query never both opens and closes on a quote).
                if len(cy) >= 2 and cy[0] == cy[-1] and cy[0] in ("\"", "'"):
                    cy = cy[1:-1].strip()
                tool_calls += 1
                rec = {"turn": turn, "kind": "tool_call", "tool": "query",
                       "raw_query": cy, "input": {}}
                try:
                    rows = gateway.execute_query(cy)
                    rec["ok"] = True
                    record(rec)
                    feedback.append(f"CYPHER rows: {_envelope(rows)}")
                except Exception as ex:
                    rec["ok"] = False
                    rec["error"] = str(ex)[:200]
                    record(rec)
                    feedback.append(f"CYPHER error: {str(ex)[:200]}")
                continue
            if kind == "TOOL":
                if not access["tools"]:
                    feedback.append("TOOL not permitted for this arm.")
                    continue
                name, _, argstr = payload.strip().partition(" ")
                name = name.strip()
                argstr = argstr.strip()
                args: Dict[str, Any] = {}
                if argstr:
                    try:
                        args = json.loads(argstr)
                    except Exception:
                        m = re.search(r"\{.*\}", argstr, re.S)
                        if m:
                            try:
                                args = json.loads(m.group(0))
                            except Exception:
                                args = {}
                if name not in access["tools"] or name not in TOOLS:
                    feedback.append(f"TOOL {name} not available. Use one of: "
                                    f"{', '.join(access['tools'])}.")
                    continue
                tool_calls += 1
                # raw_query = the structured args string the model emitted, EXACTLY
                # (CLAUDE.md #1); matches how Claude MCP calls were logged.
                rec = {"turn": turn, "kind": "tool_call", "tool": name,
                       "raw_query": json.dumps(args), "input": args}
                try:
                    result = TOOLS[name](args)
                    rec["ok"] = True
                    record(rec)
                    feedback.append(f"TOOL {name} -> {_envelope(result)}")
                except Exception as ex:
                    rec["ok"] = False
                    rec["error"] = str(ex)[:200]
                    record(rec)
                    feedback.append(f"TOOL {name} error: {str(ex)[:200]}")
                continue

        if rank_dir is not None:   # a premature RANK was set aside this turn
            feedback.append("NOTE: I ran your queries above but IGNORED the RANK "
                            "you emitted before seeing their results. Review the "
                            "real rows, compute the composite, then emit RANK.")
        history.append({"role": "user", "text": "\n".join(feedback) +
                        "\n\nContinue, or emit RANK when done."})

    fh.close()
    # "failed" = never reached a terminal decision (looped out / no directives).
    # A deliberate empty ranking is NOT a failure — it is the model deciding
    # nothing qualifies, which is itself a datum (esp. on a weaker model).
    failed = not done
    status = {
        "arm": arm, "seed": seed, "turns": turn, "tool_calls": tool_calls,
        "unparsed": unparsed, "ranked": bool(ranking), "n_ranked": len(ranking),
        "ranked_empty": ranked_empty, "done": done, "failed": failed,
        "trace": str(out_path),
    }
    return status


def main():
    global MODEL, PROVIDER
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=list(ARM_ACCESS))
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--label", default=None, help="seed label for filename, e.g. s1")
    ap.add_argument("--provider", default="gemini", choices=["gemini", "deepseek"],
                    help="model vendor / transport")
    ap.add_argument("--model", default=None,
                    help="model id; default per provider (gemini-2.5-flash / deepseek-chat)")
    ap.add_argument("--tag", default="gem",
                    help="trace filename prefix (runs/<tag>_<arm>_<label>.jsonl); e.g. gpro, ds")
    args = ap.parse_args()
    PROVIDER = args.provider
    MODEL = args.model or ("deepseek-chat" if PROVIDER == "deepseek" else "gemini-2.5-flash")
    label = args.label or f"s{args.seed}"
    out = ROOT / "runs" / f"{args.tag}_{args.arm}_{label}.jsonl"
    print(f"[{PROVIDER} {MODEL}] arm={args.arm} seed={args.seed} -> {out.name}",
          flush=True)
    t0 = time.time()
    status = run_session(args.arm, args.seed, out)
    status["wall_s"] = round(time.time() - t0, 1)
    print(json.dumps(status, indent=2), flush=True)
    # sidecar status for the batch driver
    (out.with_suffix(".status.json")).write_text(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
