import json
from types import SimpleNamespace

import pytest

from cids_cli import cli
from cids_cli.timetable import TIMETABLE_PATH


class _TimetableClient:
    def __init__(self, *, old_end="22-03-2027", flexible=False):
        self.old_end = old_end
        self.flexible = flexible
        self.calls = []

    def status(self):
        return True, None

    def request(self, method, path):
        assert method == "GET"
        self.calls.append(path)
        if path == TIMETABLE_PATH:
            selected = "2" if self.flexible else "1"
            return SimpleNamespace(text=f'''
                <input name="setjadual" value="62">
                <input name="bilastart" value="23-03-2027" disabled>
                <select name="anjal"><option value="{selected}" selected>Type</option></select>
                <input onclick="checkBeforeExit('location','teachers9.php?action=tutupjadual&amp;setjadual=62');">
                <ul id="teaching_period">
                  <li class="jadualaktif"><a onclick='checkBeforeExit("location","?action=waktumengajar&amp;setjadual=62&amp;user=73&amp;dbug=")'>Revision B</a></li>
                  <li><a onclick='checkBeforeExit("location","?action=waktumengajar&amp;setjadual=59&amp;user=73&amp;dbug=")'>01-03-2027 Revision A</a></li>
                </ul>
            ''')
        if path == f"{TIMETABLE_PATH}&setjadual=59&user=73":
            return SimpleNamespace(text=f'''
                <input name="setjadual" value="59">
                <input name="bilastart" value="01-03-2027" disabled>
                <input name="bilaend" value="{self.old_end}" disabled>
            ''')
        if path == "teachers9.php?action=semakjadual&setjadual=59":
            return SimpleNamespace(text='''
                <div class="period subject" data-day="1" data-timestart="8:00 AM"
                     data-timeend="9:00 AM" data-subject="Science" data-class="20" data-setjadual="59">
                  <b>Science</b><br>4 Bestari<br>8:00 AM - 9:00 AM
                </div>
            ''')
        if path == "teachers9.php?action=semakjadual&setjadual=62":
            return SimpleNamespace(text='''
                <div class="period subject" data-day="2" data-timestart="10:00 AM"
                     data-timeend="11:00 AM" data-subject="Science" data-class="20" data-setjadual="62">
                  <b>Science</b><br>4 Bestari<br>10:00 AM - 11:00 AM
                </div>
                <div class="period subject" data-day="2" data-timestart="1:00 PM"
                     data-timeend="2:00 PM" data-subject="Science" data-class="21" data-setjadual="62">
                  <b>Science</b><br>4 Gigih<br>1:00 PM - 2:00 PM
                </div>
            ''')
        pytest.fail(f"Unexpected request {path}")


def _periods(monkeypatch, capsys, client):
    monkeypatch.setattr(cli, "_client", lambda args: client)
    assert cli.main([
        "timetable-periods", "--date-from", "2027-03-22", "--date-to", "2027-03-24",
        "--class-id", "20", "--subject", "science",
    ]) == 0
    return json.loads(capsys.readouterr().out)["dates"]


def test_timetable_periods_use_each_revision_on_its_effective_dates(monkeypatch, capsys):
    client = _TimetableClient()
    before, after, no_periods = _periods(monkeypatch, capsys, client)
    assert before["timetable_ids"] == ["59"]
    assert before["periods"][0]["time_from"] == "8:00 AM"
    assert after["timetable_ids"] == ["62"]
    assert len(after["periods"]) == 1
    assert after["periods"][0]["class_name"] == "4 Bestari"
    assert after["periods"][0]["time_from"] == "10:00 AM"
    assert no_periods["status"] == "ready"
    assert no_periods["periods"] == []
    assert client.calls.count("teachers9.php?action=semakjadual&setjadual=62") == 1


@pytest.mark.parametrize(
    ("client_options", "index", "status"),
    [
        ({"old_end": "23-03-2027"}, 1, "ambiguous_timetable"),
        ({"old_end": "21-03-2027"}, 0, "timetable_unavailable"),
        ({"flexible": True}, 1, "flexible_timetable"),
    ],
)
def test_unresolved_timetable_dates_return_no_periods(monkeypatch, capsys, client_options, index, status):
    result = _periods(monkeypatch, capsys, _TimetableClient(**client_options))[index]
    assert result["status"] == status
    assert result["periods"] == []


def test_week_log_persists_school_numbering_and_breaks_without_network(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "_client", lambda args: pytest.fail("week log contacted CIDS"))

    assert cli.main(["week-log", "list", "--session", "2027"]) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert not (tmp_path / "cids-cli").exists()

    prefix = ["week-log", "set", "--session", "2027"]
    dates = ["--date-from", "2027-03-22", "--date-to", "2027-03-26"]
    assert cli.main(prefix + ["--week", "5"] + dates) == 0
    assert cli.main(prefix + ["--week", "6"] + dates) == 0
    assert cli.main(prefix + ["--no-teaching", "--date-from", "2027-03-29", "--date-to", "2027-04-02"]) == 0
    capsys.readouterr()

    assert cli.main(["week-log", "list", "--session", "2027", "--date", "2027-03-22"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["week"] == 6
    assert cli.main(["week-log", "list", "--session", "2027", "--date", "2027-04-02"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["week"] is None

    assert cli.main(prefix + ["--week", "7", "--date-from", "2027-03-25", "--date-to", "2027-03-27"]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "WEEK_LOG_OVERLAP"
