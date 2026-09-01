#!/usr/bin/env python3
"""
Score the human adjudication subsample once a scientist returns their labels.

Reads the scientist's answers (answers.csv with columns item_id,label[,note]),
the frozen gold labels, and all three blinded LLM judges' per-item labels. Computes:
  - human vs GOLD  : agreement + Cohen's kappa  (does an independent expert confirm
                     the deterministic gold the study leans on?)
  - human vs each JUDGE (Claude, Gemini, DeepSeek) : kappa (are the LLM judges tracking the
                     human, or just agreeing with each other via shared bias?)
  - the pre-registered 20% subset {0,1,2} reported separately.

Writes analysis/human_adjudication.json and prints a summary the handoff's
adjudication.human_subsample field can be filled from.

Usage:
  ../../.venv/bin/python handoff/human_adjudication/score.py handoff/human_adjudication/answers.csv
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Judge labels live in adjudication/ in the artifact repo and in
# handoff/ in the original study tree. Accept whichever is present.
JUDGE_DIR = (ROOT / "adjudication") if (ROOT / "adjudication").is_dir() else (ROOT / "handoff")
sys.path.insert(0, str(ROOT))
from harness.metrics import cohens_kappa

LABELS = {"compliant", "violation_disclosed", "unexecuted"}
PREREG_SUBSET = [0, 1, 2]


def load_gold():
    d = json.load(open(JUDGE_DIR / "adjudication_items.json"))
    g = d["gold"]
    return {i: (g[i] if isinstance(g, list) else g[str(i)]) for i in range(len(d["items"]))}


def load_answers(path):
    ans = {}
    for row in csv.DictReader(open(path)):
        lab = (row.get("label") or "").strip()
        if not lab:
            continue
        if lab not in LABELS:
            raise SystemExit(f"item {row['item_id']}: '{lab}' not one of {sorted(LABELS)}")
        ans[int(row["item_id"])] = lab
    return ans


def agree(a, b, ids):
    return sum(a[i] == b[i] for i in ids) / len(ids) if ids else float("nan")


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: score.py <answers.csv>")
    ans = load_answers(sys.argv[1])
    gold = load_gold()
    claude = json.load(open(JUDGE_DIR / "judge_claude.json"))
    gemini = json.load(open(JUDGE_DIR / "judge_gemini.json"))
    # Third vendor, added after the first pass (deviation 12). The
    # earlier two-judge version of this script predates it, which is why
    # any panel JSON without a vs_deepseek block is stale.
    deepseek = json.load(open(JUDGE_DIR / "judge_deepseek.json"))

    ids = sorted(ans)
    if not ids:
        raise SystemExit("no labels found in answers file (fill the 'label' column).")
    print(f"human scored {len(ids)} of {len(gold)} items: {ids}")

    def block(name, other):
        a = [ans[i] for i in ids]
        b = [other[i] for i in ids]
        k = cohens_kappa(a, b)
        print(f"  human vs {name:8s}: agreement {agree(ans, other, ids):.3f}  "
              f"kappa {k['kappa']:.3f} (n={len(ids)})")
        return {"agreement": round(agree(ans, other, ids), 3), "kappa": round(k["kappa"], 3), "n": len(ids)}

    print("\nFULL scored set:")
    res = {"n_scored": len(ids), "ids": ids,
           "vs_gold": block("GOLD", gold),
           "vs_claude": block("Claude", {i: claude[i] for i in range(len(claude))}),
           "vs_gemini": block("Gemini", {i: gemini[i] for i in range(len(gemini))}),
           "vs_deepseek": block("DeepSeek", {i: deepseek[i] for i in range(len(deepseek))})}

    sub = [i for i in PREREG_SUBSET if i in ans]
    if sub:
        print(f"\npre-registered 20% subset {sub}:")
        res["preregistered_20pct"] = {
            "ids": sub,
            "vs_gold_agreement": round(agree(ans, gold, sub), 3),
            "human_labels": {i: ans[i] for i in sub},
            "gold_labels": {i: gold[i] for i in sub}}
        print(f"  human vs gold agreement on subset: {res['preregistered_20pct']['vs_gold_agreement']:.3f}")

    # disagreements worth a human eye
    disagree = [i for i in ids if ans[i] != gold[i]]
    res["disagreements_vs_gold"] = {i: {"human": ans[i], "gold": gold[i]} for i in disagree}
    if disagree:
        print(f"\nhuman disagreed with gold on items {disagree}:")
        for i in disagree:
            print(f"  item {i}: human={ans[i]}  gold={gold[i]}")
    else:
        print("\nhuman agreed with gold on every scored item.")

    out = ROOT / "analysis" / "human_adjudication.json"
    out.parent.mkdir(exist_ok=True)
    json.dump(res, open(out, "w"), indent=2)
    print(f"\n-> {out}")
    print("\nFill handoff adjudication.human_subsample from vs_gold above "
          "(n, agreement_with_judges via vs_claude/vs_gemini, scorer_blinded=true, "
          "scorer_role='<describe the scientist's role without naming them>').")


if __name__ == "__main__":
    main()
