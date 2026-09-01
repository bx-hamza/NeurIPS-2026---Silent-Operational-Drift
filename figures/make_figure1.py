#!/usr/bin/env python3
"""Figure 1: operationalization fidelity versus decision divergence (E1).

Regenerates the paper figure from data/HANDOFF.json alone.
    python figures/make_figure1.py [--out figures/figure1.pdf]
"""
import argparse, json, pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parent.parent
BLUE, GREEN, RED, GRAY = "#4C72B0", "#55A868", "#C44E52", "#B3B3B3"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--handoff", default=ROOT / "data" / "HANDOFF.json")
    ap.add_argument("--out", default=ROOT / "figures" / "figure1.pdf")
    a = ap.parse_args()

    e1 = json.load(open(a.handoff))["e1_fidelity"]
    of = {k: e1["by_arm"][k]["of"]["point"] for k in ("A1", "A2", "A3", "A4")}
    div = e1["decision_divergence_top10_jaccard_vs_A4"]
    mean = {k: sum(v) / len(v) for k, v in div.items()}
    mean["A4"] = 1.0  # A4 is the reference

    labels = ["A1\nprose/no-data", "A2\nprose+queries",
              "A3\nprose+tools", "A4\nexecutable"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.2, 3.7))
    fig.suptitle("E1: binding-compliance is not reproducibility (Claude, 3 seeds)",
                 fontsize=12)

    # A1 has undefined OF (it executed nothing), so it is drawn as absent.
    ax1.bar(labels, [0.0, of["A2"], of["A3"], of["A4"]],
            color=["none", BLUE, BLUE, GREEN], width=0.62)
    ax1.axhline(1.0, ls=":", lw=1, color="0.6")
    ax1.set_ylim(0, 1.12)
    ax1.set_ylabel("Operationalization fidelity (OF)", fontsize=11)
    ax1.set_title("OF: every executing arm looks compliant", fontsize=11)
    ax1.text(0, 0.10, "undefined\n(all unexecuted)", ha="center", va="bottom",
             color="0.5", fontsize=9)

    vals = [mean["A1"], mean["A2"], mean["A3"], mean["A4"]]
    bars = ax2.bar(labels, vals, color=[GRAY, RED, RED, GREEN], width=0.62)
    for b, v in zip(bars, vals):
        ax2.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.2f}",
                 ha="center", va="bottom", fontsize=10)
    ax2.set_ylim(0, 1.12)
    ax2.set_ylabel("Top-10 overlap with executable arm\n"
                   "(Jaccard; low = inverted portfolio)", fontsize=11)
    ax2.set_title("Portfolio: prose arms barely overlap the executable", fontsize=11)

    for ax in (ax1, ax2):
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(axis="x", labelsize=9.5)

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(a.out)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
