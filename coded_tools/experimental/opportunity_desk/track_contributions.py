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
from datetime import date
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.experimental.opportunity_desk.board_reader import BoardReader
from coded_tools.experimental.opportunity_desk.contribution_ladder import ContributionLadder
from coded_tools.experimental.opportunity_desk.desk_clock import DeskClock
from coded_tools.experimental.opportunity_desk.desk_profile import DeskProfile
from coded_tools.experimental.opportunity_desk.desk_store import DeskStore
from coded_tools.experimental.opportunity_desk.safe_page_source import SafePageSource

logger = logging.getLogger(__name__)


class TrackContributions(CodedTool):
    """
    Checks the owner's own pull requests and issues in the upstream repositories they
    contribute to, reports what changed since the last check, and gives each one the
    ContributionLadder's verdict on what to do next.

    One GitHub search covers every repository, which keeps the daily run well inside
    GitHub's unauthenticated limit of ten searches a minute.
    """

    # Tests replace this with a fake that serves recorded responses.
    source_class: type = SafePageSource

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> str:
        """
        :param args: Unused; the GitHub login and repositories come from the profile.
        :param sly_data: Unused.
        :return: JSON with the changes and each item's verdict, or a message starting with "Error:".
        """
        try:
            profile: DeskProfile = DeskProfile.load()
        except ValueError as error:
            return self._error(str(error))
        user: str = profile.github_user()
        if not user:
            return self._error("the profile has no github_user, so there is nothing to track")

        records, failure = await BoardReader(self.source_class()).read_contributions(user, profile.upstream_repos())
        if failure:
            return self._error(failure)

        store: DeskStore = DeskStore()
        now: str = DeskClock.now_iso()
        changes: list[dict[str, Any]] = await asyncio.to_thread(store.sync_contributions, records, now)
        today: date = DeskClock.today()
        items: list[dict[str, Any]] = [self._brief(record, today) for record in records]
        await asyncio.to_thread(
            store.log, "contributions_checked", {"tracked": len(items), "changes": len(changes)}, now
        )
        logger.info("Tracked %d upstream contributions for %s, %d changed", len(items), user, len(changes))
        return json.dumps({"github_user": user, "tracked": len(items), "changes": changes, "items": items})

    @staticmethod
    def _brief(record: dict[str, Any], today: date) -> dict[str, Any]:
        """
        :param record: A contribution record.
        :param today: The date verdicts are measured against.
        :return: The fields an agent needs to present it, with the ladder's verdict.
        """
        keys: tuple[str, ...] = ("repo", "number", "kind", "title", "state", "merged", "comments", "url")
        return {key: record.get(key) for key in keys} | {"verdict": ContributionLadder.verdict(record, today)}

    @staticmethod
    def _error(message: str) -> str:
        """
        :param message: What went wrong.
        :return: The message prefixed with "Error:".
        """
        logger.warning("TrackContributions refused the request: %s", message)
        return f"Error: {message}"
