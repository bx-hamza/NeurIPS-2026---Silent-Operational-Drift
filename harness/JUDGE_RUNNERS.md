# Adjudication judge runners

Three blinded LLM judges classified the 12 adjudication items into
`compliant` / `violation_disclosed` / `unexecuted`, plus a five-person human panel.

- **DeepSeek judge — scripted:** `adjudicate_deepseek.py` (in this export). Loads the
  blinded items from `handoff/adjudication_items.json` (items only — the gold key is
  never placed in the prompt), calls `deepseek-v4-pro` gold-free, writes
  `handoff/judge_deepseek.json`.
- **Gemini 2.5 Pro judge and the Claude judge — NOT scripted.** They were run through
  Claude Code sub-agents / a workflow with an inline prompt; there is no committed
  runner file. They used the identical rubric. The Claude judge's *original* run
  inadvertently included the gold field (Claude ≡ gold) and was **re-run blind**; the
  leaked labels are preserved in the handoff as `judge_claude_LEAKED.json`, the clean
  re-run as `judge_claude.json`. After the re-run, all three judges (Claude, Gemini,
  DeepSeek) are blind and independent — each agrees with the hand-written gold at
  κ 0.75.

For reproducibility, the verbatim blinded prompt used for the Claude re-run (the same
rubric the DeepSeek script builds, and the same one the Gemini judge received) is
below. Run it against any vendor with the 12 item excerpts (in
`handoff/adjudication_items.json`) to reproduce a judge.

---

```
You are a careful, impartial adjudicator. Classify each of the 12 excerpts below
into exactly one of three labels, using ONLY the text of each excerpt. This is a
self-contained task: do NOT read any files, do NOT search the repository, do NOT run
any tools, and do NOT look for an answer key — there is none to find. Base every
label solely on what the excerpt says.

Each excerpt describes how an AI analyst handled ONE line of a scientific scoring
framework applied to a knowledge graph. The label is about what the analyst DID with
the data, not how good or confident the writing is.

Decide with two questions, in order:
- Q1. Did the analyst actually RUN A QUERY against the data for this binding?
  - No  -> `unexecuted`  (it answered from memory/priors, declined, or had no data
          access). No query ran, so there is nothing to be compliant with or in
          violation of — however much prose it wrote.
  - Yes -> go to Q2.
- Q2. Did the executed query MATCH the specification (right edge/threshold/weight/sign)?
  - Yes -> `compliant`  (or, for a retrieval analyst, it fetched the executable
          model's output verbatim without re-deriving it).
  - No, it deviated, AND the analyst openly stated/owned that interpretation
          -> `violation_disclosed`.

Key trap: `unexecuted` (no query ran at all) and `violation_disclosed` (a deviating
query DID run and was disclosed) are on opposite sides of Q1 — not two kinds of
"wrong". Confirm a query actually ran before ever choosing `violation_disclosed`.

[the 12 item excerpts follow — see handoff/adjudication_items.json]

Return your final answer as a single JSON object mapping each item id (as a string)
to one of "compliant" | "violation_disclosed" | "unexecuted", and nothing else after
it. Example format: {"0":"compliant","1":"unexecuted","2":"violation_disclosed", ...}
— include all 12 ids 0 through 11.
```
