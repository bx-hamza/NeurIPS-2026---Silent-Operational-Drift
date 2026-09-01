#!/usr/bin/env python3
"""
Metrics for the SOD study. Every function returns a point estimate and an
interval, because a 2-page paper with bare percentages from n=24 sessions is
the fastest route to a reject.

Conventions that matter for honesty:
  * `unexecuted` is excluded from the OF denominator and reported separately.
  * Clustered bootstrap resamples SESSIONS, not parameter observations.
    Parameters within a session are not independent — one bad universe
    decision correlates violations across P03/P04/P09 — and resampling at the
    observation level would shrink the CIs by roughly sqrt(k) for free.
  * DSSM detection is scored against a reference delta computed with no agent
    in the loop. If the reference is itself agent-derived, delete this file.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import stats

RNG = np.random.default_rng(20260817)

COMPLIANT = "compliant"
VIOL_DISCLOSED = "violation_disclosed"
VIOL_SILENT = "violation_silent"
VIOL_NARRATED_COMPLIANT = "violation_narrated_compliant"
UNEXECUTED = "unexecuted"

VIOLATIONS = (VIOL_DISCLOSED, VIOL_SILENT, VIOL_NARRATED_COMPLIANT)
SILENT = (VIOL_SILENT, VIOL_NARRATED_COMPLIANT)


@dataclass
class Estimate:
    point: float
    lo: float
    hi: float
    n: int
    note: str = ""

    def __str__(self) -> str:
        return f"{self.point:.3f} [{self.lo:.3f}, {self.hi:.3f}] (n={self.n})"


# --------------------------------------------------------------------------
# Clustered bootstrap
# --------------------------------------------------------------------------
def clustered_bootstrap(sessions: Sequence[Sequence[Any]],
                        stat_fn,
                        n_boot: int = 10_000,
                        alpha: float = 0.05) -> Estimate:
    """Resample whole sessions with replacement.

    `sessions` is a list of lists: one inner list of observations per session.
    `stat_fn` takes the flattened observation list and returns a float.
    """
    sessions = [list(s) for s in sessions if len(s) > 0]
    if not sessions:
        return Estimate(float("nan"), float("nan"), float("nan"), 0,
                        "no sessions")
    flat = [o for s in sessions for o in s]
    point = stat_fn(flat)

    k = len(sessions)
    draws = []
    for _ in range(n_boot):
        idx = RNG.integers(0, k, size=k)
        resample = [o for i in idx for o in sessions[i]]
        try:
            draws.append(stat_fn(resample))
        except (ZeroDivisionError, ValueError):
            continue
    if not draws:
        return Estimate(point, float("nan"), float("nan"), len(flat),
                        "bootstrap degenerate")
    lo, hi = np.percentile(draws, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return Estimate(float(point), float(lo), float(hi), len(flat),
                    f"clustered on {k} sessions")


# --------------------------------------------------------------------------
# 1. Operationalization Fidelity + Silent Violation Rate
# --------------------------------------------------------------------------
def _of(observations: List[str]) -> float:
    executed = [s for s in observations if s != UNEXECUTED]
    if not executed:
        raise ValueError("all observations unexecuted")
    return sum(s == COMPLIANT for s in executed) / len(executed)


def _svr(observations: List[str]) -> float:
    viols = [s for s in observations if s in VIOLATIONS]
    if not viols:
        raise ValueError("no violations")
    return sum(s in SILENT for s in viols) / len(viols)


def operationalization_fidelity(sessions_states: Sequence[Sequence[str]]) -> Estimate:
    return clustered_bootstrap(sessions_states, _of)


def silent_violation_rate(sessions_states: Sequence[Sequence[str]]) -> Estimate:
    est = clustered_bootstrap(sessions_states, _svr)
    est.note += " | undefined for arms with zero violations"
    return est


def unexecuted_rate(sessions_states: Sequence[Sequence[str]]) -> Estimate:
    return clustered_bootstrap(
        sessions_states,
        lambda obs: sum(s == UNEXECUTED for s in obs) / len(obs))


def state_breakdown(sessions_states: Sequence[Sequence[str]]) -> Dict[str, int]:
    c: Counter = Counter()
    for s in sessions_states:
        c.update(s)
    return dict(c)


def discriminating_parameters(per_param: Dict[str, List[str]],
                              min_violations: int = 1) -> Dict[str, bool]:
    """A parameter with zero violations across every arm is not measuring
    anything. Report it, exclude it from headline OF, and say so."""
    return {pid: sum(s in VIOLATIONS for s in states) >= min_violations
            for pid, states in per_param.items()}


# --------------------------------------------------------------------------
# 2. Decision Stability under Substrate Mutation
# --------------------------------------------------------------------------
@dataclass
class PerturbationResult:
    perturbation_id: str
    is_null: bool
    reference_rank_delta: Dict[str, int]       # entity -> |rank change|, no agent
    agent_reported_change: bool
    agent_rank_after: Dict[str, int]
    reference_rank_after: Dict[str, int]
    matched_pre_better_than_post: bool          # staleness signal


def dssm(results: Sequence[PerturbationResult]) -> Dict[str, Estimate]:
    real = [r for r in results if not r.is_null]
    nulls = [r for r in results if r.is_null]

    out: Dict[str, Estimate] = {}

    if real:
        out["detection_rate"] = clustered_bootstrap(
            [[1.0 if r.agent_reported_change else 0.0] for r in real],
            lambda xs: float(np.mean(xs)))
        out["staleness_rate"] = clustered_bootstrap(
            [[1.0 if r.matched_pre_better_than_post else 0.0] for r in real],
            lambda xs: float(np.mean(xs)))

        disp = []
        for r in real:
            ents = set(r.agent_rank_after) & set(r.reference_rank_after)
            if ents:
                disp.append([abs(r.agent_rank_after[e] - r.reference_rank_after[e])
                             for e in ents])
        if disp:
            out["rank_displacement_error"] = clustered_bootstrap(
                disp, lambda xs: float(np.mean(xs)))

    if nulls:
        out["false_drift_rate"] = clustered_bootstrap(
            [[1.0 if r.agent_reported_change else 0.0] for r in nulls],
            lambda xs: float(np.mean(xs)))
        out["false_drift_rate"].note += (
            " | CONTROL: detection is only meaningful relative to this")
    else:
        out["false_drift_rate"] = Estimate(
            float("nan"), float("nan"), float("nan"), 0,
            "NO NULL PERTURBATIONS RUN — detection_rate is uninterpretable")

    return out


def detection_above_chance(results: Sequence[PerturbationResult]) -> Dict[str, float]:
    """Fisher exact on detected-vs-not against real-vs-null.

    This is the test that answers 'does the arm detect change, or does it just
    always say something changed?'
    """
    real = [r for r in results if not r.is_null]
    null = [r for r in results if r.is_null]
    table = [[sum(r.agent_reported_change for r in real),
              sum(not r.agent_reported_change for r in real)],
             [sum(r.agent_reported_change for r in null),
              sum(not r.agent_reported_change for r in null)]]
    odds, p = stats.fisher_exact(table)
    return {"odds_ratio": float(odds), "p_value": float(p), "table": table}


# --------------------------------------------------------------------------
# 3. Seed stability at fixed substrate
# --------------------------------------------------------------------------
def seed_stability(rankings: Sequence[Sequence[str]],
                   top_k: int = 10) -> Dict[str, float]:
    """Pairwise Kendall tau and top-k Jaccard across repeat runs."""
    taus, jaccs = [], []
    for i in range(len(rankings)):
        for j in range(i + 1, len(rankings)):
            a, b = list(rankings[i]), list(rankings[j])
            shared = [e for e in a if e in set(b)]
            if len(shared) >= 3:
                ra = [a.index(e) for e in shared]
                rb = [b.index(e) for e in shared]
                t, _ = stats.kendalltau(ra, rb)
                if not np.isnan(t):
                    taus.append(t)
            sa, sb = set(a[:top_k]), set(b[:top_k])
            if sa | sb:
                jaccs.append(len(sa & sb) / len(sa | sb))
    return {
        "kendall_tau_mean": float(np.mean(taus)) if taus else float("nan"),
        "kendall_tau_min": float(np.min(taus)) if taus else float("nan"),
        f"top{top_k}_jaccard_mean": float(np.mean(jaccs)) if jaccs else float("nan"),
        f"top{top_k}_jaccard_min": float(np.min(jaccs)) if jaccs else float("nan"),
        "n_pairs": len(jaccs),
    }


def scalar_exact_match(values: Sequence[Any]) -> Dict[str, Any]:
    """For deterministic scalars (e.g. the overlap count). Any variation here
    is a finding on its own — the true answer cannot change between seeds."""
    c = Counter(values)
    return {"unique_values": dict(c), "all_identical": len(c) == 1,
            "modal": c.most_common(1)[0][0] if c else None}


# --------------------------------------------------------------------------
# 4. Re-walk reproduction
# --------------------------------------------------------------------------
def rewalk_reproduction(attempts: Sequence[Dict[str, Any]],
                        jaccard_threshold: float = 0.9) -> Estimate:
    """attempts: [{'topk_jaccard': float, 'bindings_identical': bool}, ...]

    Both conditions required. Reproducing the list while having used different
    thresholds to get there is not reproduction.
    """
    def stat(xs):
        return sum(
            1.0 for a in xs
            if a["topk_jaccard"] >= jaccard_threshold and a["bindings_identical"]
        ) / len(xs)
    return clustered_bootstrap([[a] for a in attempts], stat)


# --------------------------------------------------------------------------
# 5. Abstention on out-of-framework queries
# --------------------------------------------------------------------------
def abstention(outcomes: Sequence[str]) -> Dict[str, Estimate]:
    """outcomes in {'abstained', 'improvised', 'answered_correctly_in_scope'}"""
    sess = [[o] for o in outcomes]
    return {
        "abstention_rate": clustered_bootstrap(
            sess, lambda xs: sum(o == "abstained" for o in xs) / len(xs)),
        "improvisation_rate": clustered_bootstrap(
            sess, lambda xs: sum(o == "improvised" for o in xs) / len(xs)),
    }


# --------------------------------------------------------------------------
# 6. Judge agreement
# --------------------------------------------------------------------------
def cohens_kappa(a: Sequence[Any], b: Sequence[Any]) -> Dict[str, float]:
    assert len(a) == len(b), "rater vectors must align"
    labels = sorted(set(a) | set(b))
    idx = {l: i for i, l in enumerate(labels)}
    n = len(a)
    m = np.zeros((len(labels), len(labels)))
    for x, y in zip(a, b):
        m[idx[x], idx[y]] += 1
    po = np.trace(m) / n
    pe = float(np.sum(m.sum(axis=0) * m.sum(axis=1))) / (n * n)
    kappa = (po - pe) / (1 - pe) if pe != 1 else float("nan")
    return {"kappa": float(kappa), "observed_agreement": float(po), "n": n}


# --------------------------------------------------------------------------
# Arm comparison
# --------------------------------------------------------------------------
def compare_arms(arm_a: Sequence[Sequence[str]],
                 arm_b: Sequence[Sequence[str]],
                 n_boot: int = 10_000) -> Dict[str, Any]:
    """Paired-by-nothing bootstrap of the OF difference between two arms.

    The A3-vs-A4 comparison is the load-bearing one in the paper. If its
    interval spans zero, the thesis is not supported and that is the result.
    """
    da, db = [list(s) for s in arm_a], [list(s) for s in arm_b]
    obs = _of([o for s in da for o in s]) - _of([o for s in db for o in s])
    draws = []
    for _ in range(n_boot):
        ia = RNG.integers(0, len(da), size=len(da))
        ib = RNG.integers(0, len(db), size=len(db))
        try:
            draws.append(
                _of([o for i in ia for o in da[i]]) -
                _of([o for i in ib for o in db[i]]))
        except ValueError:
            continue
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"of_difference": float(obs), "ci95": [float(lo), float(hi)],
            "excludes_zero": bool(lo > 0 or hi < 0)}
