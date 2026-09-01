"""Agent-facing import contract tests using synthetic lesson data only."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cids_cli import cli
from cids_cli.client import CidsError
from cids_cli.import_week import check_week, import_week, validate_week


def _document(*, duplicate: bool = False) -> dict:
    entries = [
        {
            "date": "2026-09-07",
            "time_from": "3:50 PM",
            "time_to": "4:50 PM",
            "topic": "Synthetic topic",
            "cs_code": "2.1",
            "ls_code": "2.1.1",
            "activity_html": "<p>Synthetic activity</p>",
            "reflection_html": "<p>Synthetic reflection</p>",
            "notes_html": "",
        }
    ]
    if duplicate:
        entries.append(dict(entries[0]))
    return {"version": "1", "week": 31, "entry_count": len(entries), "entries": entries}


def _source(tmp_path: Path, document: dict) -> Path:
    path = tmp_path / "week.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _options() -> dict:
    return {
        "miw_id": "10",
        "class_id": "20",
        "setjadual": "30",
        "owner_id": "40",
        "grouplevelsubject": "cg_secondary-form2-english",
        "subject": "english",
        "session": "2026",
    }


def test_validate_week_is_local_and_omits_content(tmp_path: Path) -> None:
    result = validate_week(_source(tmp_path, _document()))
    rendered = json.dumps(result)
    assert result["mode"] == "dry-run"
    assert result["write_performed"] is False
    assert "Synthetic activity" not in rendered
    assert "Synthetic reflection" not in rendered


def test_cli_dry_run_never_creates_a_client(tmp_path: Path, monkeypatch, capsys) -> None:
    source = _source(tmp_path, _document())
    monkeypatch.setattr(cli, "_client", lambda args: pytest.fail("network client created"))
    assert cli.main(["import-week", str(source), "--dry-run"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["mode"] == "dry-run"


def test_duplicate_slot_has_stable_code(tmp_path: Path) -> None:
    with pytest.raises(CidsError) as raised:
        validate_week(_source(tmp_path, _document(duplicate=True)))
    assert raised.value.code == "IMPORT_DUPLICATE_SLOT"
    assert raised.value.exit_status == 2


class _CheckClient:
    def __init__(self, *, occupied: bool = False) -> None:
        self.occupied = occupied
        self.calls = []

    def request(self, method: str, path: str, **kwargs):
        self.calls.append((method, path, kwargs))
        if path.startswith("miw9.php?action=openmiw"):
            return SimpleNamespace(text=(
                '<form id="miwform"><input name="randomtoken" value="safe-token">'
                '<a href="miw9.php?action=openRPH&amp;rph=99">07-09-2026 3:50 PM</a>'
                "</form>"
            ))
        if path.startswith("miw9.php?action=editRPH"):
            return SimpleNamespace(text=(
                '<form id="miwform"><input name="randomtoken" value="safe-token">'
                '<textarea name="rph[PedToo][1][2]"></textarea></form>'
            ))
        if path == "fetch_userrequirement.php":
            return SimpleNamespace(text="occupied" if self.occupied else "empty")
        raise AssertionError(f"unexpected request: {method} {path}")


def test_check_uses_read_only_form_requests_and_no_mutating_post(tmp_path: Path) -> None:
    client = _CheckClient()
    result = check_week(client, _source(tmp_path, _document()), **_options())
    assert result["mode"] == "check"
    assert result["lessons"][0]["action"] == "update"
    assert not any(method == "POST" and path == "miw9.php" for method, path, _ in client.calls)


def test_full_preflight_stops_before_first_write_on_conflict(tmp_path: Path) -> None:
    document = _document()
    document["entries"][0]["date"] = "2026-09-08"
    client = _CheckClient(occupied=True)
    with pytest.raises(CidsError) as raised:
        import_week(client, _source(tmp_path, document), **_options())
    assert raised.value.code == "IMPORT_SLOT_OCCUPIED"
    assert not any(method == "POST" and path == "miw9.php" for method, path, _ in client.calls)


def test_cli_error_is_structured_and_content_safe(tmp_path: Path, capsys) -> None:
    source = tmp_path / "invalid.json"
    source.write_text("not-json Synthetic reflection", encoding="utf-8")
    assert cli.main(["import-week", str(source), "--dry-run"]) == 2
    error = capsys.readouterr().err
    parsed = json.loads(error)
    assert parsed["error"]["code"] == "IMPORT_JSON_INVALID"
    assert "Synthetic reflection" not in error


def test_cli_rejects_conflicting_modes_with_stable_code(tmp_path: Path, capsys) -> None:
    source = _source(tmp_path, _document())
    assert cli.main(["import-week", str(source), "--dry-run", "--yes"]) == 2
    parsed = json.loads(capsys.readouterr().err)
    assert parsed["error"]["code"] == "IMPORT_MODE_CONFLICT"


def test_cli_requires_confirmation_for_live_import(tmp_path: Path, capsys) -> None:
    source = _source(tmp_path, _document())
    argv = [
        "import-week", str(source),
        "--miw-id", "10", "--class-id", "20", "--setjadual", "30",
        "--owner-id", "40", "--grouplevelsubject", "cg_form2_english",
    ]
    assert cli.main(argv) == 6
    parsed = json.loads(capsys.readouterr().err)
    assert parsed["error"]["code"] == "CONFIRMATION_REQUIRED"
