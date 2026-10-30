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

import re
import unicodedata

# A quote shorter than this proves little: four common words appear on most pages.
MIN_QUOTE_WORDS: int = 6
# Word n-grams compared when the quote is not found verbatim.
SHINGLE_WORDS: int = 3
# Share of the quote's n-grams that must appear on the page for a near-verbatim match.
MIN_COVERAGE: float = 0.8

NON_WORD_PATTERN: re.Pattern[str] = re.compile(r"[^a-z0-9]+")


class EvidenceMatcher:
    """
    Answers one question without an LLM: does this page really contain this quote?

    Pages are normalized (Unicode folding, case, punctuation and whitespace) before
    comparing, so a quote survives curly quotes, line breaks and markup stripping.
    When the quote is not found verbatim, its 3-word shingles are counted on the page,
    which tolerates a dropped word or a changed comma but not a paraphrase. A
    paraphrase is exactly what this check exists to catch.
    """

    @staticmethod
    def normalize(text: str) -> str:
        """
        :param text: Any text.
        :return: The text folded to lowercase ASCII words separated by single spaces.
        """
        folded: str = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        return NON_WORD_PATTERN.sub(" ", folded.lower()).strip()

    @staticmethod
    def coverage(page_text: str, quote: str) -> float:
        """
        :param page_text: The fetched page, as plain text.
        :param quote: The passage a claim says the page contains.
        :return: 1.0 for a verbatim match, else the share of the quote's shingles found on the page.
            0.0 for a quote shorter than MIN_QUOTE_WORDS.
        """
        quote_words: list[str] = EvidenceMatcher.normalize(quote).split()
        if len(quote_words) < MIN_QUOTE_WORDS:
            return 0.0
        page: str = EvidenceMatcher.normalize(page_text)
        if " ".join(quote_words) in page:
            return 1.0
        page_shingles: set[tuple[str, ...]] = EvidenceMatcher._shingles(page.split())
        quote_shingles: set[tuple[str, ...]] = EvidenceMatcher._shingles(quote_words)
        return len(quote_shingles & page_shingles) / len(quote_shingles)

    @staticmethod
    def is_supported(page_text: str, quote: str) -> bool:
        """
        :param page_text: The fetched page, as plain text.
        :param quote: The passage a claim says the page contains.
        :return: True when the coverage reaches MIN_COVERAGE.
        """
        return EvidenceMatcher.coverage(page_text, quote) >= MIN_COVERAGE

    @staticmethod
    def _shingles(words: list[str]) -> set[tuple[str, ...]]:
        """
        :param words: A list of normalized words.
        :return: Every run of SHINGLE_WORDS consecutive words.
        """
        return {tuple(words[index : index + SHINGLE_WORDS]) for index in range(len(words) - SHINGLE_WORDS + 1)}
