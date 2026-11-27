---
name: cids-cli
description: Set up the ASIE/CIDS CLI and prepare or import weekly Daily Lesson Plans (DLP/RPH) using the teacher's school week numbering, dated timetable and confirmed holiday or special-duty reflections. Use also to repair Learning Objectives.
---

# CIDS CLI

For first-time setup, install the checkout in a project Python virtual
environment with `python -m pip install .` from the repo root. Run the CLI
with that environment's interpreter in later shells. Check for CIDS CLI
0.3.0 or newer with `cids --version`. Use `cids week-schema` and
`cids import-week --help` for the installed version's input contract.
`cids auth status --json` checks the session for remote work. Guide the
teacher to enter credentials privately at the `cids auth login` prompt.
If the runtime already has `CIDS_USERNAME` and `CIDS_PASSWORD` in its secret
environment, use `cids auth login --non-interactive`. Keep credentials and
cookies out of chat and lesson files.

## Confirm the school week and schedule

- Use `cids week-log list --session SESSION` to look up the school's teaching
  week and its exact dates. Ask for the school's week number and date range
  when the log and source are missing or disagree. School teaching weeks can
  differ from calendar week numbers. Record confirmed ranges with
  `cids week-log set --session SESSION --week NUMBER --date-from START --date-to END`.
  Use `--no-teaching` in place of `--week` for a confirmed break outside a
  numbered teaching week.
- Run `cids timetable-periods --date-from START --date-to END` for every
  batch. Use the revision that covers each lesson date, including archived
  revisions for past lessons. Match the subject and class by name and use
  the returned times and timetable ID. For a flexible timetable, overlapping
  revisions or a missing date, ask which revision and periods applied.
  When a revision changes midweek, split the import by timetable ID and
  check every file before uploading any. Refresh an earlier preview before
  uploading. Show the teacher any changed periods for review.
- Before preparing the import, ask whether any scheduled lessons were
  affected by a holiday, school programme, exam, special duty or other
  cancellation if the teacher has not already said. Ask which dates and
  classes were affected and whether the school expects those slots to be
  skipped, rescheduled or recorded with a short reflection. For a required
  reflection, state what the teacher confirms happened and any confirmed
  replacement plan. Include attainment, attendance and lesson outcomes only
  when supported by the teacher's account. For a future lesson, use a
  reflection placeholder only if the teacher wants one. When changing
  only an existing reflection, preserve the lesson's other content. If
  the current content cannot be read, draft the reflection for review.

## Prepare and check lessons

Use one weekly JSON file per target MIW, class and timetable revision. In
each entry, put the teacher's Learning Objectives in `objectives` as an
array of plain-text strings, one objective per item. CIDS stores them in the lesson-specific
**Knowledge → Learning Objectives** form. Preserve any objectives already
provided in the source and copy them into this field if the source mixes them
with activities or notes. An omitted field preserves the existing objectives.
A supplied array replaces that lesson's objective list.

Apply `cs_code` and `ls_code` from the lesson source and verify them against
the target MIW's choices. The CLI resolves codes or exact labels on the MIW
when creating lessons. Existing DLP updates keep their standards.

1. Run `cids import-week FILE --dry-run`. Check the `objective_count` for the
   lessons that should receive objectives.
2. Take `--class-id` and `--setjadual` from the confirmed timetable periods.
   Resolve `--miw-id`, `--owner-id` and `--grouplevelsubject` from the target's
   CIDS forms.
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
