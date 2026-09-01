#!/usr/bin/env python3
"""Re-check every numeric claim in the paper against data/HANDOFF.json.

Each assertion below names where the number appears in the paper. If the
scored data changes, this script fails and tells you which claim to fix. It
runs offline and needs no substrate access.

    python verify_numbers.py [--handoff data/HANDOFF.json] [-v]

Exit code 0 if every claim holds, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent


class Checker:
    def __init__(self, verbose: bool = False):
        self.passed = 0
        self.failures: list[str] = []
        self.verbose = verbose

    def eq(self, where: str, got, want, tol: float = 1e-9):
        ok = (got == want) if not isinstance(want, float) else (
            got is not None and abs(got - want) <= tol)
        if ok:
            self.passed += 1
            if self.verbose:
                print(f"  ok   {where}: {got}")
        else:
            self.failures.append(f"{where}: expected {want!r}, got {got!r}")

    def is_none(self, where: str, got):
        self.eq(where, got is None, True)

    def seq(self, where: str, got, want, tol: float = 1e-9):
        if got is None or len(got) != len(want):
            self.failures.append(f"{where}: expected {want!r}, got {got!r}")
            return
        if all(abs(a - b) <= tol for a, b in zip(got, want)):
            self.passed += 1
            if self.verbose:
                print(f"  ok   {where}: {got}")
        else:
            self.failures.append(f"{where}: expected {want!r}, got {got!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--handoff", default=ROOT / "data" / "HANDOFF.json")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    d = json.load(open(args.handoff))
    c = Checker(args.verbose)

    # ---- Setup (paper section 2) -------------------------------------
    c.eq("meta.sessions_completed (S2: '52 sessions completed')",
         d["meta"]["sessions_completed"], 52)
    c.eq("meta.sessions_failed (S2: '3 failed')",
         d["meta"]["sessions_failed"], 3)
    c.eq("meta: three model families tested", len(d["meta"]["models"]), 3)

    e1 = d["e1_fidelity"]
    by_arm = e1["by_arm"]
    bam = e1["by_arm_model"]

    # ---- E1 on Claude (paper 3.1, Figure 1, Appendix Table 2) --------
    c.is_none("E1 Claude A1 OF undefined (3.1: 'OF is undefined')",
              by_arm["A1"]["of"]["point"])
    c.eq("E1 Claude A1 unexecuted (3.1: 'unexecuted rate 1.0')",
         by_arm["A1"]["unexecuted_rate"]["point"], 1.0)
    for arm in ("A2", "A3", "A4"):
        c.eq(f"E1 Claude {arm} OF (3.1: 'OF is 1.00')",
             by_arm[arm]["of"]["point"], 1.0)
    c.eq("E1 Claude A3 unexecuted (3.1: 'rate 0.03')",
         round(by_arm["A3"]["unexecuted_rate"]["point"], 2), 0.03)

    a3a4 = e1["a3_vs_a4"]
    c.eq("A4-A3 OF difference (3.1 + limitations: '0.000')",
         a3a4["of_difference"], 0.0)
    c.seq("A4-A3 CI (3.1: '[0.000,0.000]')", a3a4["ci95"], [0.0, 0.0])
    c.eq("A4-A3 CI spans zero by design (limitations caveat b)",
         a3a4["excludes_zero"], False)

    div = e1["decision_divergence_top10_jaccard_vs_A4"]
    c.seq("Claude A3 divergence (3.1: '0.053 in all three seeds')",
          div["A3"], [0.053, 0.053, 0.053])
    c.seq("Claude A2 divergence (3.1: A2-A3 converge)",
          div["A2"], [0.053, 0.053, 0.053])
    c.seq("Claude A1 divergence (3.1: '0.176 once, 0.250 twice')",
          div["A1"], [0.176, 0.25, 0.25])

    # ---- Cross-vendor (paper 3.2, Figure 2, Appendix Table 2) --------
    gem, ds = bam["gemini-2.5-flash"], bam["deepseek-v4-pro"]

    c.eq("Gemini A3 OF (3.2: '0.773')",
         round(gem["by_arm"]["A3"]["of"]["point"], 3), 0.773)
    c.seq("Gemini A3 OF CI (App: '[0.714, 0.875]')",
          [round(gem["by_arm"]["A3"]["of"]["lo"], 3),
           round(gem["by_arm"]["A3"]["of"]["hi"], 3)], [0.714, 0.875])
    c.eq("Gemini dOF excludes zero (3.2: 'CI [0.125,0.286] excludes zero')",
         gem["a3_vs_a4"]["excludes_zero"], True)
    c.eq("Gemini A3 self-stability (3.2: 'self-stability 0.000')",
         gem["self_stability_top10_jaccard"]["A3"], 0.0)

    silent = (gem["by_arm"]["A2"]["state_counts"]["violation_silent"]
              + gem["by_arm"]["A3"]["state_counts"]["violation_silent"])
    c.eq("Gemini silent violations (3.2: 'five silent violations')", silent, 5)
    total_silent = sum(
        m["by_arm"][a]["state_counts"]["violation_silent"]
        for m in bam.values() for a in ("A1", "A2", "A3", "A4"))
    c.eq("all silent violations are Gemini's (App A.1)", total_silent, 5)

    c.eq("DeepSeek A3 OF (3.2: 'OF 0.867')",
         round(ds["by_arm"]["A3"]["of"]["point"], 3), 0.867)
    c.eq("DeepSeek dOF spans zero (3.2: 'CI [0.000,0.300] spans zero')",
         ds["a3_vs_a4"]["excludes_zero"], False)
    c.seq("DeepSeek A3 per-seed divergence (3.2 + Fig 2: '0.053, 0.053, 1.000')",
          ds["decision_divergence_top10_jaccard_vs_A4"]["A3"],
          [0.053, 0.053, 1.0])
    c.eq("DeepSeek A3 self-stability (3.2: 'mean of 0.368 is bimodal')",
         ds["self_stability_top10_jaccard"]["A3"], 0.368)
    c.eq("DeepSeek A3 disclosed violations (App A.1: 'four disclosed')",
         ds["by_arm"]["A3"]["state_counts"]["violation_disclosed"], 4)

    for name, m in bam.items():
        c.eq(f"A4 model-invariant OF on {name} (3.2)",
             m["by_arm"]["A4"]["of"]["point"], 1.0)
        c.eq(f"A4 self-stability on {name} (3.2)",
             m["self_stability_top10_jaccard"]["A4"], 1.0)

    # ---- E3 / E4 (paper 3.3, Appendix Table 3) -----------------------
    e3 = d["e3_stability"]["by_arm"]
    c.eq("E3 A1 Jaccard (3.3: '0.495')", e3["A1"]["top10_jaccard_mean"], 0.495)
    c.eq("E3 A1 Kendall tau (3.3: '0.446')", e3["A1"]["kendall_tau_mean"], 0.446)
    for arm in ("A2", "A3", "A4"):
        c.eq(f"E3 {arm} Jaccard (3.3: 'stability is 1.00')",
             e3[arm]["top10_jaccard_mean"], 1.0)
        c.eq(f"E3 {arm} Kendall tau (3.3)", e3[arm]["kendall_tau_mean"], 1.0)
    c.eq("E3 A1 scalar not identical across seeds (limitations caveat d)",
         e3["A1"]["scalar_exact_match"]["decision_divergence_vs_A4"]["all_identical"],
         False)

    e4 = d["e4_rewalk"]["by_arm"]
    c.eq("E4 A1 RRR (3.3: 'RRR 0.0')", e4["A1"]["rrr"]["point"], 0.0)
    for arm in ("A2", "A3", "A4"):
        c.eq(f"E4 {arm} RRR (3.3: 'RRR 1.0')", e4[arm]["rrr"]["point"], 1.0)
        c.eq(f"E4 {arm} attempts (3.3: 'one attempt per arm')",
             e4[arm]["n_attempts"], 1)

    # ---- E2 (paper 3.3, Appendix B) ----------------------------------
    e2 = d["e2_dssm"]
    c.eq("E2 real perturbations (3.3: '14 real')", e2["n_real"], 14)
    c.eq("E2 null controls (3.3: '10 null controls')", e2["n_null"], 10)
    c.eq("E2 A3 detection (3.3: 'detection 1.000')",
         e2["by_arm"]["A3"]["detection_rate"]["point"], 1.0)
    c.eq("E2 A3 false drift (3.3: 'false-drift 0.000')",
         e2["by_arm"]["A3"]["false_drift_rate"]["point"], 0.0)
    c.eq("E2 A4 detection (3.3: 'detected nothing (0/14)')",
         e2["by_arm"]["A4"]["detection_rate"]["point"], 0.0)
    c.eq("E2 A4 staleness (3.3: 'staleness 1.000')",
         e2["by_arm"]["A4"]["staleness_rate"]["point"], 1.0)
    c.eq("E2 Fisher p (3.3: 'p = 5.1e-7')",
         round(e2["by_arm"]["A3"]["fisher"]["p_value"], 9), 5.099e-07)

    # ---- E5 (paper 3.4, Appendix Table 4) ----------------------------
    e5 = d["e5_abstention"]["by_arm"]
    for arm in ("A1", "A2", "A3", "A4"):
        c.eq(f"E5 {arm} abstention (3.4: 'abstention 1.00')",
             e5[arm]["abstention_rate"]["point"], 1.0)
        c.eq(f"E5 {arm} improvisation (3.4: 'improvisation 0.00')",
             e5[arm]["improvisation_rate"]["point"], 0.0)
        c.eq(f"E5 {arm} n (3.4: 'n=14 per arm')",
             e5[arm]["abstention_rate"]["n"], 14)

    # ---- Adjudication (paper 3.5, Appendix D) ------------------------
    adj = d["adjudication"]
    c.eq("deterministic items (3.5: '44 settled deterministically')",
         adj["deterministic_items"], 44)
    c.eq("judged items (3.5: '12 formulation-brittle')",
         adj["judged_items"], 12)
    for judge, k in adj["three_judge"]["vs_gold_kappa"].items():
        if not isinstance(k, (int, float)):
            continue  # the block carries an explanatory "note" string
        c.eq(f"judge {judge} vs gold (3.5: 'kappa = 0.75 each')", k, 0.75)
    c.eq("Fleiss across judges (3.5: 'Fleiss kappa = 0.83')",
         adj["kappa"]["kappa"], 0.83)
    for judge, k in adj["three_judge"]["vs_human_consensus_kappa"].items():
        if not isinstance(k, (int, float)):
            continue
        c.eq(f"judge {judge} vs human consensus (3.5: '0.495 per judge')",
             k, 0.495)
    c.eq("judge count (3.5: 'Three gold-free LLM judges')",
         len([v for v in adj["three_judge"]["vs_gold_kappa"].values()
              if isinstance(v, (int, float))]), 3)
    c.eq("unanimous items (3.5: '10/12 unanimous')",
         round(adj["kappa"]["observed_agreement"] * 12), 10)
    c.eq("tie-breaks used (3.5: 'no tie-breaks were needed')",
         adj["tie_breaks_used"], 0)

    hs = adj["human_subsample"]
    c.eq("panel size (3.5: 'five-person blinded human panel')",
         hs["n_raters"], 5)
    c.eq("panel per-rater min (3.5: 'per-rater kappa 0.600--0.862')",
         min(hs["per_rater_kappa_vs_gold"]), 0.6)
    c.eq("panel per-rater max (3.5)",
         max(hs["per_rater_kappa_vs_gold"]), 0.862)
    c.eq("panel Fleiss (3.5: 'Fleiss kappa = 0.687')",
         hs["inter_rater"]["fleiss_kappa"], 0.687)
    c.eq("panel consensus vs gold (3.5: 'kappa = 0.724')",
         hs["consensus_vs_gold"]["kappa"], 0.724)
    c.eq("panel consensus agreement (3.5: 'agreement 0.833')",
         hs["consensus_vs_gold"]["agreement"], 0.833)

    # ---- Cross-check the committed panel analysis against HANDOFF ----
    # audit_staleness.py covers this ground generically across every analysis
    # file; the checks below are kept because they are paper claims, not just
    # internal consistency.
    panel_path = ROOT / "analysis" / "human_adjudication_panel.json"
    if panel_path.exists():
        panel = json.load(open(panel_path))
        cons = panel.get("consensus", {})
        c.eq("panel JSON consensus-vs-gold matches HANDOFF",
             cons.get("vs_gold", {}).get("kappa"), hs["consensus_vs_gold"]["kappa"])
        judge_keys = [k for k in cons if k.startswith("vs_") and k != "vs_gold"]
        c.eq("panel JSON covers all three judges", len(judge_keys), 3)
        for k in judge_keys:
            c.eq(f"panel JSON {k} matches HANDOFF vs_human_consensus_kappa",
                 cons[k]["kappa"], 0.495)
        c.eq("panel JSON Fleiss matches HANDOFF",
             panel.get("inter_rater", {}).get("fleiss_kappa"),
             hs["inter_rater"]["fleiss_kappa"])

    # ---- E7 (paper 3.3, Appendix Table 4) ----------------------------
    e7 = d["e7_efficiency"]["by_arm"]
    c.eq("E7 A3 wall-clock (3.3: '640 s for A3')",
         e7["A3"]["wallclock_s_mean"], 640)
    c.eq("E7 A4 wall-clock (3.3: '400 s for A4')",
         e7["A4"]["wallclock_s_mean"], 400)
    c.eq("E7 equal tool calls (3.3: 'at equal tool calls')",
         e7["A3"]["tool_calls_mean"], e7["A4"]["tool_calls_mean"])

    # ---- Report ------------------------------------------------------
    total = c.passed + len(c.failures)
    if c.failures:
        print(f"FAIL  {c.passed}/{total} claims verified\n")
        for f in c.failures:
            print(f"  - {f}")
        return 1
    print(f"OK    {c.passed}/{total} paper claims verified against "
          f"{pathlib.Path(args.handoff).name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
