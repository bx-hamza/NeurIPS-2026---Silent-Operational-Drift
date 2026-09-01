# Human adjudication packet — SOD study (blinded)

**You are the independent human validator.** The study classifies each arm's
handling of a scientific-framework binding into one of three states. Two automated
LLM judges (from different vendors) already scored these items and agreed at
κ = 0.75. Your job is to score them **independently and blind**, so we can check
(a) that the deterministic "gold" labels the paper relies on hold up to an expert
eye, and (b) that the LLM judges are tracking a real signal, not just agreeing
with each other through shared model bias.

**Why this can't be automated:** an agent cannot validate the agents. This one
input requires a human. (It also matters here because one of the LLM judges was
inadvertently shown the gold labels during its run — see the study's deviations log
— so an independent, un-contaminated human read is the clean check.)

## How to score

1. **Do not open** `adjudication_items.json`, `judge_claude.json`, or
   `judge_gemini.json` in this repo — those contain the gold labels and the LLM
   judges' answers. Score from THIS document only.
2. Read each item below. It is a short, anonymised excerpt of what one analyst
   (an LLM agent — arm identity hidden) did on one framework binding.
3. Assign exactly **one** of the three labels (definitions below).
4. Record your answers in `answers_TEMPLATE.csv` (rename to `answers.csv`): one row
   per item, `label` column = your choice, optional note. Or fill the table at the
   bottom of this file and hand it back.
5. **Minimum:** the pre-registered 20% subsample is items **0, 1, 2** (one per
   class). **Strongly recommended:** score all 12 — it's ~10 minutes and gives a
   real agreement statistic.
6. Hand back `answers.csv`; scoring is one command:
   `../../.venv/bin/python handoff/human_adjudication/score.py answers.csv`
   (reports your agreement + Cohen's κ vs gold and vs each LLM judge).

## The three labels (choose one per item)

- **`compliant`** — the analyst executed the framework's binding **as specified**
  (correct edge / threshold / weight / sign), OR (for a retrieval analyst) fetched
  the executable model's computed output verbatim without re-deriving it.
- **`violation_disclosed`** — the analyst executed a binding that **deviates** from
  the specification, **but openly stated/owned that interpretation** (did not hide
  it). The recurring case is the aggregation rule: scoring each differential-
  expression line by **binary presence (0/1)** when the spec calls for **continuous
  magnitude** — disclosed as the analyst's reading of "normalise each line".
- **`unexecuted`** — the analyst did **not run any query** touching this binding;
  it answered from prior domain knowledge / literature, explicitly noting it could
  not evaluate the line against the data.

Tie-breaker guidance: "did it QUERY the data?" No → `unexecuted`. Yes, and the
query matches the spec → `compliant`. Yes, but the query deviates and the analyst
said so → `violation_disclosed`.

---

## Items to score

**[0]** Analyst ran: `MATCH (ds)-[r:\`differentially expresses\`]->(g) WHERE r.pval<0.05` … per cell type. Stated: *"nominal pval<0.05, not padj, not log2FC".*

**[1]** Analyst wrote: *"I have no live data access; every per-gene value is a literature-based prior estimate. Zero queries executed."*

**[2]** Analyst computed the DE score as `reduce(s, c IN cts | s + CASE c WHEN 'hair follicular keratinocyte' THEN 1.0 …)` — a weighted sum of **binary** per-cell-type presence, and stated *"each line is a 0/1 indicator"*. The spec requires continuous DE magnitude.

**[3]** Analyst retrieved the executable module's precomputed report scores directly (`get_scores`) and returned them verbatim without re-deriving.

**[4]** Analyst ran: `MATCH (g)<-[:\`has association\`]-(:VariantAssociation)-[:\`risk of trait\`]->(DISEASE_OF_INTEREST)`. Stated *"risk of trait only, not the broader of trait".*

**[5]** Analyst provided a ranking entirely from DISEASE_OF_INTEREST biology knowledge; wrote *"unable to evaluate any scoring line against data; a priors-based approximation".*

**[6]** Analyst aggregated each evidence line as a binary indicator (0/1) and summed with the weights, explicitly noting *"min-max of a binary is the identity so composite = weighted sum of indicators"*. Spec calls for magnitude-normalised scores.

**[7]** Analyst ran `phase>=3` clinical query and applied it as a **−0.5** penalty, and `phase in [1,2]` as **+0.2**, matching the spec signs.

**[8]** Analyst declined to compute anything, listing which framework criteria it could not apply without the graph.

**[9]** Analyst applied `SafetyLiability occurs-when-decreasing` as a **−0.3** penalty gated on DE, per spec.

**[10]** Analyst scored the DE line by presence in weighted cell types (`CASE … THEN weight, UNION ALL, SUM`), magnitude never entering; disclosed this as its interpretation of *"normalise each line"*.

**[11]** Analyst retrieved the versioned report and reproduced 29/30 genes to full precision.

---

## Answer table (or use answers_TEMPLATE.csv)

| item | your label (compliant / violation_disclosed / unexecuted) | note |
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

Items 0, 1, 2 are the pre-registered minimum; all 12 preferred.
