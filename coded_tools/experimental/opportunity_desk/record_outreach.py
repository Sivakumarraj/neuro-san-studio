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

logger = logging.getLogger(__name__)


class RecordOutreach(CodedTool):
    """
    Records a message the owner sent or received, which is what OutreachGate's
    cadence rules read. Only the owner knows what actually went out, so the desk
    keeps this record from what they tell it rather than from any mailbox.
    """

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> str:
        """
        :param args: "contact_id", "direction" ("sent" or "received"), optional
            "happened_on" (YYYY-MM-DD, default today) and "summary".
        :param sly_data: Unused.
        :return: A confirmation with the contact's last few events, or a message starting with "Error:".
        """
        contact_id: str = str(args.get("contact_id") or "")
        direction: str = str(args.get("direction") or "")
        happened_on: str = str(args.get("happened_on") or DeskClock.today().isoformat())
        try:
            profile: DeskProfile = DeskProfile.load()
            if profile.contact(contact_id) is None:
                known: str = ", ".join(profile.contact_ids())
                return f"Error: '{contact_id}' is not in your profile. Known contacts: {known}."
            store: DeskStore = DeskStore()
            now: str = DeskClock.now_iso()
            store.record_outreach(contact_id, direction, happened_on, str(args.get("summary") or ""))
        except ValueError as error:
            logger.warning("RecordOutreach refused the request: %s", error)
            return f"Error: {error}"
        store.log("outreach_recorded", {"contact_id": contact_id, "direction": direction, "on": happened_on}, now)
        recent: list[dict[str, Any]] = store.outreach_history(contact_id)[-3:]
        trail: str = "; ".join(f"{event.get('happened_on')} {event.get('direction')}" for event in recent)
        return f"Recorded: {direction} on {happened_on} for {contact_id}. Latest events: {trail}."

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> str:
        """
        Run invoke in a worker thread, because it reads files and SQLite.

        :param args: See invoke.
        :param sly_data: See invoke.
        :return: See invoke.
        """
        return await asyncio.to_thread(self.invoke, args, sly_data)
