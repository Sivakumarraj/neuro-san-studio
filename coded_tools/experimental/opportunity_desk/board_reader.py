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
from typing import Any

from aiohttp import ClientError

from coded_tools.experimental.opportunity_desk.board_parser import BoardParser
from coded_tools.experimental.opportunity_desk.desk_profile import DeskProfile
from coded_tools.experimental.opportunity_desk.posting import Posting
from coded_tools.experimental.opportunity_desk.safe_page_source import SafePageSource

logger = logging.getLogger(__name__)

# Concurrent fetches; GitHub allows 60 unauthenticated requests an hour, boards are lenient.
MAX_CONCURRENT_FETCHES: int = 4


# One question per class, so one public method.
# pylint: disable=too-few-public-methods
class BoardReader:
    """
    Reads every board and repository the profile lists, and reports each failure by name.

    One broken board never hides the others: its error is collected and returned
    beside the postings that did load, so the user sees "3 boards read, 1 failed:
    lever/acme: url_not_accessible" instead of a silent gap.
    """

    def __init__(self, source: SafePageSource):
        """
        :param source: Fetches JSON; SafePageSource in production, a fake in tests.
        """
        self._source: SafePageSource = source
        self._limit: asyncio.Semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)

    async def read_all(self, profile: DeskProfile) -> tuple[list[Posting], list[str], int]:
        """
        :param profile: The owner's profile.
        :return: The postings that loaded, one error string per failed fetch,
            and how many fetches were attempted.
        """
        jobs: list[Any] = [self._read_board(board) for board in profile.boards()]
        for spec in profile.contribution_repos():
            try:
                urls: list[str] = BoardParser.issue_urls(spec)
            except ValueError as error:
                jobs.append(self._failed(f"github/{spec.get('repo')}: {error}"))
                continue
            jobs.extend(self._read_issues(str(spec.get("repo")), url) for url in urls)

        results: list[tuple[list[Posting], str | None]] = await asyncio.gather(*jobs)
        postings: dict[str, Posting] = {}
        errors: list[str] = []
        for found, error in results:
            if error:
                errors.append(error)
            for posting in found:
                # The same issue can carry two tracked labels; keep one copy.
                postings[posting.posting_id] = posting
        return list(postings.values()), errors, len(jobs)

    async def _read_board(self, board: dict[str, Any]) -> tuple[list[Posting], str | None]:
        """
        :param board: A profile board entry.
        :return: Its postings and no error, or no postings and the error.
        """
        name: str = f"{board.get('provider')}/{board.get('slug')}"
        try:
            url: str = BoardParser.board_url(board)
            async with self._limit:
                document: Any = await self._source.fetch_json(url)
            return BoardParser.parse_board(board, document), None
        except (ValueError, ClientError, asyncio.TimeoutError) as error:
            logger.warning("Could not read board %s: %s", name, error)
            return [], f"{name}: {error}"

    async def _read_issues(self, repo: str, url: str) -> tuple[list[Posting], str | None]:
        """
        :param repo: The "owner/name" being read.
        :param url: One of its open-issues URLs.
        :return: Its contribution postings and no error, or no postings and the error.
        """
        try:
            async with self._limit:
                document: Any = await self._source.fetch_json(url)
            return BoardParser.parse_issues(repo, document), None
        except (ValueError, ClientError, asyncio.TimeoutError) as error:
            logger.warning("Could not read issues for %s: %s", repo, error)
            return [], f"github/{repo}: {error}"

    @staticmethod
    async def _failed(error: str) -> tuple[list[Posting], str | None]:
        """
        :param error: A configuration error found before any fetch.
        :return: No postings and the error, shaped like a fetch result for gather.
        """
        logger.warning("Skipped a repository: %s", error)
        return [], error
