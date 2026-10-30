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

from typing import Any

from aiohttp import ClientError


class FakePageSource:
    """
    Stands in for SafePageSource: serves recorded responses by URL prefix, and raises
    a ClientError for anything unknown, the way an unreachable host would.

    Set FakePageSource.responses before the tool under test builds its source.
    """

    responses: dict[str, Any] = {}

    async def fetch_json(self, url: str) -> Any:
        """
        :param url: The requested URL.
        :return: The recorded document whose key the URL starts with.
        :raises ClientError: When nothing is recorded for the URL.
        """
        return self._lookup(url)

    async def fetch_text(self, url: str) -> str:
        """
        :param url: The requested URL.
        :return: The recorded page text.
        :raises ClientError: When nothing is recorded for the URL.
        """
        return str(self._lookup(url))

    def _lookup(self, url: str) -> Any:
        """
        :param url: The requested URL.
        :return: The recorded response.
        :raises ClientError: When nothing is recorded for the URL.
        """
        for prefix, response in FakePageSource.responses.items():
            if url.startswith(prefix):
                return response
        raise ClientError(f"url_not_accessible: no recorded response for {url}")
