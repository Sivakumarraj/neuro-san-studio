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
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# The owner's real profile names real people, so it never lives in the repository:
# point this variable at a private file (a secret file on the host in production).
PROFILE_ENV: str = "OPPORTUNITY_DESK_PROFILE"
EXAMPLE_PROFILE: Path = Path(__file__).with_name("example_profile.json")

DEFAULT_ROLE_TERMS: tuple[str, ...] = (
    "job",
    "jobs",
    "hiring",
    "hire",
    "referral",
    "refer",
    "opening",
    "openings",
    "vacancy",
    "position",
    "resume",
    "cv",
    "interview",
    "internship",
)


class DeskProfile:
    """
    Read-only view of the owner's profile: what to look for, where to look, and the
    rules every outreach draft has to pass.

    The profile is plain JSON so it can be edited without touching code. The bundled
    example_profile.json holds fictional data and is used only when
    OPPORTUNITY_DESK_PROFILE is unset, in which case is_example() says so and the
    front man tells the user.
    """

    def __init__(self, data: dict[str, Any]):
        """
        :param data: The parsed profile document.
        """
        self._data: dict[str, Any] = data

    @staticmethod
    def load(path: str | None = None) -> "DeskProfile":
        """
        Load the profile from the given path, else from OPPORTUNITY_DESK_PROFILE, else the bundled example.

        :param path: Optional explicit path, mainly for tests.
        :return: The loaded profile.
        :raises ValueError: When the file is missing, unreadable or not a JSON object.
            The message names the path so the operator can act on it.
        """
        chosen: str = path or os.getenv(PROFILE_ENV) or str(EXAMPLE_PROFILE)
        try:
            with open(chosen, encoding="utf-8") as profile_file:
                data: Any = json.load(profile_file)
        except OSError as error:
            raise ValueError(f"cannot read the profile at {chosen}: {error}") from error
        except json.JSONDecodeError as error:
            raise ValueError(f"the profile at {chosen} is not valid JSON: {error}") from error
        if not isinstance(data, dict):
            raise ValueError(f"the profile at {chosen} must be a JSON object")
        logger.info("Loaded the opportunity desk profile from %s", chosen)
        return DeskProfile(data)

    def is_example(self) -> bool:
        """
        :return: True when this is the bundled fictional profile rather than the owner's own.
        """
        return bool(self._data.get("example", False))

    def skills(self) -> list[str]:
        """
        :return: The owner's skills, lowercased, matched as whole words against postings.
        """
        return self._lowered("skills")

    def target_titles(self) -> list[str]:
        """
        :return: Phrases that mark a title as the kind of role the owner wants.
        """
        return self._lowered("target_titles")

    def locations(self) -> list[str]:
        """
        :return: Acceptable locations, lowercased; "remote" matches remote postings.
        """
        return self._lowered("locations")

    def excluded_terms(self) -> list[str]:
        """
        :return: Terms that rule a posting out wherever they appear.
        """
        return self._lowered("excluded_terms")

    def graduation_year(self) -> int | None:
        """
        :return: The owner's graduation year, used to reject batch-restricted postings.
        """
        year: Any = self._owner().get("graduation_year")
        return int(year) if year is not None else None

    def max_experience_years(self) -> int:
        """
        :return: The most years of experience a posting may ask for. Defaults to 1.
        """
        return int(self._owner().get("max_experience_years", 1))

    def boards(self) -> list[dict[str, Any]]:
        """
        :return: Careers boards to scan, each {"provider", "slug", "company"}.
        """
        return list(self._data.get("boards") or [])

    def contribution_repos(self) -> list[dict[str, Any]]:
        """
        :return: Repositories whose open issues count as opportunities, each {"repo", "labels"}.
        """
        return list(self._data.get("contribution_repos") or [])

    def github_user(self) -> str:
        """
        :return: The owner's GitHub login, whose upstream pull requests and issues are tracked, or "".
        """
        return str(self._data.get("github_user") or "")

    def upstream_repos(self) -> list[str]:
        """
        :return: The "owner/name" repositories the owner contributes to, for contribution tracking.
        """
        return [str(repo) for repo in self._data.get("upstream_repos") or []]

    def min_score(self) -> int:
        """
        :return: The score a posting needs before it is shown as a match. Defaults to 40.
        """
        return int(self._data.get("min_score", 40))

    def evidence_threshold(self) -> float:
        """
        :return: The share of claims that must check out before research is accepted
            without escalation. Defaults to 0.7.
        """
        return float(self._data.get("evidence_threshold", 0.7))

    def contact(self, contact_id: str) -> dict[str, Any] | None:
        """
        :param contact_id: The key under "contacts".
        :return: The contact's record, or None when the profile does not know them.
        """
        contacts: dict[str, Any] = self._data.get("contacts") or {}
        return contacts.get(contact_id)

    def known_history(self, contact_id: str) -> list[dict[str, Any]]:
        """
        :param contact_id: The key under "contacts".
        :return: Messages the profile records for the contact (each "direction" and
            "happened_on"), from before the desk kept its own record. Empty when none.
        :raises ValueError: When an entry has an unknown direction or a malformed date.
        """
        events: list[dict[str, Any]] = list((self.contact(contact_id) or {}).get("history") or [])
        for event in events:
            if event.get("direction") not in ("sent", "received"):
                raise ValueError(f"history for '{contact_id}' has an entry without direction sent or received")
            date.fromisoformat(str(event.get("happened_on")))
        return events

    def contact_ids(self) -> list[str]:
        """
        :return: Every contact the profile knows, so a refusal can list valid ids.
        """
        return sorted((self._data.get("contacts") or {}).keys())

    def outreach_policy(self) -> dict[str, Any]:
        """
        :return: The rules every draft has to pass, with defaults filled in.
        """
        policy: dict[str, Any] = self._data.get("outreach") or {}
        return {
            "max_unanswered": int(policy.get("max_unanswered", 1)),
            "cooldown_days": int(policy.get("cooldown_days", 7)),
            "max_words": int(policy.get("max_words", 180)),
            "banned_phrases": [phrase.lower() for phrase in policy.get("banned_phrases") or []],
            "role_terms": [term.lower() for term in policy.get("role_terms") or DEFAULT_ROLE_TERMS],
        }

    def _owner(self) -> dict[str, Any]:
        """
        :return: The "owner" section, or an empty dict.
        """
        return self._data.get("owner") or {}

    def _lowered(self, key: str) -> list[str]:
        """
        :param key: A top-level key holding a list of strings.
        :return: The list lowercased and stripped, empty entries dropped.
        """
        return [str(value).strip().lower() for value in self._data.get(key) or [] if str(value).strip()]
