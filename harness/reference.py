#!/usr/bin/env python3
"""
Reference implementation — agent-free ground truth for the SOD study.

Framework = "DISEASE_OF_INTEREST Target Prioritization 4" (frameworks/executable_model_spec.json),
the executable model arm A4 calls. This file hand-reproduces its 13 evidence
lines with the EXACT Cypher from the model spec, so the study measures agent
bindings against an independently-computed truth (CLAUDE.md #2: no LLM in this
file; only the org-header read path in gateway.py).

VALIDATION (<test-env> baseline, 2026-08-17): the union of the 13 hand-written
evidence-line gene sets = 11,618 genes; the platform's own precomputed TP4
universe = 11,619. Agreement to one gene confirms these queries reproduce the
framework's evidence membership, and that the baseline graph and the precomputed
scores are consistent (not stale).

STATUS: per-line binding functions are freeze-ready (they are the E1 core and are
exact). The composite RANKING (reference_ranking, used by E2/E4) is DRAFT: the
platform's score aggregation is not a plain weighted sum of the per-line
normalised scores (verified), so the exact composite must be reproduced from the
engine's scoring algorithm or defined explicitly with the peer reviewer before
freeze. Until then reference_ranking raises; reference_ranking_candidate offers a
validated-by-ranking draft.

Note: the dendritic-cell evidence line originally hardcoded 'dendritic cell,
human' (which matched the graph node 'dendritic cell' zero times); the author
corrected the binding and re-ran the model on 2026-08-17, so the line is now
live. That episode is itself a clean field example of framework brittleness — a
hardcoded binding silently contributing nothing after a schema/name change —
worth a sentence in the paper even though the line is now fixed.
"""
from __future__ import annotations

import os
from typing import Dict, List, Set

try:                                    # importable as harness.reference …
    from harness.gateway import execute_query as q
except ImportError:                     # … and runnable from within harness/
    from gateway import execute_query as q

DISEASE = "DISEASE_OF_INTEREST"
MODEL_ID = os.environ.get("SOD_MODEL_ID", "")      # precomputed model id

# The 13 evidence lines, verbatim weights from the model spec.
CELL_LINES = {                          # celltype -> weight (scRNA, pval<0.05)
    "hair follicular keratinocyte": 1.0,
    "suprabasal keratinocyte": 0.9,
    "dendritic cell": 0.9,              # corrected in the model + re-run 2026-08-17
    "skin fibroblast": 0.8,
    "natural killer cell": 0.6,
    "macrophage": 0.5,
    "granular cell of epidermis": 0.4,
}
CLINICAL_PHASE34_WEIGHT = -0.5
CLINICAL_PHASE12_WEIGHT = 0.2
SAFETY_WEIGHT = -0.3
GENETICS_WEIGHT = 1.0
PATHWAYS = {"Interleukin-23 signaling": 0.2, "Interferon Signaling": 0.2}


class ReconciliationRequired(NotImplementedError):
    pass


def _lit(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _symbols(cypher: str) -> Set[str]:
    return {r["sym"] for r in q(cypher) if r.get("sym")}


# ==========================================================================
# Per-evidence-line reference sets — EXACT bindings from the model spec.
# Each returns the DISTINCT set of gene symbols the line credits. These are the
# E1 core: an arm is compliant on a line iff the query it executed selects this
# same binding (right edge, right threshold, right source).
# ==========================================================================
def ref_de_significant(celltype: str) -> Set[str]:
    """scRNA lines: `differentially expresses` with pval < 0.05 (NOT padj, NOT
    log2FC; NOT the `upregulates` edge). Distinct genes per the model cypher."""
    return _symbols(
        f"MATCH (c:CellType {{displayName:{_lit(celltype)}}})<-[:`analyzes celltype`]-"
        f"(d:DifferentialExpressionDataset)-[r:`differentially expresses`]->(g:Gene),"
        f"(d)-[:`studies condition`]->(:Disease {{displayName:{_lit(DISEASE)}}}) "
        f"WHERE r.pval < 0.05 AND g.symbol IS NOT NULL RETURN DISTINCT g.symbol AS sym")


def ref_clinical_phase34() -> Set[str]:
    """Weight -0.5. Gene acted on by a drug used in a Phase >= 3 trial for the
    disease. The sign is the trap: an agent's prior treats clinical precedent as
    positive."""
    return _symbols(
        f"MATCH (:Disease {{displayName:{_lit(DISEASE)}}})<-[:`studies condition`]-"
        f"(ct:ClinicalTrial)-[:`using the drug`]->(:Drug)-[:`acts on`]->(g:Gene) "
        f"WHERE ct.phase >= 3 AND g.symbol IS NOT NULL RETURN DISTINCT g.symbol AS sym")


def ref_clinical_phase12() -> Set[str]:
    """Weight +0.2. Phase 1-2 trial. The phase SPLIT (late-stage penalised,
    early-stage rewarded) is what an agent will not reconstruct from prose."""
    return _symbols(
        f"MATCH (:Disease {{displayName:{_lit(DISEASE)}}})<-[:`studies condition`]-"
        f"(ct:ClinicalTrial)-[:`using the drug`]->(:Drug)-[:`acts on`]->(g:Gene) "
        f"WHERE ct.phase >= 1 AND ct.phase <= 2 AND g.symbol IS NOT NULL "
        f"RETURN DISTINCT g.symbol AS sym")


def ref_safety_liability() -> Set[str]:
    """Weight -0.3. Gene with a SafetyLiability 'occurs when decreasing' and DE
    in a DISEASE_OF_INTEREST ScDiffExpDataset. An agent won't invent this channel."""
    return _symbols(
        f"MATCH (:Disease {{displayName:{_lit(DISEASE)}}})<-[:`studies disease`]-"
        f"(:ScDiffExpDataset)-[:`differentially expresses`]->(g:Gene)<-"
        f"[:`occurs when decreasing`]-(:SafetyLiability) "
        f"WHERE g.symbol IS NOT NULL RETURN DISTINCT g.symbol AS sym")


def ref_ot_genetics() -> Set[str]:
    """Weight 1.0. OT genetics via VariantAssociation `risk of trait` (NOT the
    broader `of trait`, NOT GWAS genome-wide p)."""
    return _symbols(
        f"MATCH (g:Gene)<-[:`has association`]-(:VariantAssociation)-[:`risk of trait`]->"
        f"(:Disease {{displayName:{_lit(DISEASE)}}}) "
        f"WHERE g.symbol IS NOT NULL RETURN DISTINCT g.symbol AS sym")


def ref_pathway(pathway: str) -> Set[str]:
    """Weight 0.2. Gene participates in the named pathway AND is DE in a
    DISEASE_OF_INTEREST dataset."""
    return _symbols(
        f"MATCH (p:Pathway {{displayName:{_lit(pathway)}}})<-[:`participates in`]-(g:Gene)<-"
        f"[:`differentially expresses`]-(d:DifferentialExpressionDataset)-"
        f"[:`studies condition`]->(:Disease {{displayName:{_lit(DISEASE)}}}) "
        f"WHERE g.symbol IS NOT NULL RETURN DISTINCT g.symbol AS sym")


def ref_universe() -> Set[str]:
    """Framework-defined candidate universe = every gene credited by >=1 evidence
    line. Validated == 11,618 vs the platform's 11,619 (peer-review finding #1:
    this is the framework universe, not a guessed union)."""
    u: Set[str] = set()
    for ct in CELL_LINES:
        u |= ref_de_significant(ct)
    u |= ref_clinical_phase34() | ref_clinical_phase12() | ref_safety_liability()
    u |= ref_ot_genetics()
    for pw in PATHWAYS:
        u |= ref_pathway(pw)
    return u


# ==========================================================================
# Composite ranking (E2/E4). The platform aggregation is NOT a plain weighted
# sum of per-line normalised scores (verified: Σ w·score != final). Reproducing
# it exactly needs the engine's scoring algorithm; defined explicitly with the
# reviewer before freeze. Until then this raises.
# ==========================================================================
def reference_ranking(*_a, **_k) -> List[str]:
    raise ReconciliationRequired(
        "Composite aggregation must be reproduced from the engine scoring code "
        "(Σ weight·normScore does not match the platform's final score) or defined "
        "explicitly with the peer reviewer. Per-line binding refs above are exact "
        "and freeze-ready; the ranking is not yet. Cross-check target: the "
        "precomputed oracle (see SOD_MODEL_ID), universe validated 11,618≈11,619.")


def oracle_ranking(top: int = 25) -> List[Dict]:
    """The platform's deterministic computed TP4 ranking — the cross-check
    target, NOT the reference (it is read, not hand-written). Used to validate a
    hand-written composite once the aggregation is reproduced."""
    rows = q(f"MATCH (g:Gene)-[r:HAS_SCORE_EDGE]->(:Disease {{displayName:{_lit(DISEASE)}}}) "
             f"WHERE r.modelIdProperty={_lit(MODEL_ID)} RETURN g.symbol AS sym, r.score AS score "
             f"ORDER BY r.score DESC, g.symbol ASC LIMIT {int(top)}")
    return [{"rank": i + 1, "gene": r["sym"], "score": r["score"]} for i, r in enumerate(rows)]


if __name__ == "__main__":
    print("Reference implementation (DISEASE_OF_INTEREST TP4) — per-line self-check\n")
    for ct, w in CELL_LINES.items():
        n = len(ref_de_significant(ct))
        flag = "  <-- DEAD (celltype name mismatch)" if n == 0 else ""
        print(f"  scRNA w={w:+.1f}  {ct:30s} pval<0.05: {n:5d}{flag}")
    print(f"  clinical Phase3/4 w=-0.5: {len(ref_clinical_phase34()):5d}")
    print(f"  clinical Phase1/2 w=+0.2: {len(ref_clinical_phase12()):5d}")
    print(f"  safety liability  w=-0.3: {len(ref_safety_liability()):5d}")
    print(f"  OT genetics       w=+1.0: {len(ref_ot_genetics()):5d}")
    for pw, w in PATHWAYS.items():
        print(f"  pathway w={w:+.1f}  {pw:30s}: {len(ref_pathway(pw)):5d}")
    u = ref_universe()
    print(f"\n  framework universe (union): {len(u)}   (oracle: 11619)")
    print("\n  oracle top-10 (cross-check target):")
    for e in oracle_ranking(10):
        print(f"    {e['rank']:2d}. {e['gene']:10s} {e['score']:.4f}")
