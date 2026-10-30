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
from typing import Any

from aiohttp import ClientSession

from neuro_san_studio.coded_tools.utils.safe_fetch import SafeFetch


class SafePageSource:
    """
    Fetches pages and JSON for the opportunity desk through SafeFetch.

    Every request inherits SafeFetch's SSRF protection, byte cap, timeout and
    redirect checks; nothing in this network opens its own HTTP connection. Tests
    replace this class with a fake that serves recorded responses, which is why the
    tools take a source rather than calling SafeFetch directly.
    """

    async def fetch_text(self, url: str) -> str:
        """
        :param url: An http or https URL.
        :return: The page as plain text, HTML stripped.
        :raises ValueError: On a refused URL or an oversized body (see SafeFetch).
        :raises aiohttp.ClientError: On a network or HTTP failure.
        """
        session: ClientSession
        async with SafeFetch.open_session() as session:
            return await SafeFetch.fetch_text(url, session)

    async def fetch_json(self, url: str) -> Any:
        """
        :param url: An http or https URL serving JSON.
        :return: The decoded document.
        :raises ValueError: On a refused URL, an oversized body or invalid JSON.
        :raises aiohttp.ClientError: On a network or HTTP failure.
        """
        session: ClientSession
        async with SafeFetch.open_session() as session:
            raw: str = await SafeFetch.fetch_raw(url, session)
        return json.loads(raw)
