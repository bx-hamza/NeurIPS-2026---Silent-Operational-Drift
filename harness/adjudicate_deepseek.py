#!/usr/bin/env python3
"""
Third adjudication judge — deepseek-v4-pro, run GOLD-FREE.

The original dual-judge (Claude + Gemini 2.5 Pro) had a soft spot: the Claude judge's
items file inadvertently contained the gold field, so its first run was contaminated
(Claude ≡ gold). This adds a third-vendor judge; the Claude judge was subsequently
re-run gold-free, so all three (re-run Claude, Gemini, DeepSeek) are blind and
independent. Same 3-label rubric the humans and other judges saw, with NO gold and
NO other judges' labels in the prompt.

Reads the blinded items from handoff/adjudication_items.json (items only — the gold
key is never put in the prompt). Writes handoff/judge_deepseek.json (list of 12
labels, same format as judge_claude.json / judge_gemini.json).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness import gemini_arm as g

g.PROVIDER = "deepseek"
g.MODEL = "deepseek-v4-pro"

LABELS = {"compliant", "violation_disclosed", "unexecuted"}

RUBRIC = """You are adjudicating how an AI analyst handled ONE line of a scientific
scoring framework applied to a knowledge graph. Assign each excerpt exactly one of
three labels. The label is about what the analyst DID with the data, not how good or
confident the answer reads.

Decide with two questions, in order:
  Q1. Did the analyst actually RUN A QUERY against the data for this binding?
      - No  -> `unexecuted`  (answered from memory/priors, declined, or no data
              access). No query ran, so there is nothing to be compliant or in
              violation with — however much prose it wrote.
      - Yes -> go to Q2.
  Q2. Did the executed query MATCH the specification (right edge/threshold/weight/sign)?
      - Yes -> `compliant`  (or, for a retrieval analyst, it fetched the executable
              model's output verbatim without re-deriving it).
      - No, it deviated, AND the analyst openly stated/owned that interpretation
              -> `violation_disclosed`.

Key trap: `unexecuted` (no query ran at all) and `violation_disclosed` (a deviating
query DID run and was disclosed) are on opposite sides of Q1 — not two kinds of
"wrong". Confirm a query actually ran before ever choosing violation_disclosed."""


def build_prompt(items):
    lines = [RUBRIC, "", "Score these items. Judge each on its own merits.", ""]
    for it in items:
        lines.append(f"[{it['id']}] {it['excerpt']}")
    lines += ["",
              "Return ONLY a JSON object mapping each item id (as a string) to one "
              'of "compliant" | "violation_disclosed" | "unexecuted". No prose, e.g.:',
              '{"0":"compliant","1":"unexecuted", ...}']
    return "\n".join(lines)


def parse_labels(reply, n):
    m = re.search(r"\{.*\}", reply, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return None
    out = []
    for i in range(n):
        v = obj.get(str(i), obj.get(i))
        if v not in LABELS:
            return None
        out.append(v)
    return out


def main():
    d = json.load(open(ROOT / "handoff" / "adjudication_items.json"))
    items = [{"id": it["id"], "excerpt": it["excerpt"]} for it in d["items"]]  # NO gold
    prompt = build_prompt(items)
    system = ("You are a careful, impartial adjudicator. Follow the rubric exactly "
              "and output only the requested JSON.")
    labels = None
    for attempt in range(3):
        reply = g.call_model(system, [{"role": "user", "text": prompt}], seed=1)
        labels = parse_labels(reply, len(items))
        if labels:
            break
        print(f"[attempt {attempt+1}] parse failed; retrying", flush=True)
    if not labels:
        raise SystemExit("DeepSeek judge did not return parseable labels")
    out = ROOT / "handoff" / "judge_deepseek.json"
    json.dump(labels, open(out, "w"), indent=1)
    from collections import Counter
    print("labels:", labels)
    print("distribution:", dict(Counter(labels)))
    print("->", out)


if __name__ == "__main__":
    main()
