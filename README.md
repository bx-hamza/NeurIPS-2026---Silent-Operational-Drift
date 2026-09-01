# Silent Operationalization Drift — measurement instrument and results

Artifact for the paper *Silent Operationalization Drift: Prose Scientific
Frameworks are Underdetermined Specifications for Agentic Drug Discovery*
(AI4DD workshop, NeurIPS 2026).

The paper's claim is that an LLM agent executing a prose scientific framework
must bind every underdetermined instruction at run time, and that those
bindings can be individually reasonable, openly disclosed, fully compliant on
every checkable instruction, and still invert the scientific conclusion. This
repository contains the instrument used to measure that, and the scored
results behind every number in the paper.

## What is here

| Path | Contents |
| --- | --- |
| `docs/PROTOCOL.md` | The experimental procedure end to end: arms, metrics, scoring rules, and how each experiment was run. |
| `docs/PREREGISTRATION.md` | The freeze: what was pre-registered, the tag and hash that commit to it, how the authors can demonstrate it, and what a reader of this anonymised copy cannot check without the private history. |
| `docs/DEVIATIONS.md` | All 13 deviations from the pre-registration, including the judge-contamination incident and its remediation. |
| `data/HANDOFF.json` | Canonical scored results. Every number in the paper resolves to a field in this file. |
| `analysis/` | Per-experiment analysis outputs (E1 per vendor, E2, adjudication panels). |
| `adjudication/` | Blinded judge runs from three vendors, the human panel protocol, the label guide, blinded items, and anonymised per-rater answers. See `adjudication/README.md`. |
| `figures/` | Figure generation scripts. Regenerate both paper figures from `data/HANDOFF.json` alone. |
| `traps/` | The trap suite: twelve instrumented parameters, each with its specified binding and pre-registered plausible-wrong alternatives. |
| `perturbations/` | The E2 perturbation and null-control design. |
| `harness/` | Binding extractor and classifier, metrics, perturbation engine, handoff validator, capability probe, smoke tests. See `harness/README.md` for what is present and what is still to be added. |
| `verify_numbers.py` | Re-checks every numeric claim in the paper against `data/HANDOFF.json`. |
| `audit_staleness.py` | Checks the committed analysis files are current: all three judges present, none scored against the contaminated run, and no drift from the frozen numbers. |

Two release-engineering scripts are deliberately absent: each contains the
original terms it exists to remove or detect, so committing them would undo
the anonymisation. See `harness/README.md`.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # numpy, scipy, pyyaml, matplotlib

python verify_numbers.py            # revalidate the paper's numbers
python figures/make_figure1.py      # E1 fidelity vs. divergence
python figures/make_figure2.py      # per-seed binding coin-flip
python audit_staleness.py           # analysis files current -> OK
python harness/tests_smoke.py       # instrument unit tests -> SMOKE OK
python adjudication/human_panel/score_panel.py   # regenerate panel reliability
```

To regenerate the specialists-only sensitivity check, pass the specialist
raters and an explicit output path:

```bash
python adjudication/human_panel/score_panel.py \
    adjudication/human_panel/answers_p1.csv \
    adjudication/human_panel/answers_p2.csv \
    adjudication/human_panel/answers_p3.csv \
    adjudication/human_panel/answers_p4.csv \
    --out analysis/human_adjudication_panel_specialists.json
```

Everything above runs offline from the committed JSON. Nothing in the
verification or figure path requires access to the knowledge graph, and none
of it needs `requests`, which is only used by the gateway adapters when
running the arms against a live substrate.

If `python harness/tests_smoke.py` raises `ModuleNotFoundError: No module
named 'yaml'`, the requirements are not installed in the active interpreter.
The trap suite and perturbation design are YAML, so `pyyaml` is needed even
for the offline path.

## What is deliberately not here

**The knowledge graph.** The substrate is a third-party production system
that we neither own nor can redistribute. What is released instead is the set
of queries issued against it, the bindings extracted from those queries, and
the agent-free reference composites the arms are scored against. Graph scale
is reported in binned form. Re-running the agent arms therefore requires your
own substrate; re-running the scoring, the analysis, and the figures does not.

**Raw agent transcripts.** These carry the disease context and target
identities in the clear. The scored, excerpted adjudication items are
released in their place, which is what the reliability statistics are
computed over.

**The contaminated judge run is included, not omitted.** The first judge run
from the first vendor inadvertently received the gold label. It was re-run
blind, and both runs ship (`adjudication/judge_claude_LEAKED.json` and
`adjudication/judge_claude.json`) so the remediation can be checked rather
than taken on trust. No number in the paper derives from the contaminated
run.

## A note on naming

Some identifiers in this repository are generic stand-ins. The platform's own
graph and API vocabulary was renamed, and the therapeutic area appears as
`DISEASE_OF_INTEREST`. Platform access is restricted, so the original names
would not let anyone run this anyway, and they carry a de-anonymisation risk
under double-blind review.

Nothing about the measured behaviour changed. Query shapes, tool-call
sequences, bindings, thresholds, weights, and every scored result are exactly
what was executed. Gene and cell-type symbols were **not** substituted, so the
biology is fully inspectable. The anonymised-to-actual mapping is held by the
authors and can be supplied to reviewers or an area chair on request.

## Citation

See `CITATION.cff`. The workshop is non-archival; cite the arXiv version if
one is posted.

## Licence

Code under Apache-2.0 (`LICENSE`, with attribution in `NOTICE`). Data and
documentation under CC BY 4.0 (`LICENSE-data`), which also states what the
release does not cover. The copyright holder is given as "The Authors"
while the submission is under double-blind review and will be replaced with
the named authors on acceptance.
