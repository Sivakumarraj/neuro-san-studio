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
from typing import Any

from coded_tools.experimental.opportunity_desk.outreach_decision import OutreachDecision

# Markdown that Gmail and LinkedIn show literally: bold, headings, bullets, links.
MARKDOWN_PATTERN: re.Pattern[str] = re.compile(
    r"\*\*|__|^\s{0,3}#{1,6}\s|^\s*[-*+]\s|\[[^\]]+\]\([^)]+\)", re.MULTILINE
)
CONTACT_STATUSES: tuple[str, ...] = ("open", "technical_only", "reply_only", "do_not_contact")


# One question per class, so one public method.
# pylint: disable=too-few-public-methods
class OutreachRules:
    """
    Decides, in code, whether a draft message may go to a contact.

    The rules are the ones a prompt cannot be trusted to keep under pressure:
    - an unknown contact or one marked do_not_contact gets nothing;
    - a reply_only contact gets a message only when they wrote last;
    - nobody gets more than max_unanswered messages in a row without a reply
      (default 1: one message, then wait), and a permitted follow-up still waits
      cooldown_days after the last one;
    - a technical_only contact gets no hiring language at all;
    - banned phrases, markdown and drafts over max_words are refused.

    History is the owner's own record of what was sent and received (see DeskStore);
    the network never sends anything itself.
    """

    def __init__(self, policy: dict[str, Any]):
        """
        :param policy: DeskProfile.outreach_policy(): max_unanswered, cooldown_days,
            max_words, banned_phrases and role_terms.
        """
        self._policy: dict[str, Any] = policy

    def review(
        self, contact: dict[str, Any] | None, history: list[dict[str, Any]], body: str, today: date
    ) -> OutreachDecision:
        """
        :param contact: The contact's profile record, or None when unknown.
        :param history: Recorded events for the contact, oldest first, each with
            "direction" ("sent" or "received") and "happened_on" (YYYY-MM-DD).
        :param body: The draft message.
        :param today: The date the draft would be sent.
        :return: Whether it may be sent, and every rule it broke.
        """
        if contact is None:
            return OutreachDecision(allowed=False, reasons=("this contact is not in your profile; add them first",))

        reasons: list[str] = []
        status: str = contact.get("status", "open")
        if status not in CONTACT_STATUSES:
            reasons.append(f"unknown contact status '{status}'; use one of {', '.join(CONTACT_STATUSES)}")
        if status == "do_not_contact":
            reasons.append(f"marked do_not_contact ({contact.get('reason', 'no reason recorded')})")

        reasons.extend(self._cadence(contact, history, status, today))
        reasons.extend(self._content(body, status))
        return OutreachDecision(allowed=not reasons, reasons=tuple(reasons))

    def _cadence(self, contact: dict[str, Any], history: list[dict[str, Any]], status: str, today: date) -> list[str]:
        """
        :param contact: The contact's profile record; may override max_unanswered.
        :param history: Recorded events, oldest first.
        :param status: The contact's status.
        :param today: The date the draft would be sent.
        :return: Reasons the timing is wrong, if any.
        """
        reasons: list[str] = []
        unanswered: list[dict[str, Any]] = []
        for event in history:
            if event.get("direction") == "received":
                unanswered = []
            else:
                unanswered.append(event)

        if status == "reply_only" and (not history or unanswered):
            reasons.append("reply_only: write only after they write to you")

        limit: int = int(contact.get("max_unanswered", self._policy.get("max_unanswered")))
        if unanswered and len(unanswered) >= limit:
            reasons.append(
                f"{len(unanswered)} message(s) since their last reply, the latest on "
                f"{unanswered[-1].get('happened_on')}; the limit is {limit}, so wait for them to answer"
            )
        elif unanswered:
            waited: int = (today - date.fromisoformat(unanswered[-1].get("happened_on"))).days
            cooldown: int = int(self._policy.get("cooldown_days"))
            if waited < cooldown:
                reasons.append(f"only {waited} day(s) since your last message; wait at least {cooldown}")
        return reasons

    def _content(self, body: str, status: str) -> list[str]:
        """
        :param body: The draft message.
        :param status: The contact's status.
        :return: Reasons the wording is wrong, if any.
        """
        reasons: list[str] = []
        lowered: str = body.lower()
        if not body.strip():
            reasons.append("the draft is empty")

        words: int = len(body.split())
        max_words: int = int(self._policy.get("max_words"))
        if words > max_words:
            reasons.append(f"{words} words; keep it under {max_words}")

        if MARKDOWN_PATTERN.search(body):
            reasons.append("contains markdown, which email and LinkedIn show literally; use plain text")

        banned: list[str] = [phrase for phrase in self._policy.get("banned_phrases") if phrase in lowered]
        if banned:
            reasons.append(f"uses phrases you banned: {', '.join(banned)}")

        if status == "technical_only":
            found: list[str] = [
                term
                for term in self._policy.get("role_terms")
                if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lowered)
            ]
            if found:
                reasons.append(f"technical_only contact: remove hiring language ({', '.join(found)})")
        return reasons
