#!/usr/bin/env python3
"""
E2 reference composite — the agent-free ground truth for the perturbation study.

The platform's TP4 composite is NOT reproducible (Σ w·score != final; the formula
lives in the workflow, not readable engine code — RECONCILIATION.md). So
E2 does NOT try to reproduce the platform ranking. Instead it uses a DETERMINISTIC,
exactly-reproducible reference built from the FROZEN per-line evidence functions in
reference.py (untouched here): each evidence line credits a gene its spec weight iff
the gene is in that line's set, and the composite is the weighted sum. This is the
binary-presence reading — chosen because it is exactly reproducible and its DELTA
under a perturbation is exactly computable, which is all E2 needs. E2 measures
whether an arm's answer reflects the evidence DELTA a substrate edit produces,
scored against this reference — not absolute agreement with the platform ranking.

CLAUDE.md #2 holds: no LLM in this path; only reference.py's per-line Cypher.
Determinism is asserted at import-adjacent call sites (compute twice, compare).
"""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Dict, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.reference import (  # noqa: E402  (frozen per-line refs + weights)
    CELL_LINES, CLINICAL_PHASE34_WEIGHT, CLINICAL_PHASE12_WEIGHT,
    SAFETY_WEIGHT, GENETICS_WEIGHT, PATHWAYS,
    ref_de_significant, ref_clinical_phase34, ref_clinical_phase12,
    ref_safety_liability, ref_ot_genetics, ref_pathway,
)


def evidence_sets() -> Dict[str, Set[str]]:
    """Every framework line -> the set of gene symbols it credits. One live read
    per line; deterministic given the graph state."""
    sets: Dict[str, Set[str]] = {}
    for ct in CELL_LINES:
        sets[f"scRNA:{ct}"] = ref_de_significant(ct)
    sets["clinical_phase34"] = ref_clinical_phase34()
    sets["clinical_phase12"] = ref_clinical_phase12()
    sets["safety_liability"] = ref_safety_liability()
    sets["genetics"] = ref_ot_genetics()
    for pw in PATHWAYS:
        sets[f"pathway:{pw}"] = ref_pathway(pw)
    return sets


LINE_WEIGHT: Dict[str, float] = {
    **{f"scRNA:{ct}": w for ct, w in CELL_LINES.items()},
    "clinical_phase34": CLINICAL_PHASE34_WEIGHT,
    "clinical_phase12": CLINICAL_PHASE12_WEIGHT,
    "safety_liability": SAFETY_WEIGHT,
    "genetics": GENETICS_WEIGHT,
    **{f"pathway:{pw}": PATHWAYS[pw] for pw in PATHWAYS},
}


def scores(sets: Dict[str, Set[str]] = None) -> Dict[str, float]:
    """Per-gene composite score = Σ weight·(gene in line). Deterministic."""
    sets = sets if sets is not None else evidence_sets()
    out: Dict[str, float] = {}
    for line, genes in sets.items():
        w = LINE_WEIGHT[line]
        for g in genes:
            out[g] = out.get(g, 0.0) + w
    return out


def composite_ranking(sets: Dict[str, Set[str]] = None, top: int = None) -> List[str]:
    """Deterministic ranking: score desc, then gene symbol ascending (P11 tie-break)."""
    sc = scores(sets)
    ranked = sorted(sc.keys(), key=lambda g: (-sc[g], g))
    return ranked[:top] if top else ranked


def credited_lines(gene: str, sets: Dict[str, Set[str]] = None) -> List[Tuple[str, float]]:
    """Which lines credit this gene, with weights — for evidence-level delta scoring."""
    sets = sets if sets is not None else evidence_sets()
    return [(line, LINE_WEIGHT[line]) for line, genes in sets.items() if gene in genes]


if __name__ == "__main__":
    # Determinism + shape self-check (no mutation).
    s1 = evidence_sets()
    r1 = composite_ranking(s1)
    s2 = evidence_sets()
    r2 = composite_ranking(s2)
    print("universe:", len(r1), "| deterministic:", r1 == r2)
    sc = scores(s1)
    print("top-15 (score):")
    for g in r1[:15]:
        print(f"  {g:12s} {sc[g]:+.2f}  {[l for l, _ in credited_lines(g, s1)]}")
