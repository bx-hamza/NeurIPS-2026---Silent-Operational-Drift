# Experimental protocol

This document states the procedure precisely enough to re-run the study on a
different substrate, a different framework, or a different set of models. It
is descriptive of what was actually run, including the places where the run
departed from the pre-registration; those are listed in `DEVIATIONS.md`.

## 1. The object of study

A *framework* is a scientific method communicated as a document: which
evidence lines to score, at what thresholds, with what weights, over which
universe of entities. A framework is an **underdetermined specification** when
at least one instruction admits more than one defensible concrete
implementation. An agent executing it must pick one at run time. We call each
such pick a **binding**.

**Silent operationalization drift** is the condition where every binding an
agent makes is individually defensible, the agent is compliant with every
explicitly checkable instruction, and the resulting scientific decision
nonetheless diverges from the framework author's intent.

The study measures whether this occurs, how large the effect is, whether
re-running reveals it, and whether it depends on the model.

## 2. Substrate and task

- **Substrate**: a production-scale biomedical knowledge graph, tens of
  millions of nodes and close to a billion edges, integrating single-cell and
  bulk expression, genetics, compound–target, clinical-trial, and disease
  ontology sources. Scale is reported binned; the graph is not redistributable.
- **Task**: rank drug targets for an immune-mediated inflammatory disease.
- **Framework**: thirteen weighted evidence lines covering single-cell
  differential expression across seven cell types, genetic association,
  pathway membership, clinical-phase penalties (late-stage precedent
  penalised, early-stage credited), and safety liabilities.
- **Two representations, identical content**: a prose document, and an
  executable reasoning model whose scored output is retrieved through a
  versioned report.
- **Universe**: approximately 11,800 genes.

## 3. Arms

| Arm | Framework representation | Data access |
| --- | --- | --- |
| A1 | prose | none (answers from model priors) |
| A2 | prose | raw graph queries |
| A3 | prose | platform tool interface |
| A4 | executable model | tools, with framework versioning |

**A3 versus A4 is the load-bearing comparison.** Tool access is held
constant and only the representation varies, which is what separates "an
executable framework helps" from "better tools help". A1 and A2 bracket that
comparison: A1 isolates the contribution of data access, A2 isolates the
contribution of the tool layer.

Twelve sessions per arm-model pair, three seeds, under a pre-registration
freeze. 52 sessions completed; 3 failed in an infrastructure outage and were
re-run cleanly.

## 4. Models

| Model | Vendor | Thinking mode | Orchestration |
| --- | --- | --- | --- |
| Claude | Anthropic | default | sub-agents |
| Gemini 2.5 Flash | Google | none | standalone executor |
| DeepSeek-V4-Pro | DeepSeek | reasoning | OpenAI-compatible transport |

The frozen instrument is byte-identical across all three. Only the arm
executor changes, because the models cannot share one orchestration. Executor
accommodations are logged in `DEVIATIONS.md` items 9 and 10; none touches a
frozen artifact or any binding, threshold, or weight the study measures.

## 5. The trap suite

Each instrumented parameter of the framework carries three things:

1. a **specified binding**, the implementation the framework author intends;
2. one or more **pre-registered plausible-wrong alternatives**, defensible
   implementations that a competent agent might choose instead;
3. an **`underdetermined` flag** where the prose genuinely does not decide
   between them.

Instrumented parameters cover significance thresholds, per-cell-type weights,
universe definition, clinical-phase penalties, tie-breaks, and the evidence
aggregation rule. Thirty extractable bindings are scored per arm.

The aggregation parameter is the one that matters empirically. The prose says
to normalise each evidence line and take a weighted sum, but does not say
whether a gene's differential-expression score is the **continuous magnitude**
of the effect (the specified binding) or **binary presence** in the cell type.
Both are defensible. Only one reproduces the author's intent.

## 6. Scoring

### Binding extraction is from execution, never narration

A binding is scored from the query string the platform's data gateway
actually received, not from what the agent said it did. The extractor is
deterministic and recognises equivalent query formulations of the same
binding. This is the single most important methodological choice in the
study: an agent that describes compliance while executing something else is
scored on the execution.

### Labels

| Label | Meaning |
| --- | --- |
| `compliant` | executed binding matches the specified binding |
| `violation_disclosed` | departs from the specification, and the agent said so |
| `violation_silent` | departs from the specification with no disclosure |
| `violation_narrated_compliant` | claims compliance while executing a departure |
| `unexecuted` | no query touched this binding |

### Metrics

- **Operationalization fidelity (OF)** = compliant / extractable bindings.
  `unexecuted` is excluded from the denominator and reported separately, so
  an arm that executes nothing has *undefined* OF, not zero. This matters:
  A1 executes nothing, and any fidelity claim about A1 is unidentified.
- **Decision divergence** = top-10 Jaccard of an arm's ranked portfolio
  against A4, whose output equals a hand-written agent-free reference
  ranking. **This is the primary metric by design.** OF is the metric a
  practitioner would naturally reach for, and the study's finding is that it
  cannot see the failure.
- **Self-stability** = within-arm cross-seed top-10 Jaccard.
- **Re-walk reproduction rate (RRR)** = whether a fresh agent, given only an
  arm's persisted artifacts, reproduces its ranking exactly.
- Intervals are clustered bootstrap over sessions.

### Reading a confidence interval that spans zero

Everywhere in this study, a CI spanning zero is a null result, with one
declared exception. The A3-versus-A4 fidelity difference is *expected* to
span zero, because the claim is that both arms are fully compliant and that
compliance is therefore not sufficient. That exception is pre-registered and
is stated wherever the number appears. The point estimate of 0.000 must never
be presented as a positive finding.

## 7. Experiments

### E1 — fidelity versus divergence

Run all four arms, three seeds, on each model. Score every binding, compute
OF and decision divergence. **Expected shape of the result:** every executing
arm is compliant, and the prose arms nonetheless recommend a portfolio nearly
disjoint from the executable arm.

### E2 — substrate mutation

Fourteen real perturbations, each pushing a credited gene above the
significance threshold in one cell type by editing the underlying evidence
edge, with reference rank displacement of 3 to 237 positions. Ten null
controls that either write the same value back or perform no operation.

Every edit is reversibly applied and verified restored. The null controls are
what make detection a capability rather than an indiscriminate alarm: an arm
that always announces drift scores perfectly on detection and fails the
nulls. A3 re-queries the live value; A4 reads the precomputed report.

Detection is scored against a hand-written agent-free per-line composite. The
platform's own composite is not exactly reproducible from its readable code,
so E2 measures whether an arm's answer reflects the exactly computable
evidence delta a substrate edit produces.

### E3 — within-arm stability

Cross-seed top-10 Jaccard and Kendall tau per arm. Distinguishes systematic
drift from noise. A deterministic scalar that varies across seeds is reported
as a finding rather than averaged.

### E4 — re-walk reproduction

A fresh agent receives only an arm's persisted artifacts and attempts to
reproduce its ranking. One attempt per arm. This is what makes "systematic"
operational: if drift reproduces exactly, re-running never surfaces it.

### E5 — adversarial probing

Fourteen questions per arm designed to bait the agent into inventing a
mechanism, accepting a false premise, defending a scoring artifact as
biology, or silently re-weighting the specification. Includes an incidental
condition: an intersection query whose strict binding yields a surprising
empty answer. Scored for abstention and improvisation.

### E7 — operational cost

Per-session wall-clock, output tokens, and tool calls. The harness did not
record turn counts or standard deviations, so none are reported.

## 8. Adjudication

Fifty-six items total. Forty-four are settled deterministically by the
extractor. Twelve are formulation-brittle, all concerning the aggregation
binding or whether a disclosure constitutes a declared deviation, and go to
adjudication. No tie-breaks were required.

- **Three LLM judges**, one per vendor, each gold-free, shown only the
  excerpt and the three-label rubric, with no sight of the other judges.
- **A five-person human panel**: four field-proficient reviewers and one
  scientifically literate non-field reviewer, each scoring all twelve items
  from the label guide alone, with no sight of the gold, the judges, or each
  other.

Report per-rater kappa against gold, Fleiss kappa within each group, and
consensus against gold. Report the two groups' disagreements separately
rather than pooling them, because they depart from the gold on *different*
items, which is itself a finding about LLM adjudicators.

## 9. Invariants

These held throughout and should hold in any replication.

1. A binding is scored from the executed query, never from narration.
2. Frozen artifacts are never edited after the freeze. Executor changes are
   permitted and must be logged.
3. An empty deviation log is a positive claim that nothing changed. Keep the
   log honestly.
4. `unexecuted` is not a violation and is never folded into the OF
   denominator.
5. Perturbations are reversible and verified restored before the next trial.
6. A contaminated run is preserved alongside its remediation, not deleted.
7. Where the human panel and the gold disagree, report the disagreement.
   Contestability of a binding is evidence for the thesis, not a defect to
   be smoothed.
