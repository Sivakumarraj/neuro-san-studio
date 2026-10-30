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

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.experimental.opportunity_desk.desk_clock import DeskClock
from coded_tools.experimental.opportunity_desk.desk_profile import DeskProfile
from coded_tools.experimental.opportunity_desk.desk_store import DeskStore
from coded_tools.experimental.opportunity_desk.outreach_decision import OutreachDecision
from coded_tools.experimental.opportunity_desk.outreach_rules import OutreachRules

logger = logging.getLogger(__name__)


class OutreachGate(CodedTool):
    """
    The safeguard on every outgoing message: checks a draft against OutreachRules and,
    only when it passes, returns it as a copy-paste-ready plain-text block.

    The network never sends a message. The owner does, after reading the block. The
    gate makes sure that what reaches them has already passed the contact's status,
    the reply cadence and the wording rules, and it writes every decision, pass or
    block, to the audit log. Message bodies are not logged, only the verdict.
    """

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> str:
        """
        :param args: "contact_id", "body", and optional "subject".
        :param sly_data: Unused.
        :return: "CLEARED" followed by the block, or a message starting with "Error: Blocked".
        """
        contact_id: str = str(args.get("contact_id") or "")
        body: str = str(args.get("body") or "").strip()
        subject: str = str(args.get("subject") or "").strip()
        try:
            profile: DeskProfile = DeskProfile.load()
            store: DeskStore = DeskStore()
            history: list[dict[str, Any]] = self._history(profile, store, contact_id)
        except ValueError as error:
            return f"Error: {error}"

        contact: dict[str, Any] | None = profile.contact(contact_id)
        decision: OutreachDecision = OutreachRules(profile.outreach_policy()).review(
            contact, history, f"{subject}\n{body}", DeskClock.today()
        )
        now: str = DeskClock.now_iso()
        if not decision.allowed:
            store.log("outreach_blocked", {"contact_id": contact_id, "reasons": list(decision.reasons)}, now)
            logger.info("Blocked a draft to %s: %s", contact_id, "; ".join(decision.reasons))
            return self._blocked(decision, profile.contact_ids() if contact is None else [])

        store.log("outreach_cleared", {"contact_id": contact_id, "words": len(body.split())}, now)
        header: str = self._recipient(contact_id, contact)
        if subject:
            header += f"\nSubject: {subject}"
        return f"CLEARED\n{header}\n\n{body}"

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> str:
        """
        Run invoke in a worker thread, because it reads files and SQLite.

        :param args: See invoke.
        :param sly_data: See invoke.
        :return: See invoke.
        """
        return await asyncio.to_thread(self.invoke, args, sly_data)

    @staticmethod
    def _blocked(decision: OutreachDecision, known_contacts: list[str]) -> str:
        """
        :param decision: A refusal from OutreachRules.
        :param known_contacts: Valid contact ids to list when the contact was unknown, else empty.
        :return: The numbered reasons, prefixed with "Error: Blocked.".
        """
        reasons: str = " ".join(f"({index}) {reason}." for index, reason in enumerate(decision.reasons, 1))
        known: str = f" Known contacts: {', '.join(known_contacts)}." if known_contacts else ""
        return f"Error: Blocked. {reasons}{known}"

    @staticmethod
    def _history(profile: DeskProfile, store: DeskStore, contact_id: str) -> list[dict[str, Any]]:
        """
        :param profile: The owner's profile, which may list messages from before the desk kept a record.
        :param store: The desk store, with everything recorded since.
        :param contact_id: The contact's key.
        :return: Both, oldest first, so a fresh deployment with an empty store still knows who is owed a reply.
        :raises ValueError: When the profile's history for the contact is malformed.
        """
        return sorted(
            profile.known_history(contact_id) + store.outreach_history(contact_id),
            key=lambda event: str(event.get("happened_on")),
        )

    @staticmethod
    def _recipient(contact_id: str, contact: dict[str, Any]) -> str:
        """
        :param contact_id: The contact's key, used when the record has no name.
        :param contact: The contact's profile record.
        :return: "To: Name <email>", or "To: Name (channel)" for a contact without an email.
        """
        name: str = str(contact.get("name") or contact_id)
        email: str = str(contact.get("email") or "")
        if email:
            return f"To: {name} <{email}>"
        channel: str = str(contact.get("channel") or "")
        return f"To: {name} ({channel})" if channel else f"To: {name}"
