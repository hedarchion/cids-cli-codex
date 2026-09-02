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

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

Both `cids` and `cids-cli` invoke the same program. It also runs as
`python -m cids_cli`.

## Authenticate

Interactive login is safest because the password is not echoed or placed in shell
history:

```sh
cids auth login
cids auth status
```

For automation, the CLI also reads `CIDS_USERNAME` and `CIDS_PASSWORD`. Keep those
values in a secret manager rather than a committed `.env` file. The password is
never persisted. Session cookies are stored in
`~/.config/cids-cli/cookies.lwp` with user-only permissions.

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

`import-week` reads the lesson JSON locally, resumes matching DLPs when they
already exist, creates missing DLPs, and verifies that activity and reflection
content persisted. Compact JSON is the default; add `--pretty` for human-readable
output. Lesson content is never echoed.

Use the three modes in order when an agent needs maximum safety:

```sh
# Offline schema and semantic validation; zero network access.
cids import-week weekly-lessons.json --dry-run

# Authenticated remote preflight; reads CIDS but performs no lesson writes.
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
  --subject english \
  --session 2026 \
  --yes
```

Every result contains `ok`, `mode`, `write_performed`, and per-lesson statuses.
Failures are JSON on stderr with a stable `error.code`; exit statuses are `2` for
local input errors, `3` for authentication, `4` for transport/server failures,
`5` for remote precondition failures, `6` for missing confirmation, and `7` when
writes began but the batch did not finish. Important codes include
`IMPORT_SCHEMA_INVALID`, `IMPORT_IDENTIFIER_INVALID`, `IMPORT_DUPLICATE_SLOT`,
`IMPORT_SLOT_OCCUPIED`, `IMPORT_TOKEN_MISSING`, `IMPORT_NOT_PERSISTED`, and
`IMPORT_PARTIAL`.

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
pytest -q
```

The test suite is local and mocked; it does not contact `asiemodel.net`.

## Responsible use

Use this software only with an account and data you are authorized to access,
and only where the site owner permits automated access. Lesson files and API
responses may contain personal or confidential information; do not commit them
to a public repository. This project is independent and is not affiliated with
or endorsed by ASIE or the CIDS application maintainers.
