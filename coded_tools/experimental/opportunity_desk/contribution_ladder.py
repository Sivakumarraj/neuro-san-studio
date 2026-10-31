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

from datetime import date
from datetime import datetime
from typing import Any

# Review silence is normal for two weeks; after a month a second contribution should be
# under way; after six weeks one short question on the pull request is fair, once.
WAIT_DAYS: int = 14
SECOND_TARGET_DAYS: int = 30
NUDGE_DAYS: int = 45


# One question per class, so one public method.
# pylint: disable=too-few-public-methods
class ContributionLadder:
    """
    Decides, in code, what the owner should do next about one of their own upstream pull
    requests or issues, from its state and age alone.

    The point is to make waiting the default: a reviewer who is pinged early or twice
    remembers the ping, not the contribution. So the ladder only ever permits one short,
    technical question on a pull request, once it has waited more than SECOND_TARGET_DAYS,
    and never a reminder on an issue, where the next move is a small pull request instead.
    """

    @staticmethod
    def verdict(item: dict[str, Any], today: date) -> str:
        """
        :param item: A contribution record (see BoardParser.parse_contributions).
        :param today: The date to measure age against.
        :return: One line saying what to do next, starting with the state.
        """
        days: int = ContributionLadder._days_open(item, today)
        if item.get("kind") == "pull_request":
            return ContributionLadder._pull_request(item, days)
        if item.get("state") == "closed":
            return "closed"
        comments: int = int(item.get("comments") or 0)
        if comments:
            return f"open {days} day(s) with {comments} comment(s): read the discussion and answer what was asked"
        if days > WAIT_DAYS:
            return (
                f"open {days} days with no reply: do not ping; if it is a bug, a small pull request "
                "that fixes it is the next move"
            )
        return f"open {days} day(s): waiting for a maintainer"

    @staticmethod
    def _pull_request(item: dict[str, Any], days: int) -> str:
        """
        :param item: A pull request record.
        :param days: Days since it was opened.
        :return: The verdict for a pull request.
        """
        if item.get("merged"):
            return "merged: a credential you can cite"
        if item.get("state") == "closed":
            return "closed without merging: read the reviewer's reason before trying again"
        if days <= WAIT_DAYS:
            return f"open {days} day(s): wait, silence is normal"
        if days <= SECOND_TARGET_DAYS:
            return f"open {days} days: keep waiting, and line up a second contribution meanwhile"
        if days <= NUDGE_DAYS:
            return f"open {days} days: one short technical question on the pull request is fair now, once"
        return f"open {days} days: stalled; ask once if you have not, then put the effort into another contribution"

    @staticmethod
    def _days_open(item: dict[str, Any], today: date) -> int:
        """
        :param item: A contribution record with "opened_at".
        :param today: The date to measure against.
        :return: Whole days since it was opened, 0 when the date is missing or malformed.
        """
        try:
            opened: date = datetime.fromisoformat(str(item.get("opened_at")).replace("Z", "+00:00")).date()
        except ValueError:
            return 0
        return max(0, (today - opened).days)
