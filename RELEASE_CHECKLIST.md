# Release checklist

Two audiences, two moments. The anonymised repository is needed **before
submission** because the paper's reproducibility statement links to it. The
public repository is needed **on acceptance**.

## A. Before submitting (2 September)

- [x] **Populate `harness/`.** Done. The instrument, arm executors, framework
      representations, and arm prompts are in. Remaining gaps are documented
      in `harness/README.md` under "Known gaps".
- [ ] **Run the scrub and its check from the private tooling directory.**
      ```
      python private-tooling/scrub_for_release.py --repo path/to/release
      git -C path/to/release diff        # read this, do not skip it
      python private-tooling/scrub_for_release.py --repo path/to/release --check
      ```
      `scrub_for_release.py`, `validate_handoff.py` and
      `ANONYMIZATION_MAP.md` live **outside** the repository. Each contains,
      in plaintext, the terms it exists to remove or detect, so committing any
      of them would undo the anonymisation in a single file. They are
      gitignored as a second line of defence, but keep them in a separate
      directory rather than relying on that.

- [ ] **Run the instrument tests.** `python harness/tests_smoke.py` must
      print `SMOKE OK`.
- [x] **Pre-registration.** Done. There is no separate pre-registration
      document: the freeze is an annotated, hashed Git tag, and
      `docs/PREREGISTRATION.md` records what it covered, what was
      pre-registered, and how to verify it. Note the honest caveat it states:
      because this repository ships under a fresh anonymous history, the tag
      does not resolve here and the hash commits against the private
      original, demonstrable to the PC on request.
- [ ] **Run the staleness audit.** `python audit_staleness.py` must print
      `OK`. It fails if an analysis file is missing a judge, was scored
      against the contaminated judge run, or has drifted from the frozen
      numbers in `data/HANDOFF.json`.
- [ ] **Run the verification.** `python verify_numbers.py` must print
      `OK 88/88`. If it fails, the paper and the data disagree and the paper
      is wrong until reconciled.
- [ ] **Regenerate both figures** and confirm they match the paper:
      `python figures/make_figure1.py && python figures/make_figure2.py`
- [ ] **Strip identity from git metadata.** Anonymous hosting does not hide
      commit authorship. Commit fresh with a neutral author:
      ```
      git init && git checkout -b main
      git -c user.name="Anonymous" -c user.email="anon@example.com" \
          commit --allow-empty -m "Initial release"
      ```
      Do not push an existing history that contains real names or emails.
- [ ] **Check for stragglers.** Institutional names, internal URLs, ticket
      IDs, cluster names, and personal paths in code comments. `grep -ri` for
      your organisation name and your own username across the tree.
- [ ] **Confirm the human panel data is anonymised.** `adjudication/human_panel/`
      holds per-rater answers. Raters must be identified only as `p1`–`p5`,
      with no names in any CSV, filename, or the packet HTML.
- [ ] **Publish anonymously** (Anonymous GitHub or an anonymised OSF
      component) and **paste the URL into the paper's reproducibility
      statement**, replacing "the anonymised link supplied with this
      submission".
- [ ] **Verify the anonymous link resolves in a private browser window**
      before submitting.

## B. On acceptance

- [ ] Add `LICENSE` (Apache-2.0) and `LICENSE-data` (CC BY 4.0).
- [ ] Add `CITATION.cff` with the final author list and the arXiv DOI if one
      exists.
- [ ] Restore real authorship, add an acknowledgements file, and publish
      under the project's own account.
- [ ] Recompile the paper with the `final` option so the author block and the
      workshop footnote appear.
- [ ] Re-run the scrub check once more after any file is added back.

## What must never ship

| Item | Why |
| --- | --- |
| Raw agent transcripts | Disease context and target identities in the clear |
| The knowledge graph, or any dump of it | Third-party production system, not ours to redistribute |
| Gateway credentials, tokens, connection strings, cluster references | Security |
| The therapeutic area, platform, or client name | Binding anonymity constraint; the scrub enforces this |

## What deliberately does ship

The contaminated first judge run (`adjudication/judge_claude_LEAKED.json`)
ships alongside its blind re-run. It is evidence that the remediation
described in `docs/DEVIATIONS.md` items 12 and 13 actually happened, and
withholding it would ask readers to take the correction on trust. No number
in the paper derives from it, and `verify_numbers.py` reads only the clean
run.
