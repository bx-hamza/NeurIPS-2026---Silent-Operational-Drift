#!/usr/bin/env python3
"""Figure 2: one ambiguous binding, resolved per seed, decides the portfolio.

Per-seed decision divergence of the prose+tools arm (A3) against the
executable arm (A4), for all three model families, coloured by how each seed
resolved the underdetermined aggregation binding.

    python figures/make_figure2.py [--out figures/figure2.pdf]
"""
import argparse, json, pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

ROOT = pathlib.Path(__file__).resolve().parent.parent
BINARY, MAGNITUDE, FAILED = "#C44E52", "#55A868", "#9E9E9E"

# Gemini's divergence of 0.000 is not a clean binding choice: it never
# executes the binding reliably (A3 self-stability 0.000, four silent
# violations). It is drawn as a separate category so the figure does not
# overclaim a resolved choice.
CAPABILITY_FAILURE = {"Gemini 2.5 Flash"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--handoff", default=ROOT / "data" / "HANDOFF.json")
    ap.add_argument("--out", default=ROOT / "figures" / "figure2.pdf")
    a = ap.parse_args()

    e1 = json.load(open(a.handoff))["e1_fidelity"]
    bam = e1["by_arm_model"]
    models = {
        "Claude": ("claude", e1["decision_divergence_top10_jaccard_vs_A4"]["A3"]),
        "Gemini 2.5 Flash": ("gemini-2.5-flash",
                             bam["gemini-2.5-flash"]["decision_divergence_top10_jaccard_vs_A4"]["A3"]),
        "DeepSeek-V4-Pro": ("deepseek-v4-pro",
                            bam["deepseek-v4-pro"]["decision_divergence_top10_jaccard_vs_A4"]["A3"]),
    }

    fig, ax = plt.subplots(figsize=(9.4, 2.25))
    x = np.arange(len(models))
    w = 0.22

    for i, (label, (key, seeds)) in enumerate(models.items()):
        of = bam[key]["by_arm"]["A3"]["of"]["point"]
        stab = bam[key]["self_stability_top10_jaccard"]["A3"]
        for j, v in enumerate(seeds):
            if label in CAPABILITY_FAILURE:
                colour = FAILED
            else:
                colour = MAGNITUDE if v >= 0.999 else BINARY
            ax.bar(x[i] + (j - 1) * w, max(v, 0.006), width=w * 0.9,
                   color=colour, edgecolor="white", linewidth=0.6)
            ax.text(x[i] + (j - 1) * w, v + 0.035, f"{v:.3f}",
                    ha="center", va="bottom", fontsize=8)
        models[label] = (key, seeds, of, stab)

    ax.axhline(1.0, ls=":", lw=1, color="0.65")
    ax.set_xticks(x)
    ax.set_xticklabels(
        [f"{m}\n(A3 OF {v[2]:.2f}, self-stability {v[3]:.2f})"
         for m, v in models.items()], fontsize=9)
    # Headroom above the tallest bar so the legend never sits on the data.
    ax.set_ylim(0, 1.52)
    ax.set_yticks([0, 0.5, 1.0])
    ax.set_ylabel("Top-10 Jaccard\nvs. A4", fontsize=9.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=9)
    ax.legend(handles=[
        Patch(facecolor=BINARY, label="seed bound binary presence"),
        Patch(facecolor=MAGNITUDE, label="seed bound continuous magnitude (= reference)"),
        Patch(facecolor=FAILED, label="binding not reliably executed")],
        loc="upper left", ncol=1, fontsize=8.4, frameon=False,
        labelspacing=0.45, handlelength=1.4, borderpad=0.2)

    fig.tight_layout()
    fig.savefig(a.out)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
