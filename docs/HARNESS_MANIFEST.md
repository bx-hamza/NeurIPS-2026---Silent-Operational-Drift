# Export manifest — SOD harness instrument code

These are the harness files written/modified during the study run that are **not**
in the public scaffold (which already ships `traps/`, `perturbations/`,
`harness/extract.py`, `harness/metrics.py`, `harness/perturb.py`,
`harness/validate_handoff.py`, root `discover.py`, `tests_smoke.py`). Drop
`export/harness/` into the artifact repo's `harness/` and `export/frameworks/`
into `frameworks/`, preserving structure.

**Scrub policy.** Every credential, endpoint, cluster/namespace/pod name, host,
org/database id, internal object id, and local path was replaced with an
environment-variable read (see *Environment variables*). Public biology (the disease
name, gene/cell-type symbols) is kept as designed inputs and flagged, not edited. A
small set of the platform's API/schema identifiers is *functionally required* by the
code and cannot be removed without breaking it — those are listed under *Residual
internal vocabulary* for a venue-level redaction decision. No raw transcripts,
`.jsonl` traces, or run outputs are included. Regenerate with `python export_harness.py`;
re-audit with the grep under *Verification*.

`harness/` is a **namespace package** (no `__init__.py`), matching the scaffold: put
its parent on `sys.path`.

## Exported files

| File | Purpose (one line) | Experiment | Brief category |
|---|---|---|---|
| `harness/reference.py` | Hand-written agent-free per-parameter reference queries (13 evidence lines + platform oracle read); E1 is scored against these | E1 (+ E2/E4 via composite) | 1 (reference.py) |
| `harness/e2_reference.py` | Deterministic agent-free per-line composite (E2 ground truth); the platform composite is not reproducible so E2 scores the evidence delta | E2 | 2 (e2_reference.py) |
| `harness/gemini_arm.py` | Multi-provider arm executor: Gemini `generateContent` + DeepSeek OpenAI-compatible transport + the tool layer; runs A1–A4 for the Gemini/DeepSeek families | E1, E2 (probe), E5 | 3 (arm executors) |
| `harness/arm_cli.py` | Data-access logging CLI the Claude/A2 arms call through the generated wrapper; logs the exact `raw_query` per CLAUDE.md #1 | E1 (Claude family) | 3 (arm executors) |
| `harness/e5_deepseek.py` | E5 mechanistic-confabulation probe runner (reuses the gemini_arm transport + tools) | E5 | 3 (arm executors) |
| `harness/arms.py` | **Non-executable** design spec: defines the five arms, the shared task, and the trace-capture discipline (documentation, runs nothing) | all (design) | 3 (arm executors) |
| `harness/adjudicate_deepseek.py` | Blinded **DeepSeek** LLM judge runner (gold-free); classifies the 12 items via the 3-label rubric | Adjudication | 4 (judge runners) |
| `harness/gateway.py` | Read-path gateway adapter (org-header GraphQL read; guarded snapshot helper via the cluster port-forward) — how every arm and the reference reach data | all | 5 (gateway adapters) |
| `harness/mcp_client.py` | Minimal MCP stdio client that drives the platform tools for the A3/A4 arms | E1 (A3/A4) | 5 (gateway adapters) |
| `harness/e2_run.py` | E2 behavioural DSSM runner **and the reversible write adapter** (cypher-shell in the neo4j pod; the gateway is read-only) | E2 | 5 (write adapter) + E2 |
| `harness/e2_author.py` | Authors the E2 perturbation set on the live graph; strata earned by in-memory reference simulation | E2 | additional (E2) |
| `harness/e2_score.py` | E2 DSSM scorer (detection / false-drift / staleness; Fisher) | E2 | additional (E2) |
| `harness/extract_tp4.py` | Per-parameter fidelity classifier — the E1 scoring instrument (the pre-registration's "extract_tp4 classifier") | E1 | additional (E1 scoring) |
| `harness/analyze_e1.py` | E1 analysis from traces (OF / decision divergence / stability) — Claude family | E1 | additional (E1 analysis) |
| `harness/analyze_e1_gemini.py` | Same, re-pointed to the Gemini/DeepSeek trace tags (`--tag`, `--model`) | E1 (2nd/3rd families) | additional (E1 analysis) |
| `harness/prompts/A1.txt … A4.txt` | The frozen arm prompts — exactly what each arm was handed | E1 | 3 (arm executors) |
| `harness/make_session.sh` | Generates the per-session `.arm` data-access wrapper the Claude/A2 arms run through | E1 | 3 (arm executors) |
| `harness/run_gemini_e1.sh` | Batch driver for the Gemini/DeepSeek arm matrix (`PROVIDER`/`MODEL`/`TAG`) | E1, E5 | 3 (arm executors) |
| `harness/JUDGE_RUNNERS.md` | Documents the three-judge setup + the verbatim blinded prompt (Gemini/Claude judges had no committed script) | Adjudication | 4 (judge runners) |
| `frameworks/target_prioritization.md` | The prose framework handed to A1–A3 (the study's own test instrument) | E1 | required data dep |
| `frameworks/executable_model_spec.json` | The executable model spec A4 retrieves (workflow-log URIs and per-line graph uuids and query-DSL fields stripped; name/weights/bindings/cypher kept) | E1 | required data dep |

## Environment variables

Set these to run against your own deployment; all default to empty/generic so the
modules still **import** unconfigured (no import breakage).

| Variable | Replaces | Read by |
|---|---|---|
| `SOD_GATEWAY_URL` | the gateway origin (was a localhost port-forward) | gateway.py |
| `SOD_ORG_ID` | the org / neo4j database id | gateway.py, arm_cli.py, e2_run.py |
| `SOD_ORG_HEADER` | the org header name (default `x-org-id`) | gateway.py |
| `SOD_NEO4J_NS` / `SOD_NEO4J_POD` | neo4j namespace / pod (were a named cluster) | gateway.py, e2_run.py |
| `SOD_NEO4J_CONTAINER` | neo4j container (default `main`) | **gateway.py only** (e2_run.py uses the literal `main`) |
| `SOD_MODEL_ID` | the executable-model / oracle id | reference.py, arms.py, e2_run.py |
| `SOD_REPORT_ID` | the computed-scores report id | gemini_arm.py |
| `SOD_MCP_LAUNCHER` | path to your MCP stdio launcher script | arm_cli.py, mcp_client.py, make_session.sh |
| `SOD_TRACE_FILE` | per-session trace output path (**required** by arm_cli.py — it exits if unset; set by make_session.sh) | arm_cli.py |
| `SOD_ROOT` | the study root directory | make_session.sh |
| `SOD_PYTHON` | the Python interpreter (was a venv abs path) | make_session.sh, run_gemini_e1.sh |
| `GEMINI_API_KEY` / `DEEPSEEK_API_KEY` | *(unchanged — already read from `.env.local` or env, never hardcoded)* | gemini_arm.py |
| `NEO4J_AUTH` | *(unchanged — read from the neo4j pod's own env by cypher-shell)* | e2_run.py |

Vendor API hosts (`api.deepseek.com`, `generativelanguage.googleapis.com`) are the
public model endpoints and were left as-is (not secrets).

## Public-biology content (kept as designed inputs, not edited)

- **Disease name (`DISEASE_OF_INTEREST`)** and **gene / cell-type symbols** appear as legitimate
  scientific inputs (not pasted traces) in: reference.py, extract_tp4.py, e2_run.py,
  e5_deepseek.py, arms.py, gemini_arm.py (via reference), prompts/A1–A4, and both
  framework files. The study runs on a purpose-built DISEASE_OF_INTEREST test graph, not client
  data. Redact further only if your venue requires.

## Platform vocabulary (renamed)

The platform's graph and API identifiers were renamed generically rather than
retained. Platform access is restricted, so the original names give nobody
outside the authors' environment any reproducibility, while a reader who
recognised them could de-anonymise the submission.

What appears in this repository: the graph property `modelIdProperty` (its
value is env-driven via `SOD_MODEL_ID`), the graph edge `HAS_SCORE_EDGE`, the
read mutation `runReadQuery`, and the MCP tool names `list_models`,
`get_model`, `enumerate_reports`, `get_scores`, `entity_rank`, `graph_schema`,
`entity_search`, and `graph_query`. Renaming was applied consistently across
the executors, the Python helper functions, and the frozen arm prompts, so
what each arm was handed still matches what the executor calls.

Query shapes, tool-call sequences, arguments, call order, bindings,
thresholds, weights, and every scored result are exactly as executed. Gene and
cell-type symbols were **not** substituted, so the biology is fully
inspectable. The therapeutic area appears as `DISEASE_OF_INTEREST`.

The anonymised-to-actual mapping is held by the authors and can be supplied to
reviewers or an area chair on request.

Also removed during export as non-functional: internal workflow-engine names
in comments, the spec's per-line graph uuids and query-DSL copies, and the
workflow-log storage URIs.

## Imports & dependencies

- **Broken internal imports: NONE.** Every `harness.*` import resolves against
  `export ∪ scaffold`. Scaffold modules the exported code imports: `harness.extract`
  (extract_tp4), `harness.metrics` (e2_score, analyze_e1*), `harness.perturb` (e2_run).
- **External pip deps:** `requests` (gateway), `pyyaml` (e2_author) — plus
  `numpy`/`scipy` already required by the scaffold's `metrics.py`.
- **Runtime data reads:** `frameworks/target_prioritization.md` + `…/executable_model_spec.json`
  (included — `gemini_arm.py` reads both at module load, so they are required);
  `perturbations/e2.yaml` (scaffold); `handoff/adjudication_items.json` (the 12 blinded
  items — data, in the handoff package, not this code export). `adjudicate_deepseek.py`
  writes `handoff/judge_deepseek.json`.

## What genuinely does NOT exist as a standalone script (honest gaps)

- **The Gemini and Claude judge runners.** Only the **DeepSeek** judge is a committed
  script (`adjudicate_deepseek.py`). The Gemini 2.5 Pro judge and both Claude judge runs
  (original + the blinded re-run) were driven by Claude Code sub-agents / a workflow with
  an inline prompt — no committed runner file. Same 3-label rubric; the verbatim blinded
  prompt is in `harness/JUDGE_RUNNERS.md`. Their output labels live in the handoff package
  (`judge_{gemini,claude,deepseek}.json`, `judge_claude_LEAKED.json`), not in this export.
- **The Claude/A2 arm runs have no monolithic runner.** Those arms ran as Claude Code
  sub-agents that reached data through the generated `.arm` wrapper
  (`make_session.sh` → `arm_cli.py`). That wrapper + CLI *is* their executor.
- **`build_handoff.py` was deliberately NOT exported** — it assembles `HANDOFF.json`
  but embeds computed result values and env references, so it is results-bearing rather
  than pure instrument. Available on request.
- **The A4⁻ (versioning-off) predecessor model was never constructed** (`arms.py` notes
  `A4_ARCHIVED_MODEL_ID = None`); the A4-vs-A4⁻ gap-analysis is future work.
- **Human-panel adjudication scorers** (`score.py`, `score_panel.py`) live in
  `handoff/human_adjudication/`, not in this harness export.

## Verification

Export-time checks: every `.py` parses, and there are zero broken internal
imports against `export` plus the scaffold. The residual-term sweep that
produced this export is part of the authors' release tooling and is not
included here, because the pattern list enumerates the terms it exists to
detect.
