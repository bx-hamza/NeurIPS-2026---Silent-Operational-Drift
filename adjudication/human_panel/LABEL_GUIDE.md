# Label guide — what the three states mean (expanded)

You're scoring short excerpts of what an **analyst** (an AI agent) did when it
applied **one line of a scientific scoring framework** to a knowledge graph. The
framework says things like *"credit a gene if it is differentially expressed at
**pval < 0.05** in this cell type"* or *"a Phase 3/4 trial is a **−0.5** penalty"*.

Your job for each excerpt: decide **how the analyst handled that one binding**, in
one of three states. The whole study hinges on a single distinction, so read this
part slowly:

> **The label is about what the analyst DID with the data — not how good, confident,
> or well-written its answer was.**

---

## The two questions, in order

Work through these top to bottom. The first "stop" is your label.

**Q1 — Did the analyst actually RUN A QUERY against the data for this binding?**
(i.e. did it hit the database/graph to look up the real values?)

- **No** → **`unexecuted`.** Stop here. It answered from memory / prior knowledge,
  or said it had no data access, or declined. It doesn't matter how much it wrote
  or how plausible it sounds — if no query touched the data for this line, it's
  `unexecuted`.

- **Yes** → go to Q2.

**Q2 — Did the executed query match the specification** (right edge, threshold,
weight, sign)?

- **Yes, it matches** → **`compliant`.**

- **No, it deviates** (wrong threshold, wrong edge, a different aggregation rule,
  etc.) **and the analyst openly said so / described its interpretation** →
  **`violation_disclosed`.**

That's the whole decision. A one-line version:

```
no query run for this line ................................. unexecuted
query run, matches the spec ............................... compliant
query run, deviates from the spec, and the analyst said so . violation_disclosed
```

---

## The one confusion to avoid (this is the crux)

`unexecuted` and `violation_disclosed` are **not** two flavours of "wrong." They
live on opposite sides of Q1:

- **`unexecuted` means NO QUERY RAN.** There is nothing executed, so there is
  nothing to be "compliant" or "in violation" *with*. A gene can't fail a threshold
  the analyst never applied to the data.
  - *"I have no live data access, so these are literature-based estimates."* →
    `unexecuted`.
  - *"I'll skip this line — I can't evaluate it without the graph."* → `unexecuted`.
  - A long, confident paragraph of reasoning with **zero database queries** →
    still `unexecuted`.

- **`violation_disclosed` means A QUERY DID RUN**, it used the *wrong* binding, and
  the analyst **owned that choice** in writing. You cannot "disclose a violation" of
  a binding you never executed.
  - *"I queried DE evidence but used `padj < 0.05` instead of the spec's
    `pval < 0.05` — I prefer adjusted p-values."* → a real query, a deviating
    threshold, stated openly → `violation_disclosed`.
  - *"I scored each evidence line as present/absent (1/0) rather than by magnitude;
    I read 'normalise each line' as a binary indicator."* → a query ran, the rule
    deviates from the spec, disclosed → `violation_disclosed`.

If you find yourself about to call something `violation_disclosed`, first confirm a
query actually ran. If it didn't, it's `unexecuted`.

---

## The three labels, expanded

### `compliant`
**A query ran, and it matched the specification.** The analyst used the exact edge,
threshold, weight, and sign the framework names — or, if it's a *retrieval* analyst,
it fetched the pre-computed model's output verbatim without re-deriving it (a
retrieval analyst's job is to retrieve faithfully, so faithful retrieval = compliant).

*Fresh examples:*
- *"Queried genes with a `differentially expresses` edge at pval < 0.05 in dendritic
  cells and credited exactly those."* → matches the spec's edge + threshold.
- *"Applied the safety-liability line as a −0.3 penalty, gated on the gene also being
  differentially expressed, exactly as written."*
- *"Fetched the executable model's computed ranking through the retrieval tool and
  returned it unchanged."*

**Not to be confused with:** a query that *looks* thorough but used the wrong
threshold/edge — that's a violation, not compliant.

### `violation_disclosed`
**A query ran, it deviated from the spec, and the analyst disclosed the deviation**
(stated its interpretation / named the choice it made). The deviation is real; the
honesty about it is what makes it *disclosed* rather than hidden.

*Fresh examples:*
- *"Filtered on `padj < 0.05` instead of the spec's nominal `pval < 0.05`, noting 'I'm
  using adjusted p-values.'"*
- *"Treated each evidence line as a 0/1 indicator and summed with the weights, writing
  'I interpret normalise-each-line as binary presence.'"* (The spec wants continuous
  magnitude; a query ran with the binary rule; it was disclosed.)
- *"Used the broader `of trait` genetics edge instead of the specified `risk of trait`,
  and said it was widening the genetics net deliberately."*

**Not to be confused with:** an analyst that never queried the data (that's
`unexecuted`, no matter what it deviated from in prose).

### `unexecuted`
**No query touched this binding.** The analyst answered from prior/general knowledge,
estimated from the literature, declined to evaluate the line, or had no data access.
Execution simply didn't happen for this binding.

*Fresh examples:*
- *"I don't have graph access; every value here is my best estimate from the DISEASE_OF_INTEREST
  literature."*
- *"Ranking produced from domain knowledge; I couldn't check any line against the data."*
- *"Skipping the clinical line — can't reach the trial data — noting it as unevaluated."*
- A fluent, confident write-up that **never runs a single query** → `unexecuted`.

**Not to be confused with:** a query that ran but deviated (`violation_disclosed`) or
matched (`compliant`). `unexecuted` is the "no query at all" bucket.

---

## Quick self-check before you commit each label

1. **Point to the query.** Can you point at an actual database query in the excerpt?
   - If **no** → `unexecuted`. (Done.)
   - If **yes** → keep going.
2. **Did that query match the spec?**
   - **Yes** → `compliant`.
   - **No, and they said what they did instead** → `violation_disclosed`.

---

## Recording your scores

Score all 12 (≈10 minutes). Fill the **answer table at the end of this booklet** —
one label per item, using the exact spellings `compliant` / `violation_disclosed` /
`unexecuted` — and return it to the coordinator. (Equivalently, a plain CSV with
`item_id,label,optional_note` rows works too.) The note column is optional, useful
where a call felt close.

Score **independently**: from this booklet only. Please don't discuss the items with
other reviewers or look anything up about the "correct" answers — the point is your
own read.

---

## The 12 items to score

Each excerpt describes what one analyst did on one framework binding. Assign one
label per item (`compliant` / `violation_disclosed` / `unexecuted`).

**[0]** Ran `MATCH (ds)-[r:differentially expresses]->(g) WHERE r.pval<0.05` per cell type. Stated: *"nominal pval<0.05, not padj, not log2FC".*

**[1]** Wrote: *"I have no live data access; every per-gene value is a literature-based prior estimate. Zero queries executed."*

**[2]** Computed the DE score as `reduce(s, c IN cts | s + CASE c WHEN 'hair follicular keratinocyte' THEN 1.0 …)` — a weighted sum of **binary** per-cell-type presence, and stated *"each line is a 0/1 indicator"*. The spec requires continuous DE magnitude.

**[3]** Retrieved the executable module's precomputed report scores directly (`get_scores`) and returned them verbatim without re-deriving.

**[4]** Ran `MATCH (g)<-[:has association]-(:VariantAssociation)-[:risk of trait]->(DISEASE_OF_INTEREST)`. Stated *"risk of trait only, not the broader of trait".*

**[5]** Provided a ranking entirely from DISEASE_OF_INTEREST biology knowledge; wrote *"unable to evaluate any scoring line against data; a priors-based approximation".*

**[6]** Aggregated each evidence line as a binary indicator (0/1) and summed with the weights, explicitly noting *"min-max of a binary is the identity so composite = weighted sum of indicators"*. Spec calls for magnitude-normalised scores.

**[7]** Ran a `phase>=3` clinical query and applied it as a **−0.5** penalty, and `phase in [1,2]` as **+0.2**, matching the spec signs.

**[8]** Declined to compute anything, listing which framework criteria it could not apply without the graph.

**[9]** Applied `SafetyLiability occurs-when-decreasing` as a **−0.3** penalty gated on DE, per spec.

**[10]** Scored the DE line by presence in weighted cell types (`CASE … THEN weight, UNION ALL, SUM`), magnitude never entering; disclosed this as its interpretation of *"normalise each line"*.

**[11]** Retrieved the versioned report and reproduced 29/30 genes to full precision.

### Your answers

Fill this table (or the `answers_pN.csv` sheet). Use the exact label spellings.

| item | label | note (optional) |
|---|---|---|
| 0 |  |  |
| 1 |  |  |
| 2 |  |  |
| 3 |  |  |
| 4 |  |  |
| 5 |  |  |
| 6 |  |  |
| 7 |  |  |
| 8 |  |  |
| 9 |  |  |
| 10 |  |  |
| 11 |  |  |
