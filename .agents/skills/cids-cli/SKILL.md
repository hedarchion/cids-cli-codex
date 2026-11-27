---
name: cids-cli
description: Use the ASIE/CIDS CLI to validate and import weekly Daily Lesson Plans (DLP/RPH), save or repair Learning Objectives, and inspect MIW, class, and timetable records in the user's CIDS account.
---

# CIDS CLI

Use CIDS CLI 0.2.0 or newer in the agent's shell environment. Run
`cids --version` to check the installation. Use `cids week-schema` and
`cids import-week --help` for the installed version's input contract.
`cids auth status --json` checks the session for remote work. If the runtime
already has `CIDS_USERNAME` and `CIDS_PASSWORD` in its secret environment,
`cids auth login --non-interactive` starts a session. Keep credentials and
cookies out of chat and lesson files.

## Prepare and check lessons

Use one weekly JSON file per target MIW and class. In each entry, put the
teacher's Learning Objectives in `objectives` as an array of plain-text
strings, one objective per item. CIDS stores them in the lesson-specific
**Knowledge → Learning Objectives** form. Preserve any objectives already
provided in the source and copy them into this field if the source mixes them
with activities or notes. An omitted field preserves the existing objectives.
A supplied array replaces that lesson's objective list.

Apply `cs_code` and `ls_code` from the lesson source and verify them against
the target MIW's choices. The CLI resolves codes or exact labels on the MIW
when creating lessons. Existing DLP updates keep their standards.

1. Run `cids import-week FILE --dry-run`. Check the `objective_count` for the
   lessons that should receive objectives.
2. Resolve the target's `--miw-id`, `--class-id`, `--setjadual`, `--owner-id`
   and `--grouplevelsubject` from the user's target or its current CIDS forms.
   Use `cids functions` and `cids describe NAME` for discovery. Useful routes
   include `records.list`, `miw.open`, `classes.list` and `timetable.view`.
3. Run `cids import-week FILE` with those flags and `--check`. Inspect the
   proposed creates and updates against the intended dates and class. If
   CIDS does not expose the subject or session, supply the target's
   `--subject` and `--session`.
4. When the user has authorized uploading or repairing the selected lessons,
   run the same command with `--yes` in place of `--check`. Compare each
   `objectives_verified` count against its planned `objective_count` before
   reporting completion.

For `IMPORT_PARTIAL`, use `failed_entry`, `lesson_id` and `cause_code` to
inspect the lesson and rerun `--check` before any retry. A created lesson may
already exist even when the following save failed. For a missing objective
field, check that Learning Objectives is enabled in the target's Instructional
Profile. Keep objectives in that field when resolving the problem.
