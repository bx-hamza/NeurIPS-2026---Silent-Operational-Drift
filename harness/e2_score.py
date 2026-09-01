#!/usr/bin/env python3
"""
Score the E2 behavioural run (DSSM) from runs/e2/*.json using the FROZEN metrics.

Two arms:
  A3 (prose+cypher, LIVE): "detected" iff, after the mutation, its live-queried
      verdict says the gene's scRNA credit no longer holds (credited_now == False)
      — i.e. it read the changed substrate. Every perturbed gene is baseline-
      credited, so reported_change = (not credited_now).
  A4 (precomputed report, STALE): agent-free — reported_change = (report score
      changed). A raw DE edit does not re-derive HAS_SCORE_EDGE, so this is
      False on every perturbation: A4 is blind by construction.

Null perturbations are the false-positive baseline (CLAUDE.md #3). detection is
only meaningful relative to false_drift; Fisher exact tests detected-vs-null.
Bootstrap clusters on sessions (each perturbation = one session; CLAUDE.md #6).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness import metrics as M
from harness.metrics import PerturbationResult


def load():
    recs = json.load(open(ROOT / "runs" / "e2" / "_all.json"))
    # A perturbation is a NULL iff its stratum says so. The runner's is_null flag
    # follows perturb.py (kind=='noop') and so mislabels the touch-revert nulls
    # (kind=update_property, stratum=null_control); re-derive from stratum here.
    for r in recs:
        r["is_null"] = (r.get("stratum") == "null_control")
    return recs


def a3_result(r) -> PerturbationResult:
    # baseline gene is credited; A3 detected the change iff it now reports not-credited
    credited_now = r.get("A3_credited_now")
    reported_change = (credited_now is False)   # None (no verdict) counts as no-detect
    return PerturbationResult(
        perturbation_id=r["id"], is_null=r["is_null"],
        reference_rank_delta={}, agent_reported_change=reported_change,
        agent_rank_after={}, reference_rank_after={},
        matched_pre_better_than_post=False)


def a4_result(r) -> PerturbationResult:
    changed = (r.get("A4_score_before") != r.get("A4_score_after"))
    return PerturbationResult(
        perturbation_id=r["id"], is_null=r["is_null"],
        reference_rank_delta={}, agent_reported_change=bool(changed),
        agent_rank_after={}, reference_rank_after={},
        # A4 serves the pre (stale) value; a real change makes pre WRONG vs the
        # live reference — that is the staleness signal.
        matched_pre_better_than_post=(not r["is_null"] and not changed))


def summarize(name, results):
    d = M.dssm(results)
    fx = M.detection_above_chance(results)
    print(f"\n=== {name} ===")
    for k, v in d.items():
        print(f"  {k}: {v}")
    print(f"  fisher: odds={fx['odds_ratio']:.3g} p={fx['p_value']:.4g} table={fx['table']}")
    return {"dssm": {k: v.__dict__ for k, v in d.items()}, "fisher": fx}


def main():
    recs = load()
    real = [r for r in recs if not r["is_null"]]
    nulls = [r for r in recs if r["is_null"]]
    print(f"perturbations: {len(recs)} ({len(real)} real, {len(nulls)} null)")
    # sanity: reference/agent-free truth
    live_tracks = sum(1 for r in real if r.get("live_credited_after_apply") is False)
    print(f"live reference tracked the mutation (credit dropped) on {live_tracks}/{len(real)} real")
    reverts = sum(1 for r in recs if r.get("revert_ok"))
    print(f"reverts verified ok: {reverts}/{len(recs)}")
    a4_stale = sum(1 for r in real if r.get("A4_score_before") == r.get("A4_score_after"))
    print(f"A4 report score UNCHANGED under real mutation (stale): {a4_stale}/{len(real)}")

    a3 = [a3_result(r) for r in recs]
    a4 = [a4_result(r) for r in recs]
    out = {"n_real": len(real), "n_null": len(nulls),
           "live_reference_tracked": f"{live_tracks}/{len(real)}",
           "reverts_ok": f"{reverts}/{len(recs)}",
           "A4_stale_on_real": f"{a4_stale}/{len(real)}",
           "A3": summarize("A3 (live query)", a3),
           "A4": summarize("A4 (precomputed report, agent-free)", a4)}
    Path(ROOT / "analysis").mkdir(exist_ok=True)
    json.dump(out, open(ROOT / "analysis" / "e2.json", "w"), indent=2, default=str)
    print("\n-> analysis/e2.json")


if __name__ == "__main__":
    main()
