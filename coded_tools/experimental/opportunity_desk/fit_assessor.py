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

from coded_tools.experimental.opportunity_desk.desk_profile import DeskProfile
from coded_tools.experimental.opportunity_desk.fit_result import FitResult
from coded_tools.experimental.opportunity_desk.posting import Posting

# "3+ years", "2-4 years", "5 to 7 yrs": the first number is the minimum asked for.
YEARS_PATTERN: re.Pattern[str] = re.compile(r"\b(\d{1,2})\s*(?:\+|-|–|to)?\s*(?:\d{1,2})?\s*\+?\s*(?:years?|yrs?)\b")
# A graduation-year restriction, with the years before the word ("2026 batch",
# "2024/2025 passouts") or after it ("pass-out 2026", "batch of 2025").
YEARS_LIST: str = r"((?:20\d\d)(?:\s*(?:/|,|and|&|or)\s*20\d\d)*)"
BATCH_WORDS: str = r"(?:batch|graduates|grads|pass\s*-?\s*outs?)"
BATCH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(rf"\b{YEARS_LIST}\s*{BATCH_WORDS}\b"),
    re.compile(rf"\b{BATCH_WORDS}\s*(?:of\s*)?{YEARS_LIST}\b"),
)
SENIOR_TITLE_TERMS: tuple[str, ...] = ("senior", "sr.", "staff", "principal", "lead", "manager", "director", "head")
ENTRY_TERMS: tuple[str, ...] = ("fresher", "new grad", "graduate", "entry level", "entry-level", "intern", "trainee")

SKILL_POINTS: int = 50
TITLE_POINTS: int = 20
LOCATION_POINTS: int = 15
ENTRY_POINTS: int = 15
# Matching this many skills earns the full skill points; a posting rarely names more.
SKILLS_FOR_FULL_MARKS: int = 6


# One question per class, so one public method.
# pylint: disable=too-few-public-methods
class FitAssessor:
    """
    Scores a posting against the profile in plain Python, with a reason for every point.

    This is the "decisions in code" half of the network: an LLM summarizes what the
    assessor found, but never decides whether a posting fits. Hard requirements (years
    asked, graduation batch, excluded terms, senior titles) make a posting ineligible
    however well it scores, because a high score on a role the owner cannot take is
    worse than no result.

    Contributions (repository issues) are scored on skills alone and are always
    eligible: an open issue has no location or seniority bar.
    """

    def __init__(self, profile: DeskProfile):
        """
        :param profile: The owner's profile.
        """
        self._profile: DeskProfile = profile

    def assess(self, posting: Posting) -> FitResult:
        """
        :param posting: The posting to score.
        :return: Its score, eligibility and the reasons for both.
        """
        text: str = f"{posting.title}\n{posting.description}".lower()
        reasons: list[str] = []
        matched: list[str] = [skill for skill in self._profile.skills() if self._mentions(text, skill)]
        skill_score: int = round(SKILL_POINTS * min(1.0, len(matched) / SKILLS_FOR_FULL_MARKS))
        if matched:
            reasons.append(f"mentions {len(matched)} of your skills: {', '.join(matched)}")
        else:
            reasons.append("mentions none of your skills")

        if posting.kind == "contribution":
            return FitResult(score=round(skill_score * 100 / SKILL_POINTS), eligible=True, reasons=tuple(reasons))

        score: int = skill_score + self._title_points(posting, reasons) + self._location_points(posting, reasons)
        if any(self._mentions(text, term) for term in ENTRY_TERMS):
            score += ENTRY_POINTS
            reasons.append("says it is open to entry-level candidates")

        blockers: list[str] = self._blockers(posting, text)
        reasons.extend(blockers)
        return FitResult(score=min(score, 100), eligible=not blockers, reasons=tuple(reasons))

    def _title_points(self, posting: Posting, reasons: list[str]) -> int:
        """
        :param posting: The posting being scored.
        :param reasons: Reasons so far; a matching title adds one.
        :return: TITLE_POINTS when the title names a target role, else 0.
        """
        title: str = posting.title.lower()
        for phrase in self._profile.target_titles():
            if self._mentions(title, phrase):
                reasons.append(f"title matches '{phrase}'")
                return TITLE_POINTS
        return 0

    def _location_points(self, posting: Posting, reasons: list[str]) -> int:
        """
        :param posting: The posting being scored.
        :param reasons: Reasons so far; the location verdict adds one.
        :return: Full points for an acceptable location, half when none is stated, else 0.
        """
        location: str = posting.location.lower()
        if not location.strip():
            reasons.append("states no location")
            return LOCATION_POINTS // 2
        for place in self._profile.locations():
            if place in location:
                reasons.append(f"location '{posting.location}' is one you accept")
                return LOCATION_POINTS
        reasons.append(f"location '{posting.location}' is not one you listed")
        return 0

    def _blockers(self, posting: Posting, text: str) -> list[str]:
        """
        :param posting: The posting being checked.
        :param text: Its lowercased title and description.
        :return: One reason per hard requirement the owner does not meet; empty when eligible.
        """
        blockers: list[str] = []
        title: str = posting.title.lower()
        senior: list[str] = [term for term in SENIOR_TITLE_TERMS if self._mentions(title, term)]
        if senior:
            blockers.append(f"title is senior ('{senior[0]}')")

        asked: list[int] = [int(match.group(1)) for match in YEARS_PATTERN.finditer(text)]
        limit: int = self._profile.max_experience_years()
        if asked and min(asked) > limit:
            blockers.append(f"asks for {min(asked)}+ years of experience (your limit is {limit})")

        year: int | None = self._profile.graduation_year()
        batches: list[str] = [match.group(1) for pattern in BATCH_PATTERNS for match in pattern.finditer(text)]
        if year is not None and batches:
            allowed: list[int] = [int(value) for batch in batches for value in re.findall(r"20\d\d", batch)]
            if year not in allowed:
                blockers.append(f"restricted to the {' / '.join(batches)} batch (you graduated in {year})")

        for term in self._profile.excluded_terms():
            if self._mentions(text, term):
                blockers.append(f"mentions '{term}', which you excluded")
        return blockers

    @staticmethod
    def _mentions(text: str, phrase: str) -> bool:
        """
        :param text: Lowercased text to search.
        :param phrase: Lowercased word or phrase.
        :return: True when the phrase appears as a whole word or phrase, so "rag" does not match "drag".
        """
        return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None
