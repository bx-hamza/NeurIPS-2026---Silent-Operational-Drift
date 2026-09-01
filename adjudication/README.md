# adjudication

The 12 formulation-brittle items, the three blinded LLM judge runs, and the
five-person human panel.

## Files

| Path | Contents |
| --- | --- |
| `adjudication_items.json` | The 12 items with the frozen gold labels. |
| `judge_claude.json`, `judge_gemini.json`, `judge_deepseek.json` | The three gold-free judge runs, one per vendor. These are what every reported judge number comes from. |
| `judge_claude_LEAKED.json` | The contaminated first run, preserved deliberately. See below. |
| `human_panel/` | Rater protocol, label guide, blinded items, and the five anonymised answer sets (`p1`–`p5`). |
| `human_panel/score_panel.py` | Panel reliability: per-rater kappa, Fleiss, consensus vs gold, and consensus vs each judge. Writes `analysis/human_adjudication_panel.json`. |
| `human_panel/score.py` | Single-rater variant of the same scoring. |

## The contaminated run

The first judge run from the first vendor inadvertently received the gold
label. It was re-run blind, and `judge_claude.json` is that blind re-run. The
contaminated run ships as `judge_claude_LEAKED.json` so the remediation can be
checked rather than taken on trust. Nothing scores against it.

It is easy to tell the two apart: the contaminated run agrees with the gold
almost perfectly, so any analysis whose `vs_claude` block equals its `vs_gold`
block was computed against the leaked run.

## Two staleness traps, both now fixed

Worth knowing if you compare this artifact against an older copy of the study
tree.

**The scorers originally covered two judges.** The third vendor was added
later (deviation 12), so the two-judge version of `score_panel.py` predated it
and emitted no `vs_deepseek` block. Both scorers now cover all three.

**An earlier panel analysis was computed against the contaminated run**, which
made its `vs_claude` read 0.724 rather than 0.495. Regenerating with the blind
re-run gives 0.495 for all three judges, which is what the paper reports and
what `verify_numbers.py` asserts.

Neither error changed a number in the paper. Both would have misled anyone
auditing the artifact, which is why `verify_numbers.py` now cross-checks the
committed panel analysis against `data/HANDOFF.json` instead of trusting
either alone.

Three analysis files were affected and all three have been regenerated:
`human_adjudication_panel.json`, `human_adjudication_panel_specialists.json`,
and the single-rater `human_adjudication.json`. Each had both problems at
once, a missing `vs_deepseek` block and a `vs_claude` value taken from the
contaminated run. The corrections are visible: the specialists file's
`vs_claude` moves from 0.841 to 0.582, and the single-rater file's from 0.355
to 0.368. No headline figure changed, because every headline is a
human-versus-gold number and the gold was never contaminated.

`audit_staleness.py` at the repository root now checks all of this
mechanically: that every adjudication file carries all three judges, that no
file shows the leaked-run signature, that the panel files match the frozen
numbers in `data/HANDOFF.json`, and that `judge_claude.json` is not simply a
copy of the leaked run. Run it after regenerating anything in `analysis/`.

## Reproducing

```bash
python adjudication/human_panel/score_panel.py
python verify_numbers.py     # asserts the output agrees with HANDOFF.json
```
