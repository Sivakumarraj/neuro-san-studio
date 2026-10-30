# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# END COPYRIGHT

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

from coded_tools.experimental.opportunity_desk.desk_clock import DeskClock
from coded_tools.experimental.opportunity_desk.fit_result import FitResult
from coded_tools.experimental.opportunity_desk.posting import Posting

# Where the tracker lives. In production this is a persistent disk; the default sits
# under logs/, which git ignores, so a local run never writes into the repository.
DATA_DIR_ENV: str = "OPPORTUNITY_DESK_DATA_DIR"
DEFAULT_DATA_DIR: str = "logs/opportunity_desk"
DATABASE_NAME: str = "desk.sqlite3"

STATUSES: tuple[str, ...] = ("new", "shortlisted", "applied", "interviewing", "offer", "rejected", "dropped")
DIRECTIONS: tuple[str, ...] = ("sent", "received")

SCHEMA: str = """
CREATE TABLE IF NOT EXISTS opportunities (
    opportunity_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT NOT NULL,
    url TEXT NOT NULL,
    posted_at TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    score INTEGER NOT NULL,
    eligible INTEGER NOT NULL,
    reasons TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outreach_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    happened_on TEXT NOT NULL,
    summary TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS digests (
    digest_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at TEXT NOT NULL,
    item_count INTEGER NOT NULL,
    delivered INTEGER NOT NULL
);
"""


class DeskStore:
    """
    The desk's memory: tracked opportunities, the owner's record of outreach, an
    append-only audit log of every decision the tools made, and the digest history.

    SQLite, one connection per call (see _session). Every method is blocking, so coded tools call
    them through asyncio.to_thread. SQLite serializes writers itself, which is enough
    for one owner and one scheduled scan.

    Timestamps are passed in rather than read from the clock, so tests can pin them.
    """

    def __init__(self, data_dir: str | None = None):
        """
        :param data_dir: Directory for the database; defaults to OPPORTUNITY_DESK_DATA_DIR,
            then logs/opportunity_desk. Created when missing.
        """
        directory: Path = Path(data_dir or os.getenv(DATA_DIR_ENV) or DEFAULT_DATA_DIR)
        directory.mkdir(parents=True, exist_ok=True)
        self._path: Path = directory / DATABASE_NAME
        with self._session() as connection:
            connection.executescript(SCHEMA)

    def save_new(self, assessed: list[tuple[Posting, FitResult]], now: str) -> list[dict[str, Any]]:
        """
        Insert postings not seen before; leave known ones, and the owner's status on them, alone.

        :param assessed: Postings with their fit.
        :param now: ISO timestamp recorded as first_seen.
        :return: The rows that were new, as dicts.
        """
        new_ids: list[str] = []
        with self._session() as connection:
            for posting, fit in assessed:
                cursor: sqlite3.Cursor = connection.execute(
                    "INSERT OR IGNORE INTO opportunities (opportunity_id, kind, source, title, company, location, url,"
                    " posted_at, first_seen, score, eligible, reasons, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        posting.posting_id,
                        posting.kind,
                        posting.source,
                        posting.title,
                        posting.company,
                        posting.location,
                        posting.url,
                        posting.posted_at,
                        now,
                        fit.score,
                        int(fit.eligible),
                        json.dumps(list(fit.reasons)),
                        now,
                    ),
                )
                if cursor.rowcount:
                    new_ids.append(posting.posting_id)
        return [row for row in (self.get_opportunity(opportunity_id) for opportunity_id in new_ids) if row]

    def get_opportunity(self, opportunity_id: str) -> dict[str, Any] | None:
        """
        :param opportunity_id: The posting id.
        :return: The row as a dict, or None.
        """
        with self._session() as connection:
            row: sqlite3.Row | None = connection.execute(
                "SELECT * FROM opportunities WHERE opportunity_id = ?", (opportunity_id,)
            ).fetchone()
        return self._opportunity(row) if row else None

    def list_opportunities(
        self, status: str | None = None, min_score: int = 0, limit: int = 20, since: str | None = None
    ) -> list[dict[str, Any]]:
        """
        :param status: Only this status, when given.
        :param min_score: Only rows scoring at least this.
        :param limit: At most this many rows, best first.
        :param since: Only rows first seen at or after this ISO timestamp.
        :return: Eligible rows first, then by score, then newest.
        """
        clauses: list[str] = ["score >= ?"]
        values: list[Any] = [min_score]
        if status:
            clauses.append("status = ?")
            values.append(status)
        if since:
            clauses.append("first_seen >= ?")
            values.append(since)
        values.append(limit)
        with self._session() as connection:
            rows: list[sqlite3.Row] = connection.execute(
                f"SELECT * FROM opportunities WHERE {' AND '.join(clauses)}"  # nosec B608 - fixed clause names
                " ORDER BY eligible DESC, score DESC, first_seen DESC LIMIT ?",
                values,
            ).fetchall()
        return [self._opportunity(row) for row in rows]

    def update_status(self, opportunity_id: str, status: str, note: str, now: str) -> bool:
        """
        :param opportunity_id: The posting id.
        :param status: One of STATUSES.
        :param note: Free text kept with the row; an empty note keeps the old one.
        :param now: ISO timestamp.
        :return: True when a row was updated.
        :raises ValueError: For a status outside STATUSES.
        """
        if status not in STATUSES:
            raise ValueError(f"unknown status '{status}'; use one of {', '.join(STATUSES)}")
        with self._session() as connection:
            cursor: sqlite3.Cursor = connection.execute(
                "UPDATE opportunities SET status = ?, note = CASE WHEN ? = '' THEN note ELSE ? END, updated_at = ?"
                " WHERE opportunity_id = ?",
                (status, note, note, now, opportunity_id),
            )
        return cursor.rowcount > 0

    def record_outreach(self, contact_id: str, direction: str, happened_on: str, summary: str) -> None:
        """
        :param contact_id: The contact's key in the profile.
        :param direction: "sent" or "received".
        :param happened_on: YYYY-MM-DD.
        :param summary: One line about the message.
        :raises ValueError: For an unknown direction or a malformed date.
        """
        if direction not in DIRECTIONS:
            raise ValueError(f"direction must be one of {', '.join(DIRECTIONS)}")
        date.fromisoformat(happened_on)
        with self._session() as connection:
            connection.execute(
                "INSERT INTO outreach_events (contact_id, direction, happened_on, summary, recorded_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (contact_id, direction, happened_on, summary, DeskClock.now_iso()),
            )

    def outreach_history(self, contact_id: str) -> list[dict[str, Any]]:
        """
        :param contact_id: The contact's key in the profile.
        :return: Their events, oldest first.
        """
        with self._session() as connection:
            rows: list[sqlite3.Row] = connection.execute(
                "SELECT direction, happened_on, summary FROM outreach_events WHERE contact_id = ?"
                " ORDER BY happened_on, event_id",
                (contact_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def log(self, action: str, detail: dict[str, Any], now: str) -> None:
        """
        Append to the audit log. Nothing is ever updated or deleted there.

        :param action: A short verb, e.g. "scan" or "outreach_blocked".
        :param detail: What was decided and why; never message bodies or secrets.
        :param now: ISO timestamp.
        """
        with self._session() as connection:
            connection.execute(
                "INSERT INTO audit_log (at, action, detail) VALUES (?, ?, ?)", (now, action, json.dumps(detail))
            )

    def audit_tail(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        :param limit: How many entries.
        :return: The most recent entries, newest first.
        """
        with self._session() as connection:
            rows: list[sqlite3.Row] = connection.execute(
                "SELECT at, action, detail FROM audit_log ORDER BY entry_id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"at": row["at"], "action": row["action"], "detail": json.loads(row["detail"])} for row in rows]

    def last_digest_at(self) -> str | None:
        """
        :return: When the last delivered digest went out, or None.
        """
        with self._session() as connection:
            row: sqlite3.Row | None = connection.execute(
                "SELECT sent_at FROM digests WHERE delivered = 1 ORDER BY digest_id DESC LIMIT 1"
            ).fetchone()
        return row["sent_at"] if row else None

    def record_digest(self, now: str, item_count: int, delivered: bool) -> None:
        """
        :param now: ISO timestamp.
        :param item_count: How many opportunities the digest listed.
        :param delivered: Whether it was emailed; an undelivered digest does not move last_digest_at.
        """
        with self._session() as connection:
            connection.execute(
                "INSERT INTO digests (sent_at, item_count, delivered) VALUES (?, ?, ?)",
                (now, item_count, int(delivered)),
            )

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        """
        Open a connection whose rows are addressable by column name, commit when the
        block succeeds, roll back when it raises, and always close it.

        :return: A context manager yielding the connection.
        """
        connection: sqlite3.Connection = sqlite3.connect(self._path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _opportunity(row: sqlite3.Row) -> dict[str, Any]:
        """
        :param row: An opportunities row.
        :return: The row as a dict, with eligible as a bool and reasons as a list.
        """
        record: dict[str, Any] = dict(row)
        record["eligible"] = bool(record.get("eligible"))
        record["reasons"] = json.loads(record.get("reasons") or "[]")
        return record
