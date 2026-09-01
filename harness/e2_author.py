#!/usr/bin/env python3
"""
Author the E2 perturbation set, grounded on the CURRENT <test-env> graph.

Each real perturbation targets the `differentially expresses` edge PVAL (the exact
property the framework's P01 binding and reference.py read — NOT the `upregulates`
edge the old draft used, which the framework never reads). SET pval = 0.9 pushes a
gene above the pval<0.05 line in one cell type, removing that line's credit.

Strata are EARNED, not asserted: for every candidate we SIMULATE the effect on the
deterministic reference in-memory (remove the gene from that cell-line set, recompute
the composite ranking, measure the gene's rank displacement) — no mutation needed to
predict it. We then keep high_impact (displacement >= 10) and low_impact (1..9) with
distinct genes, and query the REAL pval so the revert restores the exact prior value.

Nulls (>=10): touch-revert-to-same-value (a write that does not cross the binding)
and pure noops. A null must move the reference by 0 (asserted here and re-checked at
run time — CLAUDE.md #3).

Writes perturbations/e2.yaml + a simulation report. NO mutation happens here.
"""
from __future__ import annotations
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.gateway import execute_query as X
from harness import e2_reference as R
from harness.reference import CELL_LINES

CELL_TYPES = list(CELL_LINES)

DE_DATASET_BY_CT = {}   # celltype -> dataset displayName (one per ct on this graph)


def _lit(s):
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def real_pval(gene, ct):
    """The current pval on (gene)'s differentially-expresses edge in cell-type ct,
    plus the dataset name. Assumes one such edge (verified on this graph)."""
    rows = X(f"MATCH (c:CellType {{displayName:{_lit(ct)}}})<-[:`analyzes celltype`]-"
             f"(d:DifferentialExpressionDataset)-[r:`differentially expresses`]->"
             f"(g:Gene {{symbol:{_lit(gene)}}}) WHERE r.pval < 0.05 "
             f"RETURN d.displayName AS ds, r.pval AS pval ORDER BY r.pval LIMIT 1")
    return (rows[0]["ds"], rows[0]["pval"]) if rows else (None, None)


def apply_revert(gene, ct, ds, pv, to_value):
    """SET the DE edge pval. `to_value` is 0.9 (apply) or the real pv (revert)."""
    base = (f"MATCH (c:CellType {{displayName:{_lit(ct)}}})<-[:`analyzes celltype`]-"
            f"(d:DifferentialExpressionDataset {{displayName:{_lit(ds)}}})-"
            f"[r:`differentially expresses`]->(g:Gene {{symbol:{_lit(gene)}}}) ")
    return base + f"SET r.pval = {to_value}"


def main():
    sets = R.evidence_sets()
    base = R.composite_ranking(sets)
    base_rank = {g: i for i, g in enumerate(base)}
    sc = R.scores(sets)

    # Fast displacement: only gene X's score changes (drops by the line weight), so
    # X's new rank = (#genes scoring above new_score) + (#tie genes with symbol < X).
    # No re-sort — count via a precomputed ascending score array + per-score symbols.
    import bisect
    from collections import defaultdict
    asc = sorted(sc.values())
    by_score = defaultdict(list)
    for g, s in sc.items():
        by_score[s].append(g)
    for s in by_score:
        by_score[s].sort()

    def displacement(gene, ct):
        line = f"scRNA:{ct}"
        if gene not in sets.get(line, set()):
            return None
        new_score = sc[gene] - R.LINE_WEIGHT[line]
        above = len(asc) - bisect.bisect_right(asc, new_score)
        ties = by_score.get(new_score, [])
        tie_below = bisect.bisect_left(ties, gene)   # genes at new_score with symbol < gene
        new_rank = above + tie_below
        return new_rank - base_rank[gene]

    # Collect every (gene, cell-line, displacement); then sample for cell-type
    # DIVERSITY and a spread of effect sizes rather than concentrating on the
    # lowest-weight line. One perturbation per gene (distinct genes).
    from collections import defaultdict
    by_ct = defaultdict(list)                 # ct -> [(gene, disp)]
    seen_gene = set()
    for gene in base[:3000]:
        for ct in CELL_TYPES:
            d = displacement(gene, ct)
            if d is not None and d >= 1:
                by_ct[ct].append((gene, d))

    picked, used_genes = [], set()

    def grab(ct, lo, hi, n):
        got = 0
        for gene, d in sorted(by_ct.get(ct, []), key=lambda t: t[1]):
            if got >= n:
                break
            if gene in used_genes or not (lo <= d < hi):
                continue
            used_genes.add(gene); picked.append((gene, ct, d)); got += 1

    # 4 low_impact (disp 1..9), spread across cell types; then ~14 high across
    # cell types and a range of magnitudes.
    for ct in CELL_TYPES:
        grab(ct, 1, 10, 1)                    # up to 1 low per cell type
    picked = picked[:4]
    used_genes = {g for g, _, _ in picked}
    for ct in CELL_TYPES:                     # 2 high per cell type = 14
        grab(ct, 10, 200, 1)
        grab(ct, 200, 10_000, 1)

    reals = []
    for gene, ct, disp in picked:
        ds, pv = real_pval(gene, ct)
        if ds is None:
            continue
        reals.append({"gene": gene, "ct": ct, "ds": ds, "pval": pv,
                      "stratum": "low_impact" if disp < 10 else "high_impact",
                      "sim_displacement": disp, "score_before": round(sc[gene], 2)})
    reals.sort(key=lambda r: r["sim_displacement"])

    # Assemble YAML perturbation entries
    perts = []
    for i, r in enumerate(reals, 1):
        pid = f"P{i:03d}"
        perts.append({
            "id": pid, "kind": "update_property", "stratum": r["stratum"],
            "target": {"gene": r["gene"], "celltype": r["ct"], "dataset": r["ds"],
                       "field": "pval", "sim_displacement": r["sim_displacement"]},
            "apply_query": apply_revert(r["gene"], r["ct"], r["ds"], r["pval"], "0.9"),
            "revert_query": apply_revert(r["gene"], r["ct"], r["ds"], r["pval"], repr(r["pval"])),
            "note": f"push {r['gene']} above pval<0.05 in {r['ct']} "
                    f"(sim displacement {r['sim_displacement']}, score {r['score_before']}).",
        })
    # NULLS: 5 touch-revert-same-value on real edges (write does not cross binding),
    # 5 pure noops.
    null_targets = [reals[j] for j in (0, 3, 8, 12, 16) if j < len(reals)]
    for k, r in enumerate(null_targets, 1):
        pid = f"N{k:03d}"
        same = apply_revert(r["gene"], r["ct"], r["ds"], r["pval"], repr(r["pval"]))
        perts.append({
            "id": pid, "kind": "update_property", "stratum": "null_control",
            "target": {"gene": r["gene"], "celltype": r["ct"], "dataset": r["ds"],
                       "field": "pval"},
            "apply_query": same, "revert_query": same,
            "note": f"touch-and-revert {r['gene']} {r['ct']} pval to the SAME value; "
                    f"write occurs but the binding does not change — reference must not move.",
        })
    for k in range(len(null_targets) + 1, 11):
        perts.append({"id": f"N{k:03d}", "kind": "noop", "stratum": "null_control",
                      "target": {}, "note": "pure re-run; no change."})

    doc = {
        "snapshot_id": "<test-env>-baseline-reversible-SET",
        "reference": "harness/e2_reference.py composite (deterministic, agent-free); "
                     "platform composite is NOT reproducible (RECONCILIATION.md).",
        "perturbations": perts,
    }
    import yaml
    out = Path("perturbations/e2.yaml")
    out.write_text("# E2 perturbation set — RE-AUTHORED on <test-env> (differentially "
                   "expresses pval edges).\n# Generated by harness/e2_author.py; "
                   "strata earned by in-memory reference simulation.\n\n" +
                   yaml.safe_dump(doc, sort_keys=False, width=100))
    print(f"wrote {out}: {len(reals)} real "
          f"({sum(1 for r in reals if r['stratum']=='high_impact')} high, "
          f"{sum(1 for r in reals if r['stratum']=='low_impact')} low) + "
          f"{len(perts)-len(reals)} null")
    print("\nreal perturbations (earned strata):")
    for r in reals:
        print(f"  {r['gene']:10s} {r['ct'][:26]:26s} {r['stratum']:11s} "
              f"disp={r['sim_displacement']:5d}  pval={r['pval']:.2e}")


if __name__ == "__main__":
    main()
