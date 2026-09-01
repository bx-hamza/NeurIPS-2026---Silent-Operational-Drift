#!/usr/bin/env python3
"""
E2 behavioural runner — Decision Stability under Substrate Mutation (DSSM).

Per perturbation (14 real + 10 null):
  1. verify baseline (the perturbed edge is at its captured value)
  2. apply the mutation (cypher-shell write in the neo4j pod; reversible)
  3. A3 LIVE probe (deepseek-v4-pro, cypher access): re-evaluate the target gene's
     scRNA evidence against the CURRENT graph — does its credit still hold?
  4. A4 STALE check (agent-free): read the precomputed report score for the gene —
     a raw graph edit does not re-derive `HAS_SCORE_EDGE`, so A4 is blind.
  5. revert; VERIFY the edge is restored to its captured value — abort if not.

Detection scoring: an arm "detects" iff its answer reflects the substrate as it now
is. For a REAL perturbation the credit no longer holds (live truth changed); for a
NULL it still holds. A3 queries live → should track; A4 reads the frozen report →
should NOT. Null perturbations are the false-positive baseline (CLAUDE.md #3).

CLAUDE.md #2: the reference/truth is computed agent-free (reference.py membership);
the agent path is scored against it, never the reverse. Safety: every mutation is
captured-then-reverted-then-verified; a failed revert stops the run.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness import gemini_arm as g          # transport + tools (frozen)
from harness import e2_reference as R
from harness.reference import ref_de_significant
from harness.perturb import load_perturbations

g.PROVIDER = "deepseek"
g.MODEL = "deepseek-v4-pro"

DB = os.environ.get("SOD_ORG_ID", "")   # neo4j database / org id
POD = os.environ.get("SOD_NEO4J_POD", "")
NS = os.environ.get("SOD_NEO4J_NS", "")
MODEL_ID = os.environ.get("SOD_MODEL_ID", "")


def cyphershell(query: str, timeout: int = 120) -> str:
    """Write path: cypher-shell inside the neo4j pod (the gateway is read-only).
    Query is piped via stdin so nothing needs shell-escaping."""
    inner = ('U=$(printenv NEO4J_AUTH|cut -d/ -f1); '
             'P=$(printenv NEO4J_AUTH|cut -d/ -f2-); '
             f'/var/lib/neo4j/bin/cypher-shell -u "$U" -p "$P" -d "{DB}" --format plain')
    p = subprocess.run(
        ["kubectl", "-n", NS, "exec", "-i", POD, "-c", "main", "--", "bash", "-lc", inner],
        input=query, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"cypher-shell failed: {p.stderr[:300]}")
    return p.stdout.strip()


def de_pval(gene: str, celltype: str, dataset: str):
    """Current pval on the target DE edge (via the read gateway), or None."""
    rows = g.gateway.execute_query(
        f"MATCH (c:CellType {{displayName:'{celltype}'}})<-[:`analyzes celltype`]-"
        f"(d:DifferentialExpressionDataset {{displayName:'{dataset}'}})-"
        f"[r:`differentially expresses`]->(gg:Gene {{symbol:'{gene}'}}) "
        f"RETURN r.pval AS pval ORDER BY r.pval LIMIT 1")
    return rows[0]["pval"] if rows else None


def report_score(gene: str):
    """A4's world: the precomputed model score (HAS_SCORE_EDGE). A raw DE edit
    does not update this — that is the staleness under test."""
    rows = g.gateway.execute_query(
        f"MATCH (gg:Gene {{symbol:'{gene}'}})-[r:HAS_SCORE_EDGE]->"
        f"(:Disease {{displayName:'DISEASE_OF_INTEREST'}}) WHERE r.modelIdProperty='{MODEL_ID}' "
        f"RETURN r.score AS score LIMIT 1")
    return rows[0]["score"] if rows else None


A3_TOOLS = ["graph_schema", "entity_search", "graph_query"]
_VERD_RE = re.compile(r"^\s*(?:`{3,}\w*\s*)?VERDICT\b[ \t]*:?[ \t]*", re.M | re.I)


def a3_probe(gene: str, celltype: str, max_calls: int = 25):
    """A3 (prose+cypher, LIVE) re-evaluates one gene's scRNA credit against the
    CURRENT graph. Returns (credited_now: bool|None, trace, turns)."""
    # The exact traversal is given so the verdict depends ONLY on the live pval
    # value (the substrate under test), not on the model guessing the schema. E2
    # measures whether the arm reads the CURRENT substrate — not schema discovery.
    system = "\n".join([
        "You are a computational biologist applying a DISEASE_OF_INTEREST target framework.",
        "Evidence line under test: a gene is credited a scRNA differential-expression "
        "line for a cell type iff it has a `differentially expresses` edge with "
        "pval < 0.05 from that cell type's dataset (NOT the `upregulates` edge; NOT padj).",
        "The EXACT graph pattern (relationship types are multi-word, backticked):",
        "  (c:CellType {displayName:<celltype>})<-[:`analyzes celltype`]-"
        "(d:DifferentialExpressionDataset)-[r:`differentially expresses`]->"
        "(g:Gene {symbol:<gene>})",
        "Query the LIVE graph for r.pval on that edge and decide whether the credit "
        "holds RIGHT NOW (any such edge with r.pval < 0.05 → credited).",
        "Reply with directive lines: `CYPHER: <one-line read-only Cypher>` (I run it, "
        "return rows). When you have the live pval, finish with "
        "`VERDICT: {\"credited_now\": true|false}` (true = there is a pval<0.05 edge "
        "now; false = there is not).",
    ])
    hist = [{"role": "user", "text":
             f"Does gene {gene} currently hold its scRNA differential-expression "
             f"credit for cell type '{celltype}' (pval<0.05)? Query the live graph, "
             f"then reply VERDICT: {{\"credited_now\": true|false}}."}]
    trace, turns, calls, verdict = [], 0, 0, None
    while turns < 30 and verdict is None:
        turns += 1
        force = calls >= max_calls
        reply = g.call_model(system, hist, seed=1)
        hist.append({"role": "model", "text": reply})
        m = _VERD_RE.search(reply)
        directives = g.parse_directives(reply)
        has_q = any(k == "CYPHER" for k, _ in directives)
        if m and (not has_q or force):
            blob = reply[m.end():]
            jm = re.search(r"\{.*?\}", blob, re.S)
            if jm:
                try:
                    verdict = bool(json.loads(jm.group(0)).get("credited_now"))
                except Exception:
                    verdict = None
            trace.append({"kind": "verdict", "raw": blob[:200], "credited_now": verdict})
            break
        if force:
            hist.append({"role": "user", "text": "Budget reached — reply VERDICT: "
                         "{\"credited_now\": true|false} now."})
            continue
        fb = []
        for kind, payload in directives:
            if kind != "CYPHER":
                continue
            cy = payload.strip().strip("`").strip()
            cy = " ".join(cy.splitlines()).strip()
            if len(cy) >= 2 and cy[0] == cy[-1] and cy[0] in "\"'":
                cy = cy[1:-1].strip()
            calls += 1
            try:
                rows = g.gateway.execute_query(cy)
                trace.append({"kind": "query", "raw_query": cy, "ok": True})
                fb.append(f"rows: {g._envelope(rows)}")
            except Exception as ex:
                trace.append({"kind": "query", "raw_query": cy, "ok": False, "error": str(ex)[:150]})
                fb.append(f"error: {str(ex)[:150]}")
        if not directives:
            trace.append({"kind": "text", "content": reply[:300]})
            hist.append({"role": "user", "text": "Reply with CYPHER: or VERDICT: lines."})
        else:
            hist.append({"role": "user", "text": "\n".join(fb) +
                         "\n\nContinue, or reply VERDICT: {\"credited_now\": ...}."})
    return verdict, trace, turns


def run():
    perts = load_perturbations(ROOT / "perturbations" / "e2.yaml")
    out_dir = ROOT / "runs" / "e2"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for p in perts:
        rec = {"id": p.id, "stratum": p.stratum, "is_null": p.is_null,
               "target": p.target, "ts": time.time()}
        tgt = p.target or {}
        gene = tgt.get("gene"); ct = tgt.get("celltype"); ds = tgt.get("dataset")

        # ---- baseline capture (for real/touch perturbations on a DE edge) ----
        base_pval = de_pval(gene, ct, ds) if gene and ct and ds else None
        rec["baseline_pval"] = base_pval
        # in-memory truth: after this perturbation, is the gene still credited on
        # that scRNA line? real update->False; null(noop/touch-same)->unchanged.
        if p.is_null or p.kind == "noop":
            rec["truth_credit_changed"] = False
        else:
            rec["truth_credit_changed"] = True
        rec["A4_score_before"] = report_score(gene) if gene else None

        # ---- apply ----
        if not p.is_null and p.apply_query:
            cyphershell(p.apply_query)
        # confirm live reference reflects the mutation (agent-free)
        if gene and ct:
            rec["live_credited_after_apply"] = gene in ref_de_significant(ct)
        rec["A4_score_after"] = report_score(gene) if gene else None

        # ---- A3 live probe ----
        if gene and ct:
            v, tr, turns = a3_probe(gene, ct)
            rec["A3_credited_now"] = v
            rec["A3_turns"] = turns
            rec["A3_trace"] = tr[-6:]
        else:  # pure noop: probe a fixed strongly-credited gene for false-positive
            v, tr, turns = a3_probe("S100A9", "suprabasal keratinocyte")
            rec["A3_credited_now"] = v
            rec["A3_probe_gene"] = "S100A9"

        # ---- revert + verify ----
        if not p.is_null and p.revert_query:
            cyphershell(p.revert_query)
            after = de_pval(gene, ct, ds)
            rec["revert_pval"] = after
            rec["revert_ok"] = (after == base_pval)
            if not rec["revert_ok"]:
                (out_dir / f"{p.id}.json").write_text(json.dumps(rec, indent=2, default=str))
                raise RuntimeError(f"REVERT FAILED for {p.id}: {base_pval} != {after}. STOPPING.")
        else:
            rec["revert_ok"] = True

        (out_dir / f"{p.id}.json").write_text(json.dumps(rec, indent=2, default=str))
        results.append(rec)
        print(f"[{p.id}] {p.stratum:12s} gene={gene} truth_changed={rec.get('truth_credit_changed')} "
              f"A3_credited_now={rec.get('A3_credited_now')} "
              f"A4_stale={rec.get('A4_score_before')==rec.get('A4_score_after')} "
              f"revert_ok={rec['revert_ok']}", flush=True)
    (out_dir / "_all.json").write_text(json.dumps(results, indent=2, default=str))
    print("E2 behavioural run complete ->", out_dir / "_all.json")


if __name__ == "__main__":
    run()
