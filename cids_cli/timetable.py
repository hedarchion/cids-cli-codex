"""Resolve dated teaching periods from the teacher's CIDS timetable revisions."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from .client import CidsClient, CidsError


TIMETABLE_PATH = "teachers9.php?action=waktumengajar"


@dataclass(frozen=True)
class Timetable:
    id: str
    first_day: date
    last_day: Optional[date]
    flexible: bool

    def covers(self, day: date) -> bool:
        return self.first_day <= day and (self.last_day is None or day <= self.last_day)


def _cids_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%d-%m-%Y").date()
    except ValueError:
        raise CidsError(
            "CIDS provided an unreadable timetable date.", code="TIMETABLE_DATE_INVALID", exit_status=5,
        ) from None


def _timetable_id(page: BeautifulSoup) -> Optional[str]:
    field = page.select_one('input[name="setjadual"][value]')
    value = field.get("value", "") if field is not None else ""
    return value if re.fullmatch(r"[1-9][0-9]*", value) else None


def _timetable(page: BeautifulSoup, expected_id: str) -> Optional[Timetable]:
    effective = page.select_one('input[name="bilastart"][value]')
    ended = page.select_one('input[name="bilaend"][value]')
    active = page.select_one('[onclick*="action=tutupjadual"]')
    if _timetable_id(page) != expected_id or effective is None:
        raise CidsError(
            "CIDS did not return the expected timetable settings.", code="TIMETABLE_FORM_UNAVAILABLE",
            exit_status=5,
        )
    if ended is None and active is None:
        return None  # A saved draft has an effective date but has never been activated.
    flexible = page.select_one('select[name="anjal"] option[selected]')
    return Timetable(
        expected_id, _cids_date(effective["value"]),
        _cids_date(ended["value"]) if ended is not None and ended["value"] else None,
        flexible is not None and flexible.get("value") in {"2", "3"},
    )


def _timetables(client: CidsClient) -> List[Timetable]:
    page = BeautifulSoup(client.request("GET", TIMETABLE_PATH).text, "html.parser")
    menu = page.select_one("#teaching_period")
    if menu is None:
        raise CidsError("CIDS timetable history is unavailable.", code="TIMETABLE_FORM_UNAVAILABLE", exit_status=5)
    current_id = _timetable_id(page)
    candidates = {}
    if current_id:
        candidates[current_id] = TIMETABLE_PATH
    for link in menu.select('a[onclick*="setjadual="]'):
        found = re.search(r"[?&]setjadual=([1-9][0-9]*)(?:&|['\"])", link["onclick"])
        if not found:
            continue
        path = f"{TIMETABLE_PATH}&setjadual={found[1]}"
        owner = re.search(r"&user=([0-9]+)(?:&|['\"])", link["onclick"])
        if owner:
            path += f"&user={owner[1]}"
        candidates.setdefault(found[1], path)

    timetables = []
    for candidate, path in candidates.items():
        settings = page if candidate == current_id else BeautifulSoup(
            client.request("GET", path).text, "html.parser",
        )
        timetable = _timetable(settings, candidate)
        if timetable is not None:
            timetables.append(timetable)
    return timetables


def _periods(client: CidsClient, timetable_id: str) -> List[Dict[str, str]]:
    path = f"teachers9.php?action=semakjadual&setjadual={timetable_id}"
    page = BeautifulSoup(client.request("GET", path).text, "html.parser")
    periods = []
    for period in page.select(".period.subject[data-day][data-timestart][data-timeend][data-subject][data-class]"):
        if period.get("data-setjadual") != timetable_id or period["data-day"] not in {"0", "1", "2", "3", "4", "5", "6"}:
            continue
        subject_label = period.find("b", recursive=False)
        labels = list(period.stripped_strings)
        periods.append({
            "weekday": period["data-day"],
            "time_from": period["data-timestart"],
            "time_to": period["data-timeend"],
            "subject": period["data-subject"],
            "class_id": period["data-class"],
            "class_name": labels[1] if subject_label is not None and len(labels) > 2 else "",
        })
    return periods


def timetable_periods(
    client: CidsClient, first_day: date, last_day: date,
    *, class_id: Optional[str] = None, subject: Optional[str] = None,
) -> dict:
    if last_day < first_day:
        raise CidsError("The date range ends before it starts.", code="DATE_RANGE_INVALID", exit_status=2)

    timetables = _timetables(client)
    revisions: Dict[str, List[Dict[str, str]]] = {}
    dates = []
    for offset in range((last_day - first_day).days + 1):
        day = first_day + timedelta(days=offset)
        matches = [timetable for timetable in timetables if timetable.covers(day)]
        result = {"date": day.isoformat(), "timetable_ids": [match.id for match in matches], "periods": []}
        if not matches:
            result["status"] = "timetable_unavailable"
        elif len(matches) > 1:
            result["status"] = "ambiguous_timetable"
        elif matches[0].flexible:
            result["status"] = "flexible_timetable"
        else:
            timetable_id = matches[0].id
            if timetable_id not in revisions:
                revisions[timetable_id] = _periods(client, timetable_id)
            periods = revisions[timetable_id]
            result["status"] = "ready" if periods else "periods_unavailable"
            result["periods"] = [
                {key: value for key, value in period.items() if key != "weekday"}
                for period in periods
                if period["weekday"] == str(day.isoweekday() % 7)
                and (class_id is None or period["class_id"] == class_id)
                and (subject is None or period["subject"].casefold() == subject.casefold())
            ]
        dates.append(result)
    return {"dates": dates}
