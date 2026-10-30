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

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.experimental.opportunity_desk.desk_clock import DeskClock
from coded_tools.experimental.opportunity_desk.desk_store import STATUSES
from coded_tools.experimental.opportunity_desk.desk_store import DeskStore

logger = logging.getLogger(__name__)

ACTIONS: tuple[str, ...] = ("list", "update", "audit")
MAX_ROWS: int = 100


class PipelineTracker(CodedTool):
    """
    Lists tracked opportunities, moves one through the pipeline, or shows the audit log.

    Status values are checked here, not by the agent, so the pipeline can never hold
    a status the digest and the reports do not understand.
    """

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> str:
        """
        :param args: "action" is "list" (optional "status", "min_score", "limit"),
            "update" ("opportunity_id", "status", optional "note") or "audit" (optional "limit").
        :param sly_data: Unused.
        :return: JSON for the agent to present, or a message starting with "Error:".
        """
        action: str = str(args.get("action") or "list")
        if action not in ACTIONS:
            return self._error(f"unknown action '{action}'; use one of {', '.join(ACTIONS)}")
        try:
            limit: int = max(1, min(int(args.get("limit") or 20), MAX_ROWS))
            store: DeskStore = DeskStore()
            if action == "list":
                rows: list[dict[str, Any]] = store.list_opportunities(
                    status=args.get("status") or None, min_score=int(args.get("min_score") or 0), limit=limit
                )
                return json.dumps({"count": len(rows), "statuses": list(STATUSES), "opportunities": rows})
            if action == "audit":
                return json.dumps({"entries": store.audit_tail(limit)})
            return self._update(store, args)
        except ValueError as error:
            return self._error(str(error))

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> str:
        """
        Run invoke in a worker thread, because SQLite calls block.

        :param args: See invoke.
        :param sly_data: See invoke.
        :return: See invoke.
        """
        return await asyncio.to_thread(self.invoke, args, sly_data)

    def _update(self, store: DeskStore, args: dict[str, Any]) -> str:
        """
        :param store: The desk store.
        :param args: "opportunity_id", "status" and optional "note".
        :return: A confirmation, or a message starting with "Error:".
        :raises ValueError: For a status outside STATUSES.
        """
        opportunity_id: str = str(args.get("opportunity_id") or "")
        status: str = str(args.get("status") or "")
        now: str = DeskClock.now_iso()
        if not store.update_status(opportunity_id, status, str(args.get("note") or ""), now):
            return self._error(f"no tracked opportunity has the id '{opportunity_id}'")
        store.log("status_changed", {"opportunity_id": opportunity_id, "status": status}, now)
        return f"Moved {opportunity_id} to '{status}'."

    @staticmethod
    def _error(message: str) -> str:
        """
        :param message: What went wrong.
        :return: The message prefixed with "Error:".
        """
        logger.warning("PipelineTracker refused the request: %s", message)
        return f"Error: {message}"
