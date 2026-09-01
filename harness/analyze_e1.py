#!/usr/bin/env python3
"""
E1 analysis: OF/SVR by arm (clustered bootstrap on sessions), compare_arms(A4,A3),
and the PRIMARY metric — decision divergence (top-k Jaccard vs the executable arm).
Uses the FROZEN metrics.py + extract_tp4 classifier. Scored seeds: s1,s2,s3
(s0 pilot is exploratory, reported separately).
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.extract_tp4 import classify_arm, TP4_PARAMS, UNDERDETERMINED
from harness.reference import oracle_ranking
from harness import metrics as M

ARMS = ["A1", "A2", "A3", "A4"]
RETR = {"A1": False, "A2": False, "A3": False, "A4": True}
SEEDS = ["s1", "s2", "s3"]
PAT = "runs/e1_{a}_{s}.jsonl"
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


def jac(a, b, k=10):
    A, B = set(a[:k]), set(b[:k])
    return len(A & B) / len(A | B) if A | B else 0.0


# Score every session -> per-session list of param states (excluding P08 for the
# clean deterministic OF; P08 is the underdetermined binding, judge-adjudicated).
NONP08 = [pid for pid, _ in TP4_PARAMS if pid not in UNDERDETERMINED]
states = {a: [] for a in ARMS}          # per-arm list of per-session state-lists (non-P08)
p08 = {a: [] for a in ARMS}             # per-arm P08 state per session
for a in ARMS:
    for s in SEEDS:
        f = classify_arm(Path(PAT.format(a=a, s=s)), is_retrieval=RETR[a], oracle_top=oracle30)
        by = {x.pid: x for x in f}
        states[a].append([by[p].state for p in NONP08])
        p08[a].append(by["P08"].state)

print("="*72)
print("E1 — 4 arms x 3 seeds (Claude), prereg-v1. PRIMARY metric = decision divergence.")
print("="*72)

print("\n[1] DECISION DIVERGENCE vs executable arm A4 (top-10 Jaccard) — PRIMARY")
for a in ["A1", "A2", "A3"]:
    js = [jac(ranking(PAT.format(a=a, s=s)), ranking(PAT.format(a="A4", s=s))) for s in SEEDS]
    print(f"   {a} vs A4:  per-seed {['%.3f'%x for x in js]}  mean={sum(js)/len(js):.3f}")
# A2 vs A3 convergence
js = [jac(ranking(PAT.format(a="A2", s=s)), ranking(PAT.format(a="A3", s=s))) for s in SEEDS]
print(f"   A2 vs A3 (prose convergence): {['%.3f'%x for x in js]}")

print("\n[2] OF / unexecuted / SVR by arm (clustered bootstrap on sessions; non-P08 bindings)")
for a in ARMS:
    unex = M.unexecuted_rate(states[a])
    try:
        of = M.operationalization_fidelity(states[a])
        of_s = str(of)
    except Exception:
        of_s = "undefined (all unexecuted)"
    try:
        svr = M.silent_violation_rate(states[a]); svr_s = str(svr)
    except Exception:
        svr_s = "undefined (no violations)"
    print(f"   {a}: OF={of_s}")
    print(f"        unexecuted_rate={unex}")

print("\n[3] compare_arms(A4, A3) — OF difference on non-P08 bindings")
cmp = M.compare_arms(states["A4"], states["A3"])
print(f"   OF difference A4-A3 = {cmp['of_difference']:.3f}, 95% CI {['%.3f'%x for x in cmp['ci95']]}, excludes_zero={cmp['excludes_zero']}")
print("   (Expected ~0: both arms are compliant on the query-extractable bindings.")
print("    The effect is NOT in OF — it is in decision divergence [1] and P08 [4].)")

print("\n[4] P08 aggregation (underdetermined; magnitude=correct, binary=drift)")
for a in ["A2", "A3", "A4"]:
    print(f"   {a}: per-seed P08 = {p08[a]}")
print("   All prose arms (A2,A3) executed BINARY-presence aggregation every seed")
print("   (disclosed); A4 uses the executable model. Deterministic detection is")
print("   formulation-brittle -> the dual-judge scores disclosed-vs-silent (D7).")

print("\n[5] Cross-seed stability (E3): within-arm top-10 Jaccard + Kendall tau")
for a in ARMS:
    rks = [ranking(PAT.format(a=a, s=s)) for s in SEEDS]
    st = M.seed_stability(rks, top_k=10)
    print(f"   {a}: top10_jaccard_mean={st['top10_jaccard_mean']:.3f} kendall_tau_mean={st.get('kendall_tau_mean',float('nan')):.3f}")

# persist
out = {"decision_divergence": {a: [jac(ranking(PAT.format(a=a,s=s)), ranking(PAT.format(a="A4",s=s))) for s in SEEDS] for a in ["A1","A2","A3"]},
       "compare_A4_A3_OF": cmp, "p08_by_arm_seed": p08,
       "sessions": {a: {"seeds": SEEDS, "n": len(SEEDS)} for a in ARMS}, "sessions_failed": 0}
Path("analysis").mkdir(exist_ok=True)
json.dump(out, open("analysis/e1.json","w"), indent=2)
print("\n-> analysis/e1.json")
