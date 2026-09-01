# harness — the measurement instrument

**Status: complete for scoring and analysis. Runnable end to end only against
a substrate with the same schema.**

Everything the study used to instrument, execute, score, and analyse the arms
is here, together with the frozen arm prompts and the two framework
representations under test. What cannot be shipped is the knowledge graph
itself.

## The instrument

| File | What it does |
| --- | --- |
| `../traps/target_prioritization.yaml` | The trap suite. Twelve instrumented parameters, each with its specified binding and pre-registered plausible-wrong alternatives. `P08 aggregation_rule` is the underdetermined one that drives the paper's result. |
| `extract.py` | Extracts the bindings an agent *executed* from the query strings the gateway received and classifies each against the specified binding. `executed_binding` and `narrated_binding` are never merged, because the finding lives in the gap between them. |
| `extract_tp4.py` | The per-parameter fidelity classifier applied to this framework. The pre-registration's "extract_tp4 classifier". |
| `metrics.py` | OF, silent-violation rate, DSSM detection, RRR, stability, Cohen and Fleiss kappa. Clustered bootstrap resamples *sessions*, not parameter observations. |
| `reference.py` | Hand-written agent-free per-parameter reference queries across the thirteen evidence lines. This is the oracle E1 is scored against. |
| `e2_reference.py` | Agent-free deterministic per-line composite, the E2 ground truth. |
| `tests_smoke.py` | Unit tests over synthetic traces. Prints `SMOKE OK`. The numbers it prints are fixtures, not study results. |

## Running the arms

| File | What it does |
| --- | --- |
| `arms.py` | Non-executable design spec: the arms, the shared task, and the trace-capture discipline. |
| `prompts/A1.txt` … `A4.txt` | The frozen arm prompts, exactly as each arm received them. |
| `arm_cli.py` | The data-access CLI the Claude and A2 arms call through. Logs the exact `raw_query`, which is what makes execution-based scoring possible. |
| `make_session.sh` | Generates the per-session `.arm` wrapper those arms run through. |
| `gemini_arm.py` | Multi-provider executor: Gemini `generateContent`, DeepSeek OpenAI-compatible transport, and the tool layer. Runs A1–A4 for those two families. |
| `run_gemini_e1.sh` | Batch driver for the Gemini and DeepSeek arm matrix. |
| `gateway.py` | Read-path gateway adapter. |
| `mcp_client.py` | Minimal MCP stdio client driving the platform tools for A3 and A4. |

## Experiments and analysis

| File | What it does |
| --- | --- |
| `perturb.py` | E2 engine and design validator: reversible application, restoration verification, null-control generation. |
| `e2_author.py` | Authors the E2 perturbation set against the live graph. |
| `e2_run.py` | E2 behavioural runner and the reversible write adapter. The gateway is read-only, so writes go through a separate path. |
| `e2_score.py` | E2 scorer: detection, false drift, staleness, Fisher exact. |
| `e5_deepseek.py` | E5 adversarial-probe runner. |
| `adjudicate_deepseek.py` | The blinded DeepSeek judge runner, gold-free. |
| `JUDGE_RUNNERS.md` | The three-judge setup and the verbatim blinded prompt. |
| `analyze_e1.py`, `analyze_e1_gemini.py` | E1 analysis from traces: OF, decision divergence, stability. |
| `discover.py` | Read-only capability probe. Run first on a new substrate. |

## Configuration

All endpoints, org and cluster identifiers, model and report ids, and paths
are environment variables. Every module imports unconfigured, so the tree can
be inspected and unit-tested without a deployment. `docs/HARNESS_MANIFEST.md`
lists each variable and which modules read it. API keys for the vendor
endpoints are read from the environment and were never committed.

## Not included, deliberately

Two scripts from the authors' pipeline are withheld because each one contains,
in plaintext, the terms it exists to remove or detect. `scrub_for_release.py`
holds the substitution table, and `validate_handoff.py` holds a
forbidden-term list. Committing either would restore exactly the information
the anonymisation removes. Neither is needed to use this artifact. Both are
available from the authors after acceptance.

## Known gaps, stated rather than papered over

- **Only the DeepSeek judge exists as a committed script.** The Gemini judge
  and both Claude judge runs were driven through sub-agents with an inline
  prompt, so there is no runner file for them. All three used the same
  three-label rubric, and the verbatim blinded prompt is in
  `JUDGE_RUNNERS.md`. The resulting labels are in `adjudication/`.
- **The Claude and A2 arms have no monolithic runner.** They ran as
  sub-agents reaching data through the generated `.arm` wrapper, so
  `make_session.sh` together with `arm_cli.py` *is* their executor.
- **`build_handoff.py` is not included.** It assembles `HANDOFF.json` but
  embeds computed result values, making it results-bearing rather than
  instrument. Available on request.
- **The A4⁻ versioning-off comparison was never built.** `arms.py` records
  `A4_ARCHIVED_MODEL_ID = None`. That comparison is future work.

## Substrate dependency

Re-running the arms needs a knowledge graph with the same schema. The graph
used in the study is a third-party production system and is not
redistributable, so end-to-end replication on the original substrate is not
possible outside the authors' environment. Everything downstream of the
scored bindings runs offline from `data/HANDOFF.json` and reproduces the
paper exactly.

Replication on a *different* substrate is the more useful target, and
`docs/PROTOCOL.md` is written to support it. The trap-suite design, the
extract-from-execution rule, the null-control requirement, and the
fidelity-versus-divergence metric pair transfer to any framework with at
least one underdetermined instruction.
