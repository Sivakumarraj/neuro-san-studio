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

from aiohttp import ClientError
from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.experimental.opportunity_desk.desk_clock import DeskClock
from coded_tools.experimental.opportunity_desk.desk_profile import DeskProfile
from coded_tools.experimental.opportunity_desk.desk_store import DeskStore
from coded_tools.experimental.opportunity_desk.evidence_matcher import MIN_QUOTE_WORDS
from coded_tools.experimental.opportunity_desk.evidence_matcher import EvidenceMatcher
from coded_tools.experimental.opportunity_desk.safe_page_source import SafePageSource

logger = logging.getLogger(__name__)

MAX_CLAIMS: int = 8


class CheckEvidence(CodedTool):
    """
    Fetches the page each claim cites and checks that the quoted passage is really on it.

    This is the network's red flag, in the MAKER sense: a cheap researcher's answer is
    accepted only when enough of its claims are backed by text that can be found at the
    cited URL. The verdict, SUPPORTED or ESCALATE, is computed here from the
    profile's evidence_threshold; the researcher is told to escalate to the stronger
    model on ESCALATE rather than argue with it.
    """

    # Tests replace this with a fake that serves recorded pages.
    source_class: type = SafePageSource

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> str:
        """
        :param args: "claims", a list of {"claim", "source_url", "quote"} with at most 8 entries.
        :param sly_data: Unused.
        :return: JSON with a status per claim and the overall verdict, or a message starting with "Error:".
        """
        claims: Any = args.get("claims")
        if not isinstance(claims, list) or not claims:
            return self._error("pass 'claims' as a non-empty list of {claim, source_url, quote}")
        if len(claims) > MAX_CLAIMS:
            return self._error(f"at most {MAX_CLAIMS} claims per check; keep the most important ones")
        try:
            threshold: float = DeskProfile.load().evidence_threshold()
        except ValueError as error:
            return self._error(str(error))

        source: SafePageSource = self.source_class()
        urls: list[str] = sorted({str(claim.get("source_url", "")) for claim in claims if isinstance(claim, dict)})
        pages: dict[str, str | Exception] = dict(
            zip(urls, await asyncio.gather(*(self._fetch(source, url) for url in urls)))
        )

        results: list[dict[str, Any]] = [self._judge(claim, pages) for claim in claims]
        verified: int = sum(1 for result in results if result.get("status") == "verified")
        ratio: float = verified / len(results)
        verdict: str = "SUPPORTED" if ratio >= threshold else "ESCALATE"
        await asyncio.to_thread(
            DeskStore().log,
            "evidence_checked",
            {"claims": len(results), "verified": verified, "verdict": verdict},
            DeskClock.now_iso(),
        )
        return json.dumps(
            {
                "verdict": verdict,
                "verified": verified,
                "total": len(results),
                "ratio": round(ratio, 2),
                "threshold": threshold,
                "claims": results,
            }
        )

    @staticmethod
    async def _fetch(source: SafePageSource, url: str) -> str | Exception:
        """
        :param source: The page source.
        :param url: A cited URL.
        :return: The page text, or the exception that stopped it, so one dead link fails one claim.
        """
        try:
            return await source.fetch_text(url)
        except (ValueError, ClientError, asyncio.TimeoutError) as error:
            logger.warning("Could not fetch cited page %s: %s", url, error)
            return error

    @staticmethod
    def _judge(claim: Any, pages: dict[str, str | Exception]) -> dict[str, Any]:
        """
        :param claim: One {"claim", "source_url", "quote"} entry.
        :param pages: Fetched page text, or the fetch error, per URL.
        :return: The claim with a status: verified, quote_not_found, quote_too_short,
            fetch_failed or malformed.
        """
        if not isinstance(claim, dict):
            return {"claim": str(claim), "status": "malformed", "detail": "each claim must be an object"}
        quote: str = str(claim.get("quote", ""))
        result: dict[str, Any] = {"claim": claim.get("claim", ""), "source_url": claim.get("source_url", "")}
        page: str | Exception | None = pages.get(str(claim.get("source_url", "")))
        if len(EvidenceMatcher.normalize(quote).split()) < MIN_QUOTE_WORDS:
            return result | {"status": "quote_too_short", "detail": f"quote at least {MIN_QUOTE_WORDS} words verbatim"}
        if isinstance(page, Exception) or page is None:
            return result | {"status": "fetch_failed", "detail": str(page)}
        coverage: float = EvidenceMatcher.coverage(page, quote)
        status: str = "verified" if EvidenceMatcher.is_supported(page, quote) else "quote_not_found"
        return result | {"status": status, "detail": f"{coverage:.0%} of the quote found on the page"}

    @staticmethod
    def _error(message: str) -> str:
        """
        :param message: What went wrong.
        :return: The message prefixed with "Error:".
        """
        logger.warning("CheckEvidence refused the request: %s", message)
        return f"Error: {message}"
