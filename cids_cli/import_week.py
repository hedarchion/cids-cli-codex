"""Import a generated weekly lesson JSON file into an existing CIDS MIW."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from bs4 import BeautifulSoup, Tag
from jsonschema import Draft202012Validator, FormatChecker

from .client import CidsClient, CidsError, ResponseData
from .forms import FormValues, find_form, form_values


# These related Learning Area and Focus choices were observed on the original
# Form 2 English MIWs. Use them only if present alongside the matched standards.
LEGACY_RELATED_CHOICES = {
    ("InsPro[8][23268]", "InsPro[9][23288]"): ("InsPro[3][23207]", "InsPro[938][23277]"),
    ("InsPro[8][23503]", "InsPro[9][23529]"): ("InsPro[3][23502]", "InsPro[938][23507]"),
    ("InsPro[8][23582]", "InsPro[9][23591]"): ("InsPro[3][23581]", "InsPro[938][23586]"),
}
OBJECTIVE_KEYS = ("objectives", "objectives_html", "objective_html",
                  "learning_objectives", "lesson_objectives")
PostForm = Callable[[str, FormValues], ResponseData]


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
    objectives: Optional[Tuple[str, ...]] = None

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


def _lesson_form(page: str) -> Tag:
    form = find_form(page, "miwform")
    if form is None:
        raise _import_error(
            "IMPORT_FORM_NOT_FOUND",
            "The expected CIDS lesson form was not found.",
            exit_status=5,
        )
    return form


def week_schema() -> Mapping[str, Any]:
    return json.loads(
        resources.files("cids_cli").joinpath("week_import.schema.json").read_text(encoding="utf-8")
    )


def _objectives(item: Mapping[str, Any], index: int) -> Optional[Tuple[str, ...]]:
    fields = [key for key in OBJECTIVE_KEYS if key in item]
    if not fields:
        return None
    if len(fields) != 1:
        raise _import_error(
            "IMPORT_OBJECTIVES_INVALID",
            f"Entry {index} must supply objectives in one field.",
            details={"entry": index, "fields": fields},
        )
    supplied = item[fields[0]]
    if isinstance(supplied, str):
        markup = BeautifulSoup(supplied, "html.parser")
        for line_break in markup.find_all("br"):
            line_break.replace_with("\n")
        items = markup.select("li") or markup.select("p")
        supplied = [node.get_text() for node in items] if items else markup.get_text().splitlines()
    objectives = tuple(" ".join(value.split()) for value in supplied)
    if not objectives or not all(objectives) or len(set(objectives)) != len(objectives):
        raise _import_error(
            "IMPORT_OBJECTIVES_INVALID",
            f"Entry {index} requires distinct, non-blank objectives.",
            details={"entry": index, "field": fields[0]},
        )
    return objectives


def _time_key(value: str) -> int:
    hour, minute, period = re.fullmatch(r"(\d{1,2}):(\d{2})\s+([AP]M)", value, re.I).groups()
    return (int(hour) % 12 + 12 * (period.upper() == "PM")) * 60 + int(minute)


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

    errors = sorted(
        Draft202012Validator(week_schema(), format_checker=FormatChecker()).iter_errors(raw),
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
        "date", "time_from", "time_to", "topic",
        "activity_html", "reflection_html", "notes_html",
    )
    for index, item in enumerate(raw["entries"], 1):
        entry = LessonEntry(
            **{key: item[key] for key in required},
            cs_code=item.get("cs_code", "").strip(), ls_code=item.get("ls_code", "").strip(),
            objectives=_objectives(item, index),
        )
        start = _time_key(entry.time_from)
        end = _time_key(entry.time_to)
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
    slots = [(entry.date, _time_key(entry.time_from)) for entry in entries]
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
            "objective_count": len(entry.objectives or ()),
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
    session: Optional[str],
) -> None:
    identifiers = {
        "miw_id": miw_id,
        "class_id": class_id,
        "setjadual": setjadual,
        "owner_id": owner_id,
    }
    if session is not None:
        identifiers["session"] = session
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


def _existing_lessons(page: str) -> Dict[Tuple[str, int], List[str]]:
    result: Dict[Tuple[str, int], List[str]] = {}
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
            key = (matched.group(1), _time_key(matched.group(2)))
            ids = result.setdefault(key, [])
            if lesson_id not in ids:
                ids.append(lesson_id)
    return result


def _standards_for(form: Tag, entry: LessonEntry, index: int) -> FormValues:
    controls = form.select('input[type="checkbox"][name^="InsPro["]:not([disabled])')
    choices = {}
    for classes, heading, code in (
        (".standard_kandungan, .content_standard", "cs_code", entry.cs_code),
        (".standard_pembelajaran, .learning_standard", "ls_code", entry.ls_code),
    ):
        if not code:
            continue
        matches = {}
        for group in form.select(classes):
            for control in group.select('input[type="checkbox"][name^="InsPro["]:not([disabled])'):
                label = control.find_next_sibling()
                if label is None or label.name not in {"li", "label"}:
                    continue
                text = label.get_text(" ", strip=True)
                code_span = label.find("span", recursive=False)
                prefix = code_span.get_text(" ", strip=True) if code_span is not None else ""
                if (code.casefold() == text.casefold()
                        or code.casefold() == prefix.casefold()
                        or re.match(rf"^(?:[\w-]+:\s*)?{re.escape(code)}(?=\s|:|$)", text, re.I)):
                    matches[control["name"]] = control.get("value", "on")
        if len(matches) != 1:
            raise _import_error(
                "IMPORT_STANDARD_AMBIGUOUS" if matches else "IMPORT_STANDARD_NOT_FOUND",
                f"Entry {index} needs a unique {heading} choice in the target MIW.",
                exit_status=5,
                details={"entry": index, "field": heading},
            )
        choices.update(matches)
    related = LEGACY_RELATED_CHOICES.get(tuple(choices), ())
    for control in controls:
        if control["name"] in related:
            choices[control["name"]] = control.get("value", "on")
    return choices


def _edit_path(lesson_id: str) -> str:
    return f"miw9.php?action=editRPH&rph={lesson_id}&rphFormat=a&src="


def _profile_path(lesson_id: Optional[str]) -> str:
    path = "set9.php?action=instructional"
    if lesson_id is not None:
        path += f"&src=rph&rph={lesson_id}&rphaction=edit"
    return path


def _objective_profile(
    client: CidsClient, lesson_id: Optional[str], index: int,
) -> Tuple[FormValues, str]:
    page = client.request("GET", _profile_path(lesson_id)).text
    form = find_form(page, "new")
    payload = form_values(form) if form is not None else {}
    expected = {"action": "savecontent", "set": "InsPro"}
    if lesson_id is not None:
        expected.update({"src": "rph", "rph": lesson_id, "rphaction": "edit"})
    if (form is None or form.get("action") != "set9.php" or not payload.get("randomtoken")
            or any(payload.get(key) != value for key, value in expected.items())):
        raise _import_error(
            "IMPORT_OBJECTIVES_FORM_UNAVAILABLE",
            f"Entry {index} could not open the expected CIDS Knowledge form.",
            exit_status=5,
            details={"entry": index},
        )
    submit = form.select_one('input[type="submit"][name="submit"], button[type="submit"][name="submit"]')
    if submit is not None:
        payload["submit"] = submit.get("value", "")
    fields = []
    for row in form.select(".InsPro_item.type_multitext"):
        label = row.select_one(".il")
        if not row.select_one('[class*="objektif_multitext"]') and (
            label is None or label.get_text(" ", strip=True).casefold() not in {
                "learning objective", "learning objectives", "lesson objective",
                "lesson objectives", "objektif pembelajaran", "objektif pelajaran",
            }
        ):
            continue
        for widget in row.select('ul.chosen-choices[id^="ul_"]'):
            group = re.fullmatch(r"ul_(\d+)", widget["id"])
            if group and widget.select_one(f'textarea[id="new_{group[1]}"]:not([disabled])'):
                fields.append(f"content[{group[1]}][]")
    if len(fields) != 1:
        raise _import_error(
            "IMPORT_OBJECTIVES_FIELD_UNAVAILABLE",
            f"Entry {index} needs one editable Learning Objectives field in CIDS.",
            exit_status=5,
            details={"entry": index},
        )
    return payload, fields[0]


def _miw_defaults(page: str, subject: Optional[str], session: Optional[str]) -> Tuple[str, str]:
    values = {"subject": subject, "sesi": session}
    for key, value in values.items():
        if not value:
            match = re.search(rf"\bmiw_{key}\s*=\s*(['\"])(.*?)\1", page)
            if match:
                values[key] = html.unescape(match.group(2)).strip()
    if not values["subject"] or not re.fullmatch(r"[0-9]+", values["sesi"] or ""):
        raise _import_error(
            "IMPORT_CONTEXT_MISSING",
            "Could not determine the subject or session from the MIW. Supply --subject and --session.",
            exit_status=5,
        )
    return values["subject"], values["sesi"]


def _check_slot(
    client: CidsClient, entry: LessonEntry, index: int,
    *, owner_id: str, class_id: str, subject: str, session: str,
) -> None:
    slot = client.request("POST", "fetch_userrequirement.php", data={
        "get_option": "", "rphdate": entry.cids_date,
        "user_id": owner_id, "sesi": session, "subject": subject,
        "learners": class_id, "time_from": entry.time_from, "time_to": entry.time_to,
    }).text.strip()
    if slot not in {"empty", "not_exist"}:
        raise _import_error(
            "IMPORT_SLOT_OCCUPIED",
            f"Entry {index} conflicts with an occupied CIDS slot.",
            exit_status=5,
            details={"entry": index, "date": entry.date, "time_from": entry.time_from},
        )


def _check_preconditions(
    client: CidsClient,
    source: Path,
    *,
    miw_id: str,
    class_id: str,
    setjadual: str,
    owner_id: str,
    grouplevelsubject: str,
    subject: Optional[str] = None,
    session: Optional[str] = None,
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
    form = _lesson_form(miw.text)
    base_payload = form_values(form)
    existing = _existing_lessons(miw.text)
    plans: List[LessonPlan] = []
    checked_objectives_form = False
    slot_context = None

    for index, entry in enumerate(entries, 1):
        key = (entry.cids_date, _time_key(entry.time_from))
        matches = []
        for lesson_id in existing.get(key, ()):
            editable = client.request("GET", _edit_path(lesson_id))
            payload = form_values(_lesson_form(editable.text))
            existing_class = payload.get("ur[class_id]") or payload.get("class_id")
            if existing_class and existing_class != class_id:
                continue
            if not payload.get("randomtoken") or not any(
                name.startswith("rph[PedToo]") for name in payload
            ):
                raise _import_error(
                    "IMPORT_EDIT_FORM_UNAVAILABLE",
                    f"Entry {index} cannot be opened as an editable DLP.",
                    exit_status=5,
                    details={"entry": index, "date": entry.date, "time_from": entry.time_from},
                )
            existing_end = payload.get("ur[time_to]") or payload.get("rph[time_to]")
            if isinstance(existing_end, str) and existing_end and (
                not re.fullmatch(r"\d{1,2}:\d{2}\s+[AP]M", existing_end, re.I)
                or _time_key(existing_end) != _time_key(entry.time_to)
            ):
                raise _import_error(
                    "IMPORT_SLOT_OCCUPIED",
                    f"Entry {index} has a different end time from the existing DLP.",
                    exit_status=5,
                    details={"entry": index},
                )
            matches.append(lesson_id)
        if len(matches) > 1:
            raise _import_error(
                "IMPORT_SLOT_OCCUPIED",
                f"Entry {index} matches multiple DLPs in the target MIW.",
                exit_status=5,
                details={"entry": index},
            )
        if matches:
            if entry.objectives is not None:
                _objective_profile(client, matches[0], index)
            plans.append(LessonPlan(entry, "update", matches[0]))
            continue

        if not base_payload.get("randomtoken"):
            raise _import_error(
                "IMPORT_TOKEN_MISSING",
                "The MIW creation form does not contain a current request token.",
                exit_status=5,
            )
        _standards_for(form, entry, index)
        if slot_context is None:
            slot_context = _miw_defaults(miw.text, subject, session)
        slot_subject, slot_session = slot_context
        _check_slot(client, entry, index, owner_id=owner_id, class_id=class_id,
                    subject=slot_subject, session=slot_session)
        if entry.objectives is not None and not checked_objectives_form:
            # The MIW Knowledge form uses the same curriculum configuration
            # as new DLPs. The new lesson's own form is checked again after create.
            client.request("GET", f"miw9.php?action=openmiw&id={miw_id}")
            _objective_profile(client, None, index)
            checked_objectives_form = True
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
            "objective_count": len(plan.entry.objectives or ()),
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
    write: PostForm,
    miw_page: str,
    entry: LessonEntry,
    index: int,
    *,
    class_id: str,
    setjadual: str,
    owner_id: str,
    grouplevelsubject: str,
) -> str:
    form = _lesson_form(miw_page)
    payload = {name: value for name, value in form_values(form).items()
               if not name.startswith("InsPro[")}
    if not payload.get("randomtoken"):
        raise _import_error("IMPORT_TOKEN_MISSING", "The MIW creation token is missing.", exit_status=5)
    payload.update(_standards_for(form, entry, index))
    button = form.select_one('[onclick*="checkBeforeCreate"]')
    action = button.get("value", button.get_text(strip=True)) if button else "Create DLP"
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
        "action": action,
    })
    response = write("miw9.php", payload)
    if not _success(response.text, "DLP has been created", "RPH telah dicipta", "RPH berjaya dicipta"):
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
    return match.group(1)


def _save_objectives(
    client: CidsClient, write: PostForm, lesson_id: str, objectives: Tuple[str, ...], index: int,
) -> None:
    payload, field = _objective_profile(client, lesson_id, index)
    if _saved_objectives(payload, field) != objectives:
        payload[field] = list(objectives)
        payload.setdefault("submit", "Save")
        write("set9.php", payload)


def _saved_objectives(payload: FormValues, field: str) -> Tuple[str, ...]:
    values = payload.get(field, [])
    if isinstance(values, str):
        values = [values]
    return tuple(" ".join(value.split()) for value in values)


def _save_lesson(client: CidsClient, write: PostForm, lesson_id: str, entry: LessonEntry) -> None:
    page = client.request("GET", _edit_path(lesson_id)).text
    form = _lesson_form(page)
    payload = form_values(form)
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
    button = form.select_one('[onclick*="checkBeforeSave"]')
    payload["action"] = button.get("value", button.get_text(strip=True)) if button else "Save DLP"
    write("miw9.php", payload)

    # Always verify persisted values; success banners vary by deployment and do
    # not prove that the rich-text fields survived server-side normalization.
    verified_page = client.request("GET", _edit_path(lesson_id)).text
    verified = form_values(_lesson_form(verified_page))
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
    subject: Optional[str] = None,
    session: Optional[str] = None,
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

    def write(path: str, payload: FormValues) -> ResponseData:
        nonlocal mutation_attempted
        mutation_attempted = True
        return client.request("POST", path, data=payload)

    for index, plan in enumerate(plans, 1):
        entry = plan.entry
        lesson_id = plan.lesson_id
        try:
            if lesson_id:
                result = "updated"
            else:
                miw = client.request("GET", f"miw9.php?action=openmiw&id={miw_id}")
                slot_subject, slot_session = _miw_defaults(miw.text, subject, session)
                _check_slot(client, entry, index, owner_id=owner_id, class_id=class_id,
                            subject=slot_subject, session=slot_session)
                lesson_id = _create_lesson(
                    write, miw.text, entry, index, class_id=class_id,
                    setjadual=setjadual, owner_id=owner_id,
                    grouplevelsubject=grouplevelsubject,
                )
                result = "created"
            if entry.objectives is not None:
                _save_objectives(client, write, lesson_id, entry.objectives, index)
            _save_lesson(client, write, lesson_id, entry)
            if entry.objectives is not None:
                verified, field = _objective_profile(client, lesson_id, index)
                if _saved_objectives(verified, field) != entry.objectives:
                    raise _import_error(
                        "IMPORT_OBJECTIVES_NOT_PERSISTED",
                        "CIDS did not retain the requested Learning Objectives.",
                        exit_status=5,
                        details={"entry": index},
                    )
            imported.append({
                "index": index,
                "date": entry.date,
                "time_from": entry.time_from,
                "time_to": entry.time_to,
                "lesson_id": lesson_id,
                "objectives_verified": len(entry.objectives or ()),
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
                        "lesson_id": lesson_id,
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
