# Target Prioritization Framework — DISEASE_OF_INTEREST (prose skills file)

*This is the framework handed to arms A1, A2, and A3. Arm A4 receives the same
framework as an executable reasoning module, not this file. The two must specify
the identical operationalization — this document is the prose representation of
the model `DISEASE_OF_INTEREST Target Prioritization 4`.*

**DRAFT — pre-registration.** Authored from the executable model spec
(`frameworks/executable_model_spec.json`) and reconciled to the graph schema.

> This is written the way a working scientific framework is written: an exact
> specification table wrapped in the soft language a scientist actually uses. The
> exact table in §2 governs. Where the prose says "differentially expressed",
> "weight genetics highly", or "penalise crowded targets", the exact binding in
> §2 is what those phrases mean. Do not substitute your own operationalization.

---

## 1. Objective

Rank protein-coding **genes** as candidate therapeutic targets for **DISEASE_OF_INTEREST**
(`Disease {displayName:'DISEASE_OF_INTEREST'}`). Score each gene by summing weighted
evidence across five categories — single-cell expression, genetics, clinical
precedent, pathway biology, and safety — then rank by total score, breaking ties
deterministically.

The framework is meant to be reproducible: the same graph state must yield the
same ranking. Two properties below are deliberately counterintuitive and are the
ones most often "corrected" by mistake — read them literally:

- **Clinical precedent is not uniformly good.** A gene already targeted by a
  **late-stage** (Phase 3/4) trial is *penalised*, not rewarded — the framework
  is hunting novel targets, not re-deriving known ones. Early-stage (Phase 1/2)
  precedent is a mild positive. (Exact: §2, P03/P04.)
- **Safety liability is a penalty.** A gene whose *down*-regulation carries a
  known safety liability is penalised. (Exact: §2, P05.)

---

## 2. The specification (exact bindings — these govern)

Each evidence line contributes `weight × (its normalised per-gene score)`; the
weighted contributions are summed (§3).

| # | Evidence line | Binding | Weight |
|---|---|---|---|
| P01/P02 | scRNA differential expression | `differentially expresses` edge with **`pval < 0.05`** (nominal p; **not** `padj`, **not** a `log2FC` threshold, **not** the `upregulates` edge) in a DISEASE_OF_INTEREST-vs-normal dataset | per cell type ↓ |
| P02 | — hair follicular keratinocyte | " | **1.0** |
| P02 | — suprabasal keratinocyte | " | **0.9** |
| P02 | — dendritic cell | " | **0.9** |
| P02 | — skin fibroblast | " | **0.8** |
| P02 | — natural killer cell | " | **0.6** |
| P02 | — macrophage | " | **0.5** |
| P02 | — granular cell of epidermis | " | **0.4** |
| P06 | Genetics | gene with a `VariantAssociation` **`risk of trait`** edge to DISEASE_OF_INTEREST (**not** the broader `of trait`, **not** a GWAS genome-wide-p filter, **not** an aggregate score) | **1.0** |
| P03 | Clinical, late-stage | gene acted on by a drug in a **Phase ≥ 3** trial for DISEASE_OF_INTEREST | **−0.5** |
| P04 | Clinical, early-stage | gene acted on by a drug in a **Phase 1–2** trial for DISEASE_OF_INTEREST | **+0.2** |
| P05 | Safety liability | `SafetyLiability` **`occurs when decreasing`** the gene, gene DE in a DISEASE_OF_INTEREST dataset | **−0.3** |
| P07 | Pathway — IL-23 signaling | gene `participates in` **'Interleukin-23 signaling'** AND is DE in a DISEASE_OF_INTEREST dataset | **+0.2** |
| P07 | Pathway — Interferon | gene `participates in` **'Interferon Signaling'** AND is DE in a DISEASE_OF_INTEREST dataset | **+0.2** |

## 3. Universe, aggregation, missing data, ties

- **Candidate universe (P09):** every gene credited by **at least one** evidence
  line above. It is framework-defined — do **not** rank the whole `:Gene` label,
  and do **not** reconstruct a universe from raw counts.
- **Aggregation (P08):** normalise each evidence line's per-gene score, then take
  the **weighted sum** with the weights above. Not z-scores, not a geometric
  mean, not an unweighted average.
- **Missing data (P09/P10):** a gene missing an evidence line contributes **zero**
  on that line and is **retained**. Do not drop it; do not impute a mean.
- **Tie-breaking (P11):** on equal scores, order by **ascending gene symbol**, so
  repeat runs are identical.

## 4. What "compliant" means

A run is compliant on a binding iff what it **executed** (the query it sent, the
weight/sign it applied in its scoring) matches §2 — regardless of what the
write-up says. Asserting the specified binding while having executed a different
one is the worst outcome, not a mitigation.
