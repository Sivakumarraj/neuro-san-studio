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
import json
import logging
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.experimental.opportunity_desk.board_reader import BoardReader
from coded_tools.experimental.opportunity_desk.desk_clock import DeskClock
from coded_tools.experimental.opportunity_desk.desk_profile import DeskProfile
from coded_tools.experimental.opportunity_desk.desk_store import DeskStore
from coded_tools.experimental.opportunity_desk.fit_assessor import FitAssessor
from coded_tools.experimental.opportunity_desk.fit_result import FitResult
from coded_tools.experimental.opportunity_desk.posting import Posting
from coded_tools.experimental.opportunity_desk.safe_page_source import SafePageSource

logger = logging.getLogger(__name__)

DEFAULT_LIMIT: int = 10
MAX_LIMIT: int = 50


class ScanBoards(CodedTool):
    """
    Reads every board and repository in the profile, scores each posting with
    FitAssessor, stores the ones not seen before, and returns the best new matches.

    No LLM is involved anywhere in a scan, so the daily scheduled run costs only the
    front man's routing. The agent that calls this tool is told to present the
    returned scores and reasons as they are.
    """

    # Tests replace this with a fake that serves recorded responses.
    source_class: type = SafePageSource

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> str:
        """
        :param args: May contain "limit" (matches to return, default 10, at most 50).
        :param sly_data: Unused; the profile and the store hold all state.
        :return: A JSON summary, or a message starting with "Error:".
        """
        try:
            profile: DeskProfile = DeskProfile.load()
            limit: int = max(1, min(int(args.get("limit") or DEFAULT_LIMIT), MAX_LIMIT))
        except ValueError as error:
            return self._error(str(error))
        if not profile.boards() and not profile.contribution_repos():
            return self._error("the profile lists no boards or repositories to scan; add some under 'boards'")

        postings, errors, attempted = await BoardReader(self.source_class()).read_all(profile)
        if attempted and len(errors) == attempted:
            return self._error(f"every source failed: {'; '.join(errors)}")

        store: DeskStore = DeskStore()
        now: str = DeskClock.now_iso()
        new_rows: list[dict[str, Any]] = await asyncio.to_thread(store.save_new, self._assess(profile, postings), now)
        summary: dict[str, Any] = self._summarize(profile, new_rows, limit) | {
            "sources_read": attempted - len(errors),
            "sources_failed": errors,
            "postings_seen": len(postings),
        }
        counts: tuple[str, ...] = ("sources_read", "postings_seen", "new_postings", "new_matches")
        audit: dict[str, Any] = {key: summary.get(key) for key in counts} | {"sources_failed": len(errors)}
        await asyncio.to_thread(store.log, "scan", audit, now)
        logger.info("Scan stored %d new postings, %d of them matches", len(new_rows), summary.get("new_matches"))
        return json.dumps(summary)

    @staticmethod
    def _assess(profile: DeskProfile, postings: list[Posting]) -> list[tuple[Posting, FitResult]]:
        """
        :param profile: The owner's profile.
        :param postings: Everything the scan read.
        :return: Each posting with its fit, decided by FitAssessor.
        """
        assessor: FitAssessor = FitAssessor(profile)
        return [(posting, assessor.assess(posting)) for posting in postings]

    def _summarize(self, profile: DeskProfile, new_rows: list[dict[str, Any]], limit: int) -> dict[str, Any]:
        """
        :param profile: The owner's profile, for its match threshold.
        :param new_rows: Postings stored for the first time by this scan.
        :param limit: How many matches to include.
        :return: Counts and the best eligible new matches, highest score first.
        """
        matches: list[dict[str, Any]] = sorted(
            (row for row in new_rows if row.get("eligible") and row.get("score") >= profile.min_score()),
            key=lambda row: row.get("score"),
            reverse=True,
        )
        return {
            "profile_is_example": profile.is_example(),
            "new_postings": len(new_rows),
            "new_matches": len(matches),
            "min_score": profile.min_score(),
            "matches": [self._brief(row) for row in matches[:limit]],
        }

    @staticmethod
    def _brief(row: dict[str, Any]) -> dict[str, Any]:
        """
        :param row: A stored opportunity.
        :return: The fields an agent needs to present it.
        """
        keys: tuple[str, ...] = ("opportunity_id", "kind", "title", "company", "location", "url", "score", "reasons")
        return {key: row.get(key) for key in keys}

    @staticmethod
    def _error(message: str) -> str:
        """
        :param message: What went wrong.
        :return: The message prefixed with "Error:", which the agents relay and stop on.
        """
        logger.warning("ScanBoards refused the request: %s", message)
        return f"Error: {message}"
