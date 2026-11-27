"""Local teaching-week dates confirmed by the teacher or school calendar."""

import re
import sqlite3
from contextlib import closing
from datetime import date
from typing import List, Optional

from .client import CidsError, config_dir


def _validate_session(session: Optional[str]) -> None:
    if session is not None and not re.fullmatch(r"[0-9]+", session):
        raise CidsError("The CIDS session must be numeric.", code="WEEK_LOG_SESSION_INVALID", exit_status=2)


def _validate_week(week: Optional[int]) -> None:
    if week is not None and not 1 <= week <= 53:
        raise CidsError("The teaching week must be between 1 and 53.", code="WEEK_LOG_WEEK_INVALID", exit_status=2)


def _entry(session: str, week: Optional[int], date_from: str, date_to: str) -> dict:
    return {"session": session, "week": week, "date_from": date_from, "date_to": date_to}


def set_week(session: str, week: Optional[int], first_day: date, last_day: date) -> dict:
    _validate_session(session)
    _validate_week(week)
    if last_day < first_day:
        raise CidsError("The date range ends before it starts.", code="DATE_RANGE_INVALID", exit_status=2)

    start, end = first_day.isoformat(), last_day.isoformat()
    folder = config_dir()
    try:
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        with closing(sqlite3.connect(folder / "week-log.sqlite3")) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS weeks (
                    session TEXT NOT NULL,
                    week INTEGER,
                    date_from TEXT NOT NULL,
                    date_to TEXT NOT NULL,
                    PRIMARY KEY (session, date_from)
                )
            """)
            db.execute("BEGIN IMMEDIATE")
            overlap = db.execute("""
                SELECT date_from, date_to FROM weeks
                WHERE session = ? AND date_from <> ? AND date_from <= ? AND date_to >= ?
                ORDER BY date_from LIMIT 1
            """, (session, start, end, start)).fetchone()
            if overlap:
                raise CidsError(
                    f"This range overlaps the logged dates {overlap[0]} to {overlap[1]}.",
                    code="WEEK_LOG_OVERLAP", exit_status=2,
                    details={"date_from": overlap[0], "date_to": overlap[1]},
                )
            db.execute("""
                INSERT INTO weeks (session, week, date_from, date_to) VALUES (?, ?, ?, ?)
                ON CONFLICT(session, date_from) DO UPDATE SET week = excluded.week, date_to = excluded.date_to
            """, (session, week, start, end))
    except (OSError, sqlite3.Error):
        raise CidsError("Could not save the local teaching-week log.", code="WEEK_LOG_UNAVAILABLE") from None
    return _entry(session, week, start, end)


def list_weeks(
    *, session: Optional[str] = None, week: Optional[int] = None, day: Optional[date] = None,
) -> List[dict]:
    _validate_session(session)
    _validate_week(week)
    path = config_dir() / "week-log.sqlite3"
    if not path.is_file():
        return []
    day_text = day.isoformat() if day is not None else None
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            rows = db.execute("""
                SELECT session, week, date_from, date_to FROM weeks
                WHERE (? IS NULL OR session = ?) AND (? IS NULL OR week = ?)
                  AND (? IS NULL OR ? BETWEEN date_from AND date_to)
                ORDER BY date_from, session
            """, (session, session, week, week, day_text, day_text))
            return [_entry(*row) for row in rows]
    except sqlite3.Error:
        raise CidsError("Could not read the local teaching-week log.", code="WEEK_LOG_UNAVAILABLE") from None
