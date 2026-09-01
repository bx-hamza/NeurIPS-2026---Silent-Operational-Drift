#!/usr/bin/env python3
"""
E1 analysis for the SECOND MODEL FAMILY (gemini-2.5-flash). Identical logic to
analyze_e1.py — same FROZEN metrics.py + extract_tp4 classifier — only the trace
path glob changes (runs/gem_<arm>_<seed>.jsonl). The whole point is to hold the
instrument fixed and swap the model, so this file must not re-implement any
scoring; it only re-points and re-runs.

KEY question it answers: does the A3-vs-A4 decision divergence (~0.05 on Claude)
replicate on a different vendor, or is it Claude-specific?
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.extract_tp4 import classify_arm, TP4_PARAMS, UNDERDETERMINED
from harness.reference import oracle_ranking
from harness import metrics as M

# Re-point the SAME frozen scoring at any model's traces. Default = Flash.
# For the Gemini 2.5 Pro run: --tag gpro --model gemini-2.5-pro --out analysis/e1_gpro.json
_ap = argparse.ArgumentParser()
_ap.add_argument("--tag", default="gem", help="trace filename prefix under runs/")
_ap.add_argument("--model", default="gemini-2.5-flash", help="model label for the report")
_ap.add_argument("--out", default=None, help="output json (default analysis/e1_<tag>.json)")
_A = _ap.parse_args()
MODEL_LABEL = _A.model
OUT_PATH = _A.out or f"analysis/e1_{_A.tag}.json" if _A.tag != "gem" else "analysis/e1_gemini.json"

ARMS = ["A1", "A2", "A3", "A4"]
RETR = {"A1": False, "A2": False, "A3": False, "A4": True}
SEEDS = ["s1", "s2", "s3"]
PAT = "runs/" + _A.tag + "_{a}_{s}.jsonl"
oracle30 = [e["gene"] for e in oracle_ranking(30)]


def ranking(p):
    p = Path(p)
    if not p.exists():
        return []
    for l in open(p):
        r = json.loads(l)
        if r.get("kind") == "final_ranking":
            return r["entities"]
    return []


def present(a, s):
    return Path(PAT.format(a=a, s=s)).exists() and bool(ranking(PAT.format(a=a, s=s)))


def jac(a, b, k=10):
    A, B = set(a[:k]), set(b[:k])
    return len(A & B) / len(A | B) if A | B else 0.0


# only score sessions that actually produced a ranking (failed sessions are
# reported as sessions_failed, never silently folded into a metric).
avail = {a: [s for s in SEEDS if present(a, s)] for a in ARMS}
NONP08 = [pid for pid, _ in TP4_PARAMS if pid not in UNDERDETERMINED]
states = {a: [] for a in ARMS}
p08 = {a: [] for a in ARMS}
for a in ARMS:
    for s in avail[a]:
        f = classify_arm(Path(PAT.format(a=a, s=s)), is_retrieval=RETR[a], oracle_top=oracle30)
        by = {x.pid: x for x in f}
        states[a].append([by[p].state for p in NONP08])
        p08[a].append(by["P08"].state)

print("=" * 72)
print(f"E1 — SECOND FAMILY {MODEL_LABEL}, prereg-v1 (frozen instrument).")
print("=" * 72)
print("sessions available:", {a: avail[a] for a in ARMS})
failed = {a: [s for s in SEEDS if s not in avail[a]] for a in ARMS}
print("sessions FAILED (no ranking):", {a: failed[a] for a in ARMS if failed[a]})

print("\n[1] DECISION DIVERGENCE vs executable arm A4 (top-10 Jaccard) — PRIMARY")
div = {}
for a in ["A1", "A2", "A3"]:
    seeds_both = [s for s in SEEDS if present(a, s) and present("A4", s)]
    js = [jac(ranking(PAT.format(a=a, s=s)), ranking(PAT.format(a="A4", s=s))) for s in seeds_both]
    div[a] = js
    mean = sum(js) / len(js) if js else float("nan")
    print(f"   {a} vs A4:  seeds {seeds_both}  per-seed {['%.3f'%x for x in js]}  mean={mean:.3f}")
seeds_23 = [s for s in SEEDS if present("A2", s) and present("A3", s)]
js23 = [jac(ranking(PAT.format(a="A2", s=s)), ranking(PAT.format(a="A3", s=s))) for s in seeds_23]
print(f"   A2 vs A3 (prose convergence): seeds {seeds_23} -> {['%.3f'%x for x in js23]}")

print("\n[2] OF / unexecuted by arm (clustered bootstrap on sessions; non-P08)")
of_by = {}
for a in ARMS:
    if not states[a]:
        print(f"   {a}: no scored sessions"); continue
    unex = M.unexecuted_rate(states[a])
    try:
        of = M.operationalization_fidelity(states[a]); of_s = str(of); of_by[a] = of
    except Exception:
        of_s = "undefined (all unexecuted)"
    print(f"   {a}: OF={of_s}")
    print(f"        unexecuted_rate={unex}")

print("\n[3] compare_arms(A4, A3) — OF difference on non-P08 bindings")
if states["A4"] and states["A3"]:
    cmp = M.compare_arms(states["A4"], states["A3"])
    print(f"   OF difference A4-A3 = {cmp['of_difference']:.3f}, 95% CI "
          f"{['%.3f'%x for x in cmp['ci95']]}, excludes_zero={cmp['excludes_zero']}")
else:
    cmp = None
    print("   insufficient sessions")

print("\n[4] P08 aggregation (underdetermined; magnitude=correct, binary=drift)")
for a in ["A2", "A3", "A4"]:
    print(f"   {a}: per-seed P08 = {p08[a]}")

print("\n[5] Cross-seed stability (E3): within-arm top-10 Jaccard + Kendall tau")
stab = {}
for a in ARMS:
    rks = [ranking(PAT.format(a=a, s=s)) for s in avail[a]]
    if len(rks) >= 2:
        st = M.seed_stability(rks, top_k=10)
        stab[a] = st
        print(f"   {a}: top10_jaccard_mean={st['top10_jaccard_mean']:.3f} "
              f"kendall_tau_mean={st.get('kendall_tau_mean', float('nan')):.3f}")
    else:
        print(f"   {a}: <2 sessions, stability n/a")

out = {
    "model": MODEL_LABEL,
    "sessions_available": {a: avail[a] for a in ARMS},
    "sessions_failed": {a: failed[a] for a in ARMS},
    "decision_divergence": div,
    "A2_vs_A3": js23,
    "compare_A4_A3_OF": cmp,
    "p08_by_arm_seed": p08,
    "of": {a: (of_by[a].__dict__ if hasattr(of_by.get(a), "__dict__") else str(of_by.get(a)))
           for a in of_by},
    "stability": {a: stab[a] for a in stab},
}
Path("analysis").mkdir(exist_ok=True)
json.dump(out, open(OUT_PATH, "w"), indent=2, default=str)
print("\n-> " + OUT_PATH)
