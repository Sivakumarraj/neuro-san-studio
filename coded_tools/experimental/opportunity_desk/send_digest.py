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

import asyncio
import logging
import smtplib
from datetime import date
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.experimental.opportunity_desk.contribution_ladder import ContributionLadder
from coded_tools.experimental.opportunity_desk.desk_clock import DeskClock
from coded_tools.experimental.opportunity_desk.desk_profile import DeskProfile
from coded_tools.experimental.opportunity_desk.desk_store import DeskStore
from coded_tools.experimental.opportunity_desk.digest_mailer import DigestMailer

logger = logging.getLogger(__name__)

MAX_DIGEST_ITEMS: int = 25


class SendDigest(CodedTool):
    """
    Collects the matches first seen, and the owner's upstream contributions that changed,
    since the last delivered digest, and emails them to the owner.

    Written in plain text by code, not by an LLM, so the digest can never contain a
    score or a reason the assessor did not produce. When SMTP is not configured the
    digest comes back as text and is recorded as undelivered, so the next delivered
    digest still covers those matches.
    """

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> str:
        """
        :param args: Unused; the recipient comes from the environment only (see DigestMailer).
        :param sly_data: Unused.
        :return: What was sent, or the digest text when there is no mail setup,
            or a message starting with "Error:".
        """
        try:
            profile: DeskProfile = DeskProfile.load()
            store: DeskStore = DeskStore()
        except ValueError as error:
            return f"Error: {error}"
        since: str | None = store.last_digest_at()
        rows: list[dict[str, Any]] = [
            row
            for row in store.list_opportunities(min_score=profile.min_score(), limit=MAX_DIGEST_ITEMS, since=since)
            if row.get("eligible")
        ]
        changed: list[dict[str, Any]] = store.contributions(changed_since=since)
        now: str = DeskClock.now_iso()
        if not rows and not changed:
            store.log("digest_skipped", {"since": since}, now)
            return f"No new matches or contribution changes since {since or 'the first scan'}; nothing to send."

        body: str = self._format(rows, changed, since)
        count: int = len(rows) + len(changed)
        if not DigestMailer.is_configured():
            store.record_digest(now, count, delivered=False)
            store.log("digest_built", {"items": count, "delivered": False}, now)
            return f"Email is not configured, so here is the digest instead.\n\n{body}"
        try:
            DigestMailer.send(f"{len(rows)} new match(es), {len(changed)} contribution update(s)", body)
        except (smtplib.SMTPException, OSError) as error:
            logger.error("Digest email failed: %s", error)
            store.record_digest(now, count, delivered=False)
            store.log("digest_failed", {"items": count, "error": type(error).__name__}, now)
            return f"Error: the digest email failed ({type(error).__name__}: {error})."
        store.record_digest(now, count, delivered=True)
        store.log("digest_sent", {"items": count}, now)
        return f"Emailed a digest of {len(rows)} new match(es) and {len(changed)} contribution update(s) to the owner."

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> str:
        """
        Run invoke in a worker thread, because SQLite and SMTP calls block.

        :param args: See invoke.
        :param sly_data: See invoke.
        :return: See invoke.
        """
        return await asyncio.to_thread(self.invoke, args, sly_data)

    @staticmethod
    def _format(rows: list[dict[str, Any]], changed: list[dict[str, Any]], since: str | None) -> str:
        """
        :param rows: Stored opportunities, best first.
        :param changed: The owner's upstream contributions that changed in the period.
        :param since: Start of the period covered, or None for everything so far.
        :return: The digest as plain text: each match with its score and reasons, then each
            contribution update with the ladder's verdict on what to do next.
        """
        period: str = since or "your first scan"
        blocks: list[str] = []
        if rows:
            blocks.append(f"New matches since {period}:")
        for row in rows:
            reasons: str = "; ".join(row.get("reasons") or [])
            blocks.append(
                f"{row.get('score')}/100  {row.get('title')} at {row.get('company')} ({row.get('location')})\n"
                f"{row.get('url')}\n"
                f"Why: {reasons}\n"
                f"Track it with id: {row.get('opportunity_id')}"
            )
        if changed:
            blocks.append(f"Your upstream pull requests and issues that changed since {period}:")
        today: date = DeskClock.today()
        for item in changed:
            blocks.append(
                f"{item.get('repo')}#{item.get('number')}  {item.get('title')}\n"
                f"{item.get('url')}\n"
                f"What changed: {item.get('last_change')}\n"
                f"Next: {ContributionLadder.verdict(item, today)}"
            )
        return "\n\n".join(blocks)
