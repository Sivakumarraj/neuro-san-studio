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
from datetime import date
from datetime import datetime

from coded_tools.experimental.opportunity_desk.desk_clock import DeskClock
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
# Contributions. Upstream assigns most issues to whoever filed them, so assignment is a prompt to
# ask the assignee first, not a claim. A brand-new issue is usually being worked on by its filer
# (outside fixes that raced the owner were closed), so the best target has waited a week or more.
CONTRIBUTION_SKILL_POINTS: int = 40
UNASSIGNED_POINTS: int = 25
SELF_ASSIGNED_POINTS: int = 15
OTHER_ASSIGNED_POINTS: int = 5
MAINTAINER_POINTS: int = 20
SETTLED_POINTS: int = 15
LONG_OPEN_POINTS: int = 5
SETTLED_MIN_DAYS: int = 7
SETTLED_MAX_DAYS: int = 60
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

    Contributions (repository issues) have no location or seniority bar and are always
    eligible. They score on skills, on who is assigned (nobody, the filer, someone else),
    on a maintainer having filed them, and on having waited a week or more without a fix.
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
            return self._contribution_fit(posting, len(matched), reasons)

        score: int = skill_score + self._title_points(posting, reasons) + self._location_points(posting, reasons)
        if any(self._mentions(text, term) for term in ENTRY_TERMS):
            score += ENTRY_POINTS
            reasons.append("says it is open to entry-level candidates")

        blockers: list[str] = self._blockers(posting, text)
        reasons.extend(blockers)
        return FitResult(score=min(score, 100), eligible=not blockers, reasons=tuple(reasons))

    def _contribution_fit(self, posting: Posting, matched_skills: int, reasons: list[str]) -> FitResult:
        """
        :param posting: An open issue in a tracked repository.
        :param matched_skills: How many of the owner's skills the issue mentions.
        :param reasons: Reasons so far; one is added per signal.
        :return: The fit. Always eligible: whether to start is the assignee's answer to a question.
        """
        score: int = round(CONTRIBUTION_SKILL_POINTS * min(1.0, matched_skills / SKILLS_FOR_FULL_MARKS))
        score += self._assignment_points(posting, reasons)
        if self._filed_by_maintainer(posting):
            score += MAINTAINER_POINTS
            reasons.append("filed by a maintainer, so the fix is wanted")
        score += self._age_points(posting, reasons)
        reasons.append(f"{posting.comments} comment(s)")
        return FitResult(score=min(score, 100), eligible=True, reasons=tuple(reasons))

    @staticmethod
    def _assignment_points(posting: Posting, reasons: list[str]) -> int:
        """
        :param posting: An open issue.
        :param reasons: Reasons so far; the assignment verdict adds one.
        :return: Full points when nobody is assigned, fewer when its filer is (upstream's habit),
            fewest when someone else is.
        """
        assignees: list[str] = [name.strip() for name in posting.claimed_by.split(",") if name.strip()]
        if not assignees:
            reasons.append("nobody is assigned")
            return UNASSIGNED_POINTS
        if posting.filed_by and [name.lower() for name in assignees] == [posting.filed_by.lower()]:
            reasons.append(
                f"assigned to its filer {posting.filed_by}, as upstream usually does: ask them in a comment "
                "whether they would take an outside pull request before writing code"
            )
            return SELF_ASSIGNED_POINTS
        reasons.append(f"assigned to {', '.join(assignees)}: ask them before starting")
        return OTHER_ASSIGNED_POINTS

    def _filed_by_maintainer(self, posting: Posting) -> bool:
        """
        :param posting: An open issue.
        :return: True when the profile's maintainer list names the filer, or, without a list,
            when GitHub marks the filer as a collaborator.
        """
        maintainers: list[str] = self._profile.maintainers()
        if maintainers:
            return posting.filed_by.lower() in maintainers
        return posting.filed_by_maintainer

    @staticmethod
    def _age_points(posting: Posting, reasons: list[str]) -> int:
        """
        :param posting: An open issue.
        :param reasons: Reasons so far; the age verdict adds one.
        :return: The most for an issue that has waited SETTLED_MIN_DAYS to SETTLED_MAX_DAYS, none
            for a brand-new one, a little for an old one.
        """
        opened: date | None = FitAssessor._date(posting.posted_at)
        if opened is None:
            return 0
        age: int = (DeskClock.today() - opened).days
        if age < SETTLED_MIN_DAYS:
            reasons.append(f"only {age} day(s) old: its filer is probably working on it")
            return 0
        if age <= SETTLED_MAX_DAYS:
            reasons.append(f"open {age} days without a fix")
            return SETTLED_POINTS
        reasons.append(f"open {age} days")
        return LONG_OPEN_POINTS

    @staticmethod
    def _date(stamp: str) -> date | None:
        """
        :param stamp: An ISO 8601 timestamp, possibly ending in "Z", or empty.
        :return: Its date, or None when there is no usable timestamp.
        """
        try:
            return datetime.fromisoformat(stamp.replace("Z", "+00:00")).date()
        except ValueError:
            return None

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
