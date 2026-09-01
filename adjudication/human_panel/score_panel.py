#!/usr/bin/env python3
"""
Score a PANEL of independent human raters for the adjudication subsample.

Each rater's answers live in handoff/human_adjudication/answers_p{N}.csv (same
format as the single-rater template: item_id,label[,note]). Raters are anonymous
(p1, p2, …) — do not put names in filenames.

Computes, from the FROZEN gold + all three blinded LLM judges' labels:

NOTE: judge_claude.json is the BLIND RE-RUN. judge_claude_LEAKED.json is
the contaminated first run, preserved for audit and never scored here.
A panel JSON whose vs_claude equals its vs_gold was computed against the
contaminated run and is stale.
  - per-rater agreement + Cohen's kappa vs gold
  - inter-rater reliability among the humans: Fleiss' kappa (rubric validity) and
    mean pairwise Cohen's kappa, plus the unanimous-item rate
  - the human CONSENSUS (modal label per item); items with no majority are flagged
    `split` and reported separately (an ambiguous item is a signal, not an error)
  - consensus vs gold and vs each of the three blinded LLM judges
  - a per-item table (the 5 human labels + gold)

Fleiss' kappa is implemented here (not in the frozen metrics.py); Cohen's kappa is
imported from the frozen metrics. Writes analysis/human_adjudication_panel.json.

Usage:
  python adjudication/human_panel/score_panel.py
  # specialists-only sensitivity check (drops the non-field reviewer p5):
  python adjudication/human_panel/score_panel.py \
      adjudication/human_panel/answers_p{1,2,3,4}.csv \
      --out analysis/human_adjudication_panel_specialists.json
  (globs answers_p*.csv in this folder; or pass explicit CSV paths as arguments)
"""
import csv
import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Judge labels live in adjudication/ in the artifact repo and in
# handoff/ in the original study tree. Accept whichever is present.
JUDGE_DIR = (ROOT / "adjudication") if (ROOT / "adjudication").is_dir() else (ROOT / "handoff")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from harness.metrics import cohens_kappa

LABELS = {"compliant", "violation_disclosed", "unexecuted"}


def load_gold():
    d = json.load(open(JUDGE_DIR / "adjudication_items.json"))
    g = d["gold"]
    return {i: (g[i] if isinstance(g, list) else g[str(i)]) for i in range(len(d["items"]))}


def load_rater(path):
    ans = {}
    for row in csv.DictReader(open(path)):
        lab = (row.get("label") or "").strip()
        if not lab:
            continue
        if lab not in LABELS:
            raise SystemExit(f"{os.path.basename(path)} item {row['item_id']}: "
                             f"'{lab}' not one of {sorted(LABELS)}")
        ans[int(row["item_id"])] = lab
    return ans


def fleiss_kappa(rows):
    """rows: list over items of Counter(label->count); every item rated by the same
    number of raters n. Returns kappa or None if raters-per-item is not constant."""
    cats = sorted(LABELS)
    counts = [[r.get(c, 0) for c in cats] for r in rows]
    ns = {sum(row) for row in counts}
    if len(ns) != 1:
        return None                      # unequal raters/item -> Fleiss undefined
    n = ns.pop()
    if n < 2:
        return None
    N = len(counts)
    P_i = [(sum(x * x for x in row) - n) / (n * (n - 1)) for row in counts]
    P_bar = sum(P_i) / N
    p_j = [sum(row[j] for row in counts) / (N * n) for j in range(len(cats))]
    P_e = sum(p * p for p in p_j)
    return None if P_e >= 1 else (P_bar - P_e) / (1 - P_e)


def main():
    # Explicit --out so the specialists sensitivity run is reproducible rather
    # than a hand-edited copy of the full-panel output. Rater CSVs may be given
    # positionally to restrict the panel (e.g. the specialists subset).
    argv = list(sys.argv[1:])
    out_path = ROOT / "analysis" / "human_adjudication_panel.json"
    if "--out" in argv:
        i = argv.index("--out")
        try:
            out_path = Path(argv[i + 1])
        except IndexError:
            raise SystemExit("--out needs a path")
        del argv[i:i + 2]
        if not out_path.is_absolute():
            out_path = ROOT / out_path
    paths = argv or sorted(glob.glob(str(HERE / "answers_p*.csv")))
    if not paths:
        raise SystemExit("no rater files. Save each person's as answers_p1.csv, "
                         "answers_p2.csv, … in this folder (or pass paths).")
    gold = load_gold()
    claude = json.load(open(JUDGE_DIR / "judge_claude.json"))
    gemini = json.load(open(JUDGE_DIR / "judge_gemini.json"))
    # Third vendor, added after the first pass (deviation 12). The
    # earlier two-judge version of this script predates it, which is why
    # any panel JSON without a vs_deepseek block is stale.
    deepseek = json.load(open(JUDGE_DIR / "judge_deepseek.json"))
    items = sorted(gold)

    raters = {}
    for p in paths:
        name = Path(p).stem.replace("answers_", "")
        raters[name] = load_rater(p)
    print(f"panel: {len(raters)} raters {list(raters)}")

    # per-rater vs gold
    per_rater = {}
    print("\nper-rater vs GOLD:")
    for name, ans in raters.items():
        ids = [i for i in items if i in ans]
        a = [ans[i] for i in ids]; b = [gold[i] for i in ids]
        agr = sum(x == y for x, y in zip(a, b)) / len(ids) if ids else float("nan")
        k = cohens_kappa(a, b)["kappa"]
        per_rater[name] = {"n": len(ids), "agreement_vs_gold": round(agr, 3),
                           "kappa_vs_gold": round(k, 3)}
        print(f"  {name}: n={len(ids)}  agreement {agr:.3f}  kappa {k:.3f}")

    # items rated by all raters (for panel stats)
    common = [i for i in items if all(i in a for a in raters.values())]
    rlabels = {name: [ans[i] for i in common] for name, ans in raters.items()}

    # inter-rater
    rows = [Counter(raters[name][i] for name in raters) for i in common]
    fk = fleiss_kappa(rows)
    names = list(raters)
    pairwise = []
    for x in range(len(names)):
        for y in range(x + 1, len(names)):
            pairwise.append(cohens_kappa(rlabels[names[x]], rlabels[names[y]])["kappa"])
    mean_pw = sum(pairwise) / len(pairwise) if pairwise else float("nan")
    unanimous = sum(1 for r in rows if len(r) == 1) / len(rows) if rows else float("nan")
    print(f"\ninter-rater (on {len(common)} items all rated):")
    print(f"  Fleiss kappa: {fk if fk is None else round(fk,3)}")
    print(f"  mean pairwise Cohen kappa: {mean_pw:.3f}")
    print(f"  unanimous items: {unanimous:.3f}")

    # consensus (modal); ties -> split
    consensus, split = {}, []
    for i, r in zip(common, rows):
        top = r.most_common()
        if len(top) > 1 and top[0][1] == top[1][1]:
            split.append(i)
        else:
            consensus[i] = top[0][0]
    cids = sorted(consensus)
    def vs(other, label):
        a = [consensus[i] for i in cids]; b = [other[i] for i in cids]
        agr = sum(x == y for x, y in zip(a, b)) / len(cids) if cids else float("nan")
        k = cohens_kappa(a, b)["kappa"]
        print(f"  consensus vs {label}: agreement {agr:.3f}  kappa {k:.3f} (n={len(cids)})")
        return {"agreement": round(agr, 3), "kappa": round(k, 3), "n": len(cids)}
    print(f"\nconsensus (modal human label; {len(split)} split items excluded: {split}):")
    cons = {"vs_gold": vs(gold, "GOLD"),
            "vs_claude": vs({i: claude[i] for i in range(len(claude))}, "Claude"),
            "vs_gemini": vs({i: gemini[i] for i in range(len(gemini))}, "Gemini"),
            "vs_deepseek": vs({i: deepseek[i] for i in range(len(deepseek))}, "DeepSeek")}

    # per-item table
    print("\nper-item:")
    table = {}
    for i in items:
        labs = [raters[n].get(i, "-") for n in names]
        con = consensus.get(i, "SPLIT")
        flag = "  <-- consensus != gold" if con not in ("SPLIT", gold[i]) else ("  <-- SPLIT" if con == "SPLIT" else "")
        table[i] = {"raters": labs, "consensus": con, "gold": gold[i]}
        print(f"  item {i:2d}: {labs}  consensus={con:20s} gold={gold[i]}{flag}")

    out = {"n_raters": len(raters), "per_rater": per_rater,
           "inter_rater": {"fleiss_kappa": (None if fk is None else round(fk, 3)),
                           "mean_pairwise_cohen_kappa": round(mean_pw, 3),
                           "unanimous_item_rate": round(unanimous, 3),
                           "n_items_common": len(common)},
           "consensus": cons, "split_items": split, "per_item": table}
    (ROOT / "analysis").mkdir(exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=2)
    try:
        shown = out_path.relative_to(ROOT)
    except ValueError:
        shown = out_path
    print(f"\n-> {shown}")
    print("\nHeadline for the handoff: consensus-vs-gold kappa (rubric holds up) + "
          "Fleiss kappa among humans (rubric is well-defined). Fill "
          "adjudication.human_subsample from these.")


if __name__ == "__main__":
    main()
