"""Agent-facing import contract tests using synthetic lesson data only."""

from __future__ import annotations

import html
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
                '<ul class="sitems standard_kandungan">'
                '<input type="checkbox" name="InsPro[21][301]" value="1" checked>'
                '<li class="sitem"><span>2.1</span> Synthetic standard</li></ul>'
                '<ul class="sitems standard_pembelajaran">'
                '<input type="checkbox" name="InsPro[22][302]" value="1" checked>'
                '<li class="sitem"><span>2.1.1</span> Synthetic standard</li></ul>'
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


class _ImportClient:
    objective_field = "content[712][]"

    def __init__(self, *, existing=False, has_editor=True, drop_objectives=False):
        self.existing = existing
        self.has_editor = has_editor
        self.drop_objectives = drop_objectives
        self.objectives = []
        self.calls = []
        self.writes = []
        self.edit_values = {}

    def request(self, method, path, **kwargs):
        data = kwargs.get("data", {})
        self.calls.append((method, path, data))
        if path.startswith("miw9.php?action=openmiw"):
            lesson = ('<a href="miw9.php?action=openRPH&amp;rph=99">'
                      '07-09-2026 03:50 PM</a>') if self.existing else ""
            return SimpleNamespace(text=(
                "<script>var miw_subject='sains'; var miw_sesi='2027';</script>"
                '<form id="miwform"><input name="randomtoken" value="safe-token">'
                '<input type="button" value="Cipta RPH" onclick="checkBeforeCreate(this)">'
                '<ul class="sitems standard_kandungan">'
                '<input type="checkbox" name="InsPro[71][301]" value="1" checked>'
                '<li class="sitem"><span>6.1</span> Bahan</li>'
                '<input type="checkbox" name="InsPro[71][309]" value="1" checked>'
                '<li class="sitem"><span>6.10</span> Bahan lain</li></ul>'
                '<ul class="sitems standard_pembelajaran">'
                '<input type="checkbox" name="InsPro[72][302]" value="1" checked>'
                '<li class="sitem"><span>6.1.2</span> Bandingkan bahan</li></ul>'
                '<ul class="sitems objektif_multitext">'
                '<input type="checkbox" name="InsPro[712][88]" value="1" checked>'
                '<li class="sitem">Unrelated objective</li></ul>'
                f"{lesson}</form>"
            ))
        if path.startswith("miw9.php?action=editRPH"):
            controls = ('<input name="randomtoken" value="safe-token">'
                        '<input name="ur[class_id]" value="20">'
                        '<input type="button" value="Simpan RPH" onclick="checkBeforeSave(this)">')
            for field in ("rph[PedToo][1][2]", "rph[catatan][1][2]", "rph[impak]"):
                content = html.escape(self.edit_values.get(field, ""))
                controls += f'<textarea name="{field}">{content}</textarea>'
            return SimpleNamespace(text=f'<form id="miwform">{controls}</form>')
        if method == "GET" and path.startswith("set9.php?action=instructional"):
            if not self.has_editor:
                return SimpleNamespace(text="<html>No profile editor</html>")
            scope = (
                '<input name="src" value="rph"><input name="rph" value="99">'
                '<input name="rphaction" value="edit">'
            ) if "&rph=" in path else ""
            saved = "".join(
                f'<input type="hidden" name="{self.objective_field}" value="{html.escape(value)}">'
                for value in self.objectives
            )
            return SimpleNamespace(text=(
                '<form id="new" action="set9.php" method="post">'
                '<input name="randomtoken" value="profile-token">'
                '<input name="action" value="savecontent"><input name="set" value="InsPro">'
                '<select multiple name="content[71][]">'
                '<option value="301" selected>Selected standard</option>'
                '<option value="302">Unselected standard</option>'
                '<option value="303" selected>Another selected standard</option>'
                '</select>'
                f'{scope}<div class="row type_multitext InsPro_item">'
                '<div class="il">Objektif Pembelajaran</div>'
                f'<ul class="chosen-choices" id="ul_712">{saved}'
                '<li><textarea id="new_712"></textarea></li></ul></div>'
                '<input type="submit" name="submit" value="Simpan"></form>'
            ))
        if path == "fetch_userrequirement.php":
            return SimpleNamespace(text="empty")
        if method == "POST" and path in {"miw9.php", "set9.php"}:
            self.writes.append((path, dict(data)))
            if path == "set9.php":
                if not self.drop_objectives:
                    self.objectives = data[self.objective_field]
            elif data["actionRPH"] == "createRPH":
                self.existing = True
                return SimpleNamespace(text='<p>RPH telah dicipta</p><input name="id" value="99">')
            else:
                self.edit_values = dict(data)
            return SimpleNamespace(text="")
        raise AssertionError(f"unexpected request: {method} {path}")


def _science_document():
    document = _document()
    document["entries"][0].update({
        "cs_code": "6.1", "ls_code": "6.1.2",
        "objectives": ["Kenal pasti dua bahan.", "Jelaskan kegunaan bahan & sifatnya."],
    })
    return document


def test_import_creates_in_another_curriculum_and_saves_objectives_in_knowledge_form(tmp_path):
    client = _ImportClient()
    document = _science_document()
    options = _options()
    options.pop("subject")
    options.pop("session")
    options["grouplevelsubject"] = "cg_primary-year4-sains"
    result = import_week(client, _source(tmp_path, document), **options)
    assert result["lessons"][0]["status"] == "created"
    assert result["lessons"][0]["objectives_verified"] == 2
    assert "Kenal pasti" not in json.dumps(result)

    (create_path, create), (profile_path, profile), (save_path, save) = client.writes
    assert (create_path, profile_path, save_path) == ("miw9.php", "set9.php", "miw9.php")
    assert (create["action"], profile["submit"], save["action"]) == ("Cipta RPH", "Simpan", "Simpan RPH")
    assert {key for key in create if key.startswith("InsPro[")} == {"InsPro[71][301]", "InsPro[72][302]"}
    assert any(path == "fetch_userrequirement.php" and payload["subject"] == "sains"
               and payload["sesi"] == "2027" for _, path, payload in client.calls)
    assert profile[client.objective_field] == document["entries"][0]["objectives"]
    assert profile["src"] == "rph"
    assert profile["rph"] == "99"
    assert profile["content[71][]"] == ["301", "303"]
    assert client.objective_field not in save


def test_existing_dlp_uses_native_objectives_for_html_input_and_skips_unchanged_objectives(tmp_path):
    document = _document()
    document["entries"][0]["objectives_html"] = "<ol><li>Explain A &amp; B</li><li>Give an example</li></ol>"
    client = _ImportClient(existing=True)
    source = _source(tmp_path, document)
    first = import_week(client, source, **_options())
    assert first["lessons"][0]["status"] == "updated"
    assert client.objectives == ["Explain A & B", "Give an example"]
    client.writes.clear()

    result = import_week(client, source, **_options())
    assert result["lessons"][0]["objectives_verified"] == 2
    assert all(path != "set9.php" for path, _ in client.writes)


def test_objective_verification_fails_when_cids_drops_content(tmp_path):
    client = _ImportClient(existing=True, drop_objectives=True)
    with pytest.raises(CidsError) as raised:
        import_week(client, _source(tmp_path, _science_document()), **_options())
    assert raised.value.code == "IMPORT_PARTIAL"
    assert raised.value.details["cause_code"] == "IMPORT_OBJECTIVES_NOT_PERSISTED"
    assert raised.value.details["lesson_id"] == "99"


@pytest.mark.parametrize("existing", [True, False])
def test_preflight_blocks_import_if_native_objective_editor_is_missing(tmp_path, existing):
    client = _ImportClient(existing=existing, has_editor=False)
    with pytest.raises(CidsError) as raised:
        import_week(client, _source(tmp_path, _science_document()), **_options())
    assert raised.value.code == "IMPORT_OBJECTIVES_FORM_UNAVAILABLE"
    assert not client.writes


def test_legacy_entry_keeps_existing_objectives(tmp_path):
    client = _ImportClient(existing=True)
    client.objectives = ["Existing teacher objective"]
    import_week(client, _source(tmp_path, _document()), **_options())
    assert client.objectives == ["Existing teacher objective"]
    assert all(not path.startswith("set9.php") for _, path, _ in client.calls)


def test_dry_run_reports_objective_count_and_accepts_other_curricula(tmp_path):
    result = validate_week(_source(tmp_path, _science_document()))
    assert result["lessons"][0]["cs_code"] == "6.1"
    assert result["lessons"][0]["objective_count"] == 2
    assert "Kenal pasti" not in json.dumps(result)


def test_preflight_rejects_a_standard_missing_from_the_miw(tmp_path):
    document = _science_document()
    document["entries"][0]["cs_code"] = "6.11"
    client = _ImportClient()
    with pytest.raises(CidsError) as raised:
        import_week(client, _source(tmp_path, document), **_options())
    assert raised.value.code == "IMPORT_STANDARD_NOT_FOUND"
    assert raised.value.details["field"] == "cs_code"
    assert not client.writes


def test_noninteractive_login_without_credentials_fails_before_network(monkeypatch, capsys):
    monkeypatch.delenv("CIDS_USERNAME", raising=False)
    monkeypatch.delenv("CIDS_PASSWORD", raising=False)
    monkeypatch.setattr(cli, "_client", lambda args: pytest.fail("network client created"))
    assert cli.main(["auth", "login", "--non-interactive"]) == 3
    assert "AUTH_CREDENTIALS_MISSING" in capsys.readouterr().err
