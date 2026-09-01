"""Import a generated weekly lesson JSON file into an existing CIDS MIW."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from importlib import resources
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from jsonschema import Draft202012Validator, FormatChecker

from .client import CidsClient, CidsError


# Browser-resolved Form 2 English curriculum relationships. These are server
# option identifiers, not user or record identifiers.
FORM2_ENGLISH: Mapping[Tuple[str, str], Tuple[str, ...]] = {
    ("2.1", "2.1.1"): (
        "InsPro[3][23207]", "InsPro[8][23268]",
        "InsPro[938][23277]", "InsPro[9][23288]",
    ),
    ("3.1", "3.1.2"): (
        "InsPro[3][23502]", "InsPro[8][23503]",
        "InsPro[938][23507]", "InsPro[9][23529]",
    ),
    ("4.1", "4.1.3"): (
        "InsPro[3][23581]", "InsPro[8][23582]",
        "InsPro[938][23586]", "InsPro[9][23591]",
    ),
}


@dataclass(frozen=True)
class LessonEntry:
    date: str
    time_from: str
    time_to: str
    topic: str
    cs_code: str
    ls_code: str
    activity_html: str
    reflection_html: str
    notes_html: str

    @property
    def cids_date(self) -> str:
        year, month, day = self.date.split("-")
        return f"{day}-{month}-{year}"


@dataclass(frozen=True)
class LessonPlan:
    entry: LessonEntry
    action: str
    lesson_id: Optional[str] = None


def _import_error(
    code: str,
    message: str,
    *,
    exit_status: int = 2,
    details: Optional[Mapping[str, Any]] = None,
) -> CidsError:
    return CidsError(message, code=code, exit_status=exit_status, details=details)


class _FormParser(HTMLParser):
    def __init__(self, wanted_id: str = "miwform") -> None:
        super().__init__()
        self.wanted_id = wanted_id
        self.in_form = False
        self.payload: Dict[str, Any] = {}
        self._textarea: Optional[str] = None

    def _add(self, name: str, value: str) -> None:
        if name not in self.payload:
            self.payload[name] = value
        elif isinstance(self.payload[name], list):
            self.payload[name].append(value)
        else:
            self.payload[name] = [self.payload[name], value]

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        values = dict(attrs)
        if tag == "form":
            self.in_form = values.get("id") == self.wanted_id
            return
        if not self.in_form:
            return
        name = values.get("name")
        if not name:
            return
        if tag == "input":
            kind = (values.get("type") or "text").lower()
            if kind in {"button", "submit", "reset", "file"}:
                return
            if kind in {"checkbox", "radio"} and "checked" not in values:
                return
            self._add(name, values.get("value") or "")
        elif tag == "textarea":
            self._textarea = name
            self._add(name, "")

    def handle_data(self, data: str) -> None:
        if self.in_form and self._textarea:
            current = self.payload[self._textarea]
            if isinstance(current, list):
                current[-1] += data
            else:
                self.payload[self._textarea] = current + data

    def handle_endtag(self, tag: str) -> None:
        if tag == "textarea":
            self._textarea = None
        elif tag == "form" and self.in_form:
            self.in_form = False


def _form_payload(page: str) -> Dict[str, Any]:
    parser = _FormParser()
    parser.feed(page)
    if not parser.payload:
        raise _import_error(
            "IMPORT_FORM_NOT_FOUND",
            "The expected CIDS lesson form was not found.",
            exit_status=5,
        )
    return parser.payload


def _load_entries(path: Path) -> Tuple[int, List[LessonEntry]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _import_error(
            "IMPORT_SOURCE_UNREADABLE",
            f"Could not read weekly lesson JSON: {exc}",
        ) from None
    except ValueError:
        raise _import_error(
            "IMPORT_JSON_INVALID",
            "Weekly lesson file is not valid JSON.",
        ) from None

    schema = json.loads(
        resources.files("cids_cli").joinpath("week_import.schema.json").read_text(encoding="utf-8")
    )
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(raw),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        field = ".".join(str(part) for part in error.absolute_path) or "$"
        raise _import_error(
            "IMPORT_SCHEMA_INVALID",
            f"Weekly lesson JSON failed schema validation at {field}.",
            details={"field": field, "issue": error.validator},
        )

    entries: List[LessonEntry] = []
    required = (
        "date", "time_from", "time_to", "topic", "cs_code", "ls_code",
        "activity_html", "reflection_html", "notes_html",
    )
    for index, item in enumerate(raw["entries"], 1):
        entry = LessonEntry(**{key: str(item[key]) for key in required})
        if (entry.cs_code, entry.ls_code) not in FORM2_ENGLISH:
            raise _import_error(
                "IMPORT_UNSUPPORTED_STANDARD",
                f"Entry {index} uses unsupported Form 2 English standards "
                f"{entry.cs_code}/{entry.ls_code}.",
                details={"entry": index, "cs_code": entry.cs_code, "ls_code": entry.ls_code},
            )
        start = datetime.strptime(entry.time_from, "%I:%M %p")
        end = datetime.strptime(entry.time_to, "%I:%M %p")
        if end <= start:
            raise _import_error(
                "IMPORT_TIME_RANGE_INVALID",
                f"Entry {index} must end after it starts.",
                details={"entry": index},
            )
        entries.append(entry)
    declared = raw.get("entry_count")
    if declared is not None and declared != len(entries):
        raise _import_error(
            "IMPORT_ENTRY_COUNT_MISMATCH",
            "entry_count does not match the entries array.",
            details={"declared": declared, "actual": len(entries)},
        )
    slots = [(entry.date, entry.time_from, entry.time_to) for entry in entries]
    if len(slots) != len(set(slots)):
        raise _import_error(
            "IMPORT_DUPLICATE_SLOT",
            "Weekly lesson JSON contains a duplicate date and time slot.",
        )
    return raw["week"], entries


def _safe_lessons(entries: List[LessonEntry], *, action: str = "sync") -> List[Mapping[str, Any]]:
    return [
        {
            "index": index,
            "date": entry.date,
            "time_from": entry.time_from,
            "time_to": entry.time_to,
            "cs_code": entry.cs_code,
            "ls_code": entry.ls_code,
            "action": action,
            "status": "planned",
        }
        for index, entry in enumerate(entries, 1)
    ]


def validate_week(source: Path) -> Mapping[str, Any]:
    """Perform local-only schema and semantic validation."""
    week, entries = _load_entries(source)
    return {
        "ok": True,
        "mode": "dry-run",
        "write_performed": False,
        "week": week,
        "entry_count": len(entries),
        "lessons": _safe_lessons(entries),
        "warnings": [],
    }


def _validate_identifiers(
    *,
    miw_id: str,
    class_id: str,
    setjadual: str,
    owner_id: str,
    grouplevelsubject: str,
    session: str,
) -> None:
    identifiers = {
        "miw_id": miw_id,
        "class_id": class_id,
        "setjadual": setjadual,
        "owner_id": owner_id,
        "session": session,
    }
    invalid = [name for name, value in identifiers.items() if not str(value).isdigit()]
    if invalid:
        raise _import_error(
            "IMPORT_IDENTIFIER_INVALID",
            "Numeric identifier required for: " + ", ".join(invalid),
            details={"fields": invalid},
        )
    if not re.fullmatch(r"[A-Za-z0-9_-]+", grouplevelsubject):
        raise _import_error(
            "IMPORT_IDENTIFIER_INVALID",
            "grouplevelsubject contains unsupported characters.",
            details={"fields": ["grouplevelsubject"]},
        )


def _existing_lessons(page: str) -> Dict[Tuple[str, str], str]:
    result: Dict[Tuple[str, str], str] = {}
    pattern = re.compile(
        r"href=['\"]miw9\.php\?action=openRPH(?:&amp;|&)rph=(\d+)['\"][^>]*>"
        r"(.*?)</a>",
        re.I | re.S,
    )
    for lesson_id, label_html in pattern.findall(page):
        label = html.unescape(re.sub(r"<[^>]+>", " ", label_html))
        label = " ".join(label.split())
        matched = re.search(r"(\d{2}-\d{2}-\d{4})\s+(\d{1,2}:\d{2}\s+[AP]M)", label, re.I)
        if matched:
            result[(matched.group(1), matched.group(2).upper())] = lesson_id
    return result


def _check_preconditions(
    client: CidsClient,
    source: Path,
    *,
    miw_id: str,
    class_id: str,
    setjadual: str,
    owner_id: str,
    grouplevelsubject: str,
    subject: str,
    session: str,
) -> Tuple[int, List[LessonEntry], List[LessonPlan]]:
    _validate_identifiers(
        miw_id=miw_id,
        class_id=class_id,
        setjadual=setjadual,
        owner_id=owner_id,
        grouplevelsubject=grouplevelsubject,
        session=session,
    )
    week, entries = _load_entries(source)
    miw = client.request("GET", f"miw9.php?action=openmiw&id={miw_id}")
    base_payload = _form_payload(miw.text)
    existing = _existing_lessons(miw.text)
    plans: List[LessonPlan] = []

    for index, entry in enumerate(entries, 1):
        key = (entry.cids_date, entry.time_from.upper())
        lesson_id = existing.get(key)
        if lesson_id:
            editable = client.request(
                "GET",
                f"miw9.php?action=editRPH&rph={lesson_id}&rphFormat=a&src=",
            )
            payload = _form_payload(editable.text)
            if not payload.get("randomtoken") or not any(
                name.startswith("rph[PedToo]") for name in payload
            ):
                raise _import_error(
                    "IMPORT_EDIT_FORM_UNAVAILABLE",
                    f"Entry {index} cannot be opened as an editable DLP.",
                    exit_status=5,
                    details={"entry": index, "date": entry.date, "time_from": entry.time_from},
                )
            plans.append(LessonPlan(entry, "update", lesson_id))
            continue

        if not base_payload.get("randomtoken"):
            raise _import_error(
                "IMPORT_TOKEN_MISSING",
                "The MIW creation form does not contain a current request token.",
                exit_status=5,
            )
        slot = client.request("POST", "fetch_userrequirement.php", data={
            "get_option": "", "rphdate": entry.cids_date,
            "user_id": owner_id, "sesi": session, "subject": subject,
            "learners": class_id, "time_from": entry.time_from,
            "time_to": entry.time_to,
        }).text.strip()
        if slot not in {"empty", "not_exist"}:
            raise _import_error(
                "IMPORT_SLOT_OCCUPIED",
                f"Entry {index} conflicts with an occupied CIDS slot.",
                exit_status=5,
                details={"entry": index, "date": entry.date, "time_from": entry.time_from},
            )
        plans.append(LessonPlan(entry, "create"))
    return week, entries, plans


def check_week(
    client: CidsClient,
    source: Path,
    **options: str,
) -> Mapping[str, Any]:
    """Run authenticated, read-only remote preflight checks."""
    week, entries, plans = _check_preconditions(client, source, **options)
    lessons = []
    for index, plan in enumerate(plans, 1):
        item: Dict[str, Any] = {
            "index": index,
            "date": plan.entry.date,
            "time_from": plan.entry.time_from,
            "time_to": plan.entry.time_to,
            "action": plan.action,
            "status": "ready",
        }
        if plan.lesson_id:
            item["lesson_id"] = plan.lesson_id
        lessons.append(item)
    return {
        "ok": True,
        "mode": "check",
        "write_performed": False,
        "week": week,
        "entry_count": len(entries),
        "lessons": lessons,
        "warnings": [],
    }


def _success(page: str, *phrases: str) -> bool:
    normalized = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split()).lower()
    return any(phrase.lower() in normalized for phrase in phrases)


def _markup_text(value: str) -> str:
    """Normalize rich-text HTML for persistence checks."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value)).split())


def _markup_words(value: str) -> str:
    """Ignore harmless punctuation rewrites performed by the rich-text editor."""
    return " ".join(re.findall(r"\w+", _markup_text(value).casefold()))


def _create_lesson(
    client: CidsClient,
    miw_page: str,
    entry: LessonEntry,
    *,
    class_id: str,
    setjadual: str,
    owner_id: str,
    grouplevelsubject: str,
) -> Tuple[str, str]:
    payload = _form_payload(miw_page)
    for key in list(payload):
        if key.startswith("InsPro["):
            del payload[key]
    for key in FORM2_ENGLISH[(entry.cs_code, entry.ls_code)]:
        payload[key] = "1"
    payload.update({
        "class_id": class_id,
        "rph[date]": entry.cids_date,
        "rph[time_from]": entry.time_from,
        "rph[time_to]": entry.time_to,
        "rph[setjadual]": setjadual,
        "actionRPH": "createRPH",
        "id": "",
        "owner_id": owner_id,
        "grouplevelsubject": grouplevelsubject,
        "action": "Create DLP",
    })
    response = client.request("POST", "miw9.php", data=payload)
    if not _success(response.text, "DLP has been created"):
        raise _import_error(
            "IMPORT_CREATE_NOT_CONFIRMED",
            f"CIDS did not confirm creation for {entry.date} {entry.time_from}.",
            exit_status=5,
        )
    match = re.search(r"name=['\"]id['\"][^>]+value=['\"](\d+)['\"]", response.text, re.I)
    if not match:
        match = re.search(r"openRPH(?:&amp;|&)rph=(\d+)", response.text, re.I)
    if not match:
        raise _import_error(
            "IMPORT_LESSON_ID_UNRESOLVED",
            "Created DLP but could not resolve its identifier.",
            exit_status=5,
        )
    return match.group(1), response.text


def _save_lesson(client: CidsClient, lesson_id: str, page: str, entry: LessonEntry) -> None:
    payload = _form_payload(page)
    activity_fields = [key for key in payload if key.startswith("rph[PedToo]")]
    notes_fields = [key for key in payload if key.startswith("rph[catatan]")]
    if not activity_fields:
        # A normal GET opens read-only DLP mode. The site's Edit DLP button
        # navigates directly to this GET endpoint to expose editable fields.
        editable = client.request(
            "GET",
            f"miw9.php?action=editRPH&rph={lesson_id}&rphFormat=a&src=",
        )
        payload = _form_payload(editable.text)
        activity_fields = [key for key in payload if key.startswith("rph[PedToo]")]
        notes_fields = [key for key in payload if key.startswith("rph[catatan]")]
    if not activity_fields:
        raise _import_error(
            "IMPORT_EDIT_FORM_UNAVAILABLE",
            f"DLP {lesson_id} could not be opened in edit mode.",
            exit_status=5,
        )
    if not payload.get("randomtoken"):
        raise _import_error(
            "IMPORT_TOKEN_MISSING",
            f"DLP {lesson_id} edit form has no request token.",
            exit_status=5,
        )
    payload[activity_fields[0]] = entry.activity_html
    topic = f"<p><strong>Topic:</strong> {html.escape(entry.topic)}</p>"
    if entry.notes_html:
        topic += entry.notes_html
    if notes_fields:
        payload[notes_fields[0]] = topic
    payload["rph[impak]"] = entry.reflection_html
    payload["id"] = lesson_id
    payload["actionRPH"] = "simpanRPH"
    payload["action"] = "Save DLP"
    client.request("POST", "miw9.php", data=payload)

    # Always verify persisted values; success banners vary by deployment and do
    # not prove that the rich-text fields survived server-side normalization.
    verified_page = client.request(
        "GET",
        f"miw9.php?action=editRPH&rph={lesson_id}&rphFormat=a&src=",
    )
    verified = _form_payload(verified_page.text)
    saved_activities = [
        _markup_words(str(value)) for key, value in verified.items()
        if key.startswith("rph[PedToo]")
    ]
    reflection = _markup_words(str(verified.get("rph[impak]", "")))
    if _markup_words(entry.activity_html) not in saved_activities or reflection != _markup_words(entry.reflection_html):
        raise _import_error(
            "IMPORT_NOT_PERSISTED",
            f"CIDS did not persist the content for DLP {lesson_id}.",
            exit_status=5,
        )


def import_week(
    client: CidsClient,
    source: Path,
    *,
    miw_id: str,
    class_id: str,
    setjadual: str,
    owner_id: str,
    grouplevelsubject: str,
    subject: str = "english",
    session: str = "2026",
) -> Mapping[str, Any]:
    options = {
        "miw_id": miw_id,
        "class_id": class_id,
        "setjadual": setjadual,
        "owner_id": owner_id,
        "grouplevelsubject": grouplevelsubject,
        "subject": subject,
        "session": session,
    }
    week, entries, plans = _check_preconditions(client, source, **options)
    imported: List[Mapping[str, Any]] = []
    mutation_attempted = False

    for index, plan in enumerate(plans, 1):
        entry = plan.entry
        try:
            if plan.action == "update" and plan.lesson_id:
                lesson_id = plan.lesson_id
                lesson_page = client.request(
                    "GET",
                    f"miw9.php?action=editRPH&rph={lesson_id}&rphFormat=a&src=",
                ).text
                result = "updated"
                mutation_attempted = True
            else:
                miw = client.request("GET", f"miw9.php?action=openmiw&id={miw_id}")
                mutation_attempted = True
                lesson_id, lesson_page = _create_lesson(
                    client, miw.text, entry, class_id=class_id,
                    setjadual=setjadual, owner_id=owner_id,
                    grouplevelsubject=grouplevelsubject,
                )
                result = "created"
            _save_lesson(client, lesson_id, lesson_page, entry)
            imported.append({
                "index": index,
                "date": entry.date,
                "time_from": entry.time_from,
                "time_to": entry.time_to,
                "lesson_id": lesson_id,
                "action": plan.action,
                "status": result,
            })
        except CidsError as exc:
            if mutation_attempted:
                raise _import_error(
                    "IMPORT_PARTIAL",
                    "The import stopped after writes began; inspect completed entries before retrying.",
                    exit_status=7,
                    details={
                        "completed": len(imported),
                        "failed_entry": index,
                        "cause_code": exc.code,
                    },
                ) from None
            raise
    return {
        "ok": True,
        "mode": "import",
        "write_performed": bool(imported),
        "week": week,
        "entry_count": len(entries),
        "lessons": imported,
        "warnings": [],
    }
