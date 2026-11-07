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
import os
import uuid
from typing import Any

import numpy as np
from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.experimental.decision_prescriptor.decision_keys import DecisionKeys
from coded_tools.experimental.decision_prescriptor.pareto_report import ParetoReport

logger = logging.getLogger(__name__)


class RenderParetoReport(CodedTool):
    """
    Stage 4 of registries/experimental/decision_prescriptor.hocon: write the
    trade-off front out as a self-contained HTML report.
    """

    DEFAULT_OUTPUT_PATH: str = "decision_prescriptor_report.html"

    # Every report goes into this folder of the server's working directory, so an LLM-chosen
    # name can never overwrite anything else there, such as a UI template.
    REPORT_DIRECTORY: str = "decision_prescriptor_reports"

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> str:
        """
        Render the charts and return the path to the file written.

        The name comes from an LLM, so only its file name is used, it must end in .html,
        and the report is always a new file in REPORT_DIRECTORY. A short random suffix
        keeps two sessions from writing, or handing out, the same file.

        :param args: May contain "title" and "output_path".
        :param sly_data: Must hold the spec and the evolved result.
        :return: The path written, or a message starting with "Error:".
        """
        spec: dict[str, Any] | None = sly_data.get(DecisionKeys.SPEC)
        result: dict[str, Any] | None = sly_data.get(DecisionKeys.RESULT)
        if not spec or not result:
            return self._error("nothing to render yet. Evolve the prescriptors first.")

        title: str = str(args.get("title") or "Decision trade-off front")
        # Any folders in the requested path are dropped; the file name alone is kept.
        file_name: str = os.path.basename(str(args.get("output_path") or self.DEFAULT_OUTPUT_PATH))
        if not file_name.endswith(".html") or file_name == ".html":
            return self._error("the report file name must end in .html.")
        report_directory: str = os.path.join(os.path.realpath(os.getcwd()), self.REPORT_DIRECTORY)
        output_path: str = os.path.join(report_directory, f"{file_name[: -len('.html')]}-{uuid.uuid4().hex[:8]}.html")

        front: np.ndarray = result.get("front")
        balanced: int = self._balanced_index(front)

        summary: dict[str, str] = {
            "Strategies on front": f"{result.get('archive_size'):,}",
            "Shown here": str(front.shape[0]),
            "Generations": str(result.get("generations")),
            "Search time": f"{result.get('elapsed_seconds'):.1f}s",
        }

        document: str = ParetoReport.render(
            title=title,
            front=front,
            dominated=result.get("population"),
            actions=result.get("actions"),
            objective_labels=spec.get("outcome_fields"),
            action_labels=spec.get("action_fields"),
            hypervolume_history=result.get("hypervolume_history"),
            summary=summary,
            balanced_index=balanced,
        )

        try:
            os.makedirs(report_directory, exist_ok=True)
            # "x" creates the file and fails rather than replace one that already exists.
            with open(output_path, "x", encoding="utf-8") as handle:
                handle.write(document)
        except OSError as error:
            logger.error("Could not write the trade-off report to %s: %s", output_path, error)
            return f"Error writing the report: {error}"

        logger.info("Wrote the trade-off report to %s", output_path)
        return (
            f"Wrote the trade-off report to {output_path} "
            f"({front.shape[0]} strategies charted, balanced pick highlighted as strategy {balanced + 1})."
        )

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> str:
        """
        Run invoke in a worker thread, because rendering and the file write both block.

        :param args: See invoke.
        :param sly_data: See invoke.
        :return: See invoke.
        """
        return await asyncio.to_thread(self.invoke, args, sly_data)

    @staticmethod
    def _balanced_index(front: np.ndarray) -> int:
        """
        Pick the strategy closest to the center of the front, in normalized units.

        This is offered as a starting point for discussion, not a recommendation.
        Nothing in the mathematics prefers the middle of a front; only a human who
        knows what the objectives are worth can rank them.

        :param front: Objective values per strategy, in display orientation.
        :return: Row index of the most central strategy.
        """
        low: np.ndarray = front.min(axis=0)
        high: np.ndarray = front.max(axis=0)
        span: np.ndarray = np.where((high - low) < 1e-12, 1.0, high - low)
        normalized: np.ndarray = (front - low) / span
        return int(np.argmin(np.linalg.norm(normalized - 0.5, axis=1)))

    @staticmethod
    def _error(message: str) -> str:
        """
        Log a refused request and phrase it for the agent that called the tool.

        :param message: What was wrong with the request.
        :return: The message prefixed with "Error:", which the front man relays and stops on.
        """
        logger.warning("RenderParetoReport refused the request: %s", message)
        return f"Error: {message}"
