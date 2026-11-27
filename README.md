# cids-cli

`cids-cli` turns the authenticated functions of `https://asiemodel.net/model/`
into explicit terminal operations. The application is a legacy, server-rendered
PHP site rather than a documented public API, so the CLI mirrors its observed
routes and form targets.

The complete browser-derived inventory is in
[FUNCTION_MAP.md](FUNCTION_MAP.md). No username,
password, session token, live record identifier, or personal record is stored in
this repository.

## Install

Install Python 3.9 or later, then run this from a checkout of the repository.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
cids --version
```

Both `cids` and `cids-cli` invoke the same program. It also runs as
`python -m cids_cli`. On Windows, activate with `.venv\Scripts\Activate.ps1`
in PowerShell or invoke `.venv\Scripts\cids.exe` directly. Use
`python -m pip install --upgrade .` to install changes from a newer checkout
into the same environment.

## Authenticate

Interactive login is safest because the password is not echoed or placed in shell
history:

```sh
cids auth login
cids auth status
```

For automation, inject `CIDS_USERNAME` and `CIDS_PASSWORD` through the runtime's
secret store and use `cids auth login --non-interactive`. Session cookies are
stored under `$XDG_CONFIG_HOME/cids-cli/cookies.lwp` when set, or
`~/.config/cids-cli/cookies.lwp` by default. Set a separate `XDG_CONFIG_HOME`
for each agent or account that uses a different CIDS login.

```sh
cids auth logout
```

## Discover and run functions

```sh
cids functions
cids functions --domain yip
cids describe records.list
cids describe smart-search --json
```

All application calls go through a registry; there is intentionally no unrestricted
raw-request command.

Read-only examples:

```sh
cids run home
cids run records.list --param yl=2026 --param l=20 --format text
cids run resource.view --param id=RESOURCE_ID --format html --output-file resource.html
cids run dashboard.required-hours --param id=USER_ID --format json
```

Mutations fail closed unless `--yes` is supplied. Inspect them first:

```sh
cids describe yip.delete
cids run yip.delete --param id=REPORT_ID --param user=USER_ID --dry-run
cids run yip.delete --param id=REPORT_ID --param user=USER_ID --yes
```

Form-driven operations accept repeated `--param KEY=VALUE` values and uploads use
`--file FIELD=PATH`. Many write forms require hidden values or a fresh token from a
live page. Those entries are marked form-dependent; obtain the current fields and
dry-run the command instead of guessing.

AI Smart Search uses its observed JSON contract:

```sh
cids run smart-search \
  --param id=FIELD_ID \
  --param category=CATEGORY \
  --param selected=CURRENT_VALUE \
  --dry-run
```

It is guarded because it may consume application quota.

## Import a weekly lesson file

`import-week` reads a weekly lesson file, updates matching DLPs, and creates
missing ones. It saves `objectives` in each lesson's **Knowledge →
Learning Objectives** field and reopens the lesson to verify objectives,
activities, and reflection. Keep one plain-text objective per array item.
An older file that omits objectives leaves an existing DLP's objectives as
they are. Given objectives replace the existing objective list for that DLP.

```json
{
  "version": 1,
  "week": 12,
  "entries": [
    {
      "date": "2027-03-23",
      "time_from": "10:30 AM",
      "time_to": "11:30 AM",
      "topic": "Properties of materials",
      "cs_code": "6.1",
      "ls_code": "6.1.2",
      "objectives": ["Compare the properties of two materials."],
      "activity_html": "<p>Compare samples in pairs and record observations.</p>",
      "reflection_html": "<p>Reflection to be completed after the lesson.</p>",
      "notes_html": ""
    }
  ]
}
```

Print the installed schema with `cids week-schema`. Existing exports can use
`objectives_html` or `objective_html` to migrate an HTML list into separate
objectives. Use one objectives field per entry.

For new DLPs, provided standards must match choices in the target MIW by
code or exact label. Omit `cs_code` and `ls_code` where the curriculum has no
corresponding fields. An existing DLP keeps its standards when updated.
The CLI reads the MIW's subject and session for new-slot checks. Pass
`--subject` and `--session` if the MIW does not expose them.

Each live run targets one account, MIW, class and timetable revision. Get the MIW ID from its
`openmiw` link, the class and timetable IDs from the dated periods below, and
the owner ID and `grouplevelsubject` from the target CIDS forms. The
`records.list`, `miw.open`, `classes.list` and `timetable.view` read-only
functions can help locate them.

```sh
# Validate the source locally.
cids import-week weekly-lessons.json --dry-run

# Check the target and available forms without writing lessons.
cids import-week weekly-lessons.json \
  --miw-id MIW_ID --class-id CLASS_ID --setjadual TIMETABLE_ID \
  --owner-id USER_ID --grouplevelsubject GROUP_LEVEL_SUBJECT --check
```

The actual import performs the same full-batch preflight before its first write:

```sh
cids import-week weekly-lessons.json \
  --miw-id MIW_ID \
  --class-id CLASS_ID \
  --setjadual TIMETABLE_ID \
  --owner-id USER_ID \
  --grouplevelsubject GROUP_LEVEL_SUBJECT \
  --yes
```

Successful results contain `ok`, `mode`, `write_performed`, and per-lesson
statuses. Check the import's `objectives_verified` count for each lesson.
Add `--pretty` for indented JSON. Failures go to stderr as JSON with a stable
`error.code`. Exit statuses are `2` for
local input errors, `3` for authentication, `4` for transport/server failures,
`5` for remote precondition failures, `6` for missing confirmation, and `7` when
writes began but the batch did not finish. Important codes include
`IMPORT_SCHEMA_INVALID`, `IMPORT_IDENTIFIER_INVALID`, `IMPORT_DUPLICATE_SLOT`,
`IMPORT_SLOT_OCCUPIED`, `IMPORT_TOKEN_MISSING`,
`IMPORT_STANDARD_NOT_FOUND`, `IMPORT_OBJECTIVES_FIELD_UNAVAILABLE`, and
`IMPORT_PARTIAL`. A partial import reports the failed entry, its lesson ID
when available, and the underlying `cause_code`. Review that entry and run
`--check` before resuming from the same file.

## Timetable changes and teaching-week numbers

`cids timetable-periods` reads active and archived CIDS timetable revisions.
Each date in its output has a timetable ID and the periods that apply that
day when CIDS provides a single fixed revision. Flexible timetables,
overlapping revisions and missing dates are flagged for a teacher to resolve.
Check the dates before each import. If a timetable changes midweek, prepare
one import per revision with its own `--setjadual`.

```sh
cids timetable-periods --date-from 2027-03-22 --date-to 2027-03-26 --subject Science
cids week-log set --session 2027 --week 12 --date-from 2027-03-22 --date-to 2027-03-26
cids week-log list --session 2027 --date 2027-03-24
```

The teaching-week log stores school-confirmed date ranges locally under the
CIDS CLI configuration directory. The week number comes from the school.
Use `--no-teaching` for a confirmed school break outside a numbered week.
Setting a range with the same session and start date updates that entry.
Overlapping entries in one session return an error.

The agent skill checks with the teacher about holidays, exams, programmes
and special duties. For an affected period it asks whether to skip it,
reschedule it, or record the reflection the school requires.

## Agent skill

The [CIDS CLI skill](.agents/skills/cids-cli/SKILL.md) uses the
[Agent Skills format](https://agentskills.io/specification). Install the CLI
in the same environment where the agent's shell commands run. For Hermes
in this checkout, use its project-local skill discovery. For use across
projects, copy the skill to the active Hermes profile's skills directory.
The default profile uses `~/.hermes/skills`. See the
[Hermes Skills System](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/).

```sh
mkdir -p ~/.hermes/skills
cp -R .agents/skills/cids-cli ~/.hermes/skills/
hermes skills list
```

## Safety model

- Read-only routes run without confirmation.
- Every create, update, share, copy, upload, AI-assisted, account-changing, or
  destructive operation requires `--yes`; `--dry-run` never contacts the site.
- Legacy GET links that change state are still classified as mutations.
- Request traces show field names, not field values, and redact passwords, tokens,
  authorization data, and cookies.
- Uploads, payments, profile changes, meeting actions, and deletes were mapped but
  not executed during discovery.

## Tests

```sh
python -m pip install -e '.[dev]'
pytest -q
```

The test suite is local and mocked; it does not contact `asiemodel.net`.

## Responsible use

Use this software only with an account and data you are authorized to access,
and only where the site owner permits automated access. Lesson files and API
responses may contain personal or confidential information; do not commit them
to a public repository. This project is independent and is not affiliated with
or endorsed by ASIE or the CIDS application maintainers.
