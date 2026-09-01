# Deviations from pre-registration

Thirteen deviations were logged. An empty list would itself be a positive
claim that nothing changed after the freeze, so the log is kept honestly.
None of these altered a frozen artifact, a measured binding, a threshold,
or a weight.

This is the anonymised release version, matching Appendix E of the paper.
Items 12 and 13 are the substantive ones for interpreting the adjudication.
Item 8 is the only one that cost data.

1. An exploratory pilot ran before the freeze to de-risk the runner, and the frozen artifacts were refined from it. No scored session preceded the freeze.

2. The aggregation trap gained an explicit binary-presence plausible-wrong and an `underdetermined` flag after the pilot showed this was the binding that drifted.

3. The arm command-line result cap was changed from a hard truncation that emitted invalid JSON to a valid large-result envelope.

4. The disease framework was replaced with a richer disease-native version, and one evidence line was corrected and re-validated by the framework author before the freeze.

5. The study initially specified a single model family, superseded by item 9.

6. The binding extractor was generalised on pre-freeze pilot traces, so that a binding no query touches scores as unexecuted rather than as a violation, and so that equivalent query formulations are recognised.

7. The freeze covers the E1 protocol, and E2 artifacts were frozen separately before E2 ran.

8. An infrastructure outage killed the data connection mid-run during an E5 pass, failing three data-access sessions, which were re-run cleanly. No scored result depends on the failed sessions.

9. A second model family, Gemini 2.5 Flash, was added to test cross-vendor generality. The frozen instrument is byte-identical, and only the arm executor is new, because Flash cannot run in the same orchestration as Claude. Executor accommodations were confined to the reply protocol and directive parsing.

10. A third model family, DeepSeek-V4-Pro, was added as the capable-tier cross-vendor test. Three executor accommodations were required for a reasoning model: a raised token cap, because the hidden reasoning trace counts against it and exhausted the original budget; a rule that a ranking is terminal only when no executable query is still pending, because a reasoning model states a provisional priors-only ranking before running anything; and a broadened network retry.

11. Human adjudication was upgraded from the pre-registered single 20% scorer to an independent blinded panel, converting that line from a single point into an inter-rater reliability study.

12. A third adjudication judge from a third vendor was added gold-free, after the first judge's items file was found to contain the gold field.

13. The first judge was then re-run blind on the same items with the identical rubric. The contaminated run is preserved in the released record and no reported number derives from it. All three judges are uncontaminated.
