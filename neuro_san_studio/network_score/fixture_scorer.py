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

"""Run every repeat of one fixture and score each attempt."""

import logging
import os
from copy import deepcopy
from typing import Any
from unittest import TestCase

from neuro_san.test.unittest.unit_test_assert_forwarder import UnitTestAssertForwarder
from neuro_san.test.util.tests_util import TestsUtil

from neuro_san_studio.network_score.attempt_result import AttemptResult
from neuro_san_studio.network_score.scoring_tests_driver import ScoringTestsDriver
from neuro_san_studio.network_score.token_timed_assert_capture import TokenTimedAssertCapture

logger = logging.getLogger(__name__)


class FixtureScorer:
    """
    Run one fixture `repeats` times against one network and return every attempt's result.

    Unlike a fixture's own `success_ratio` check, this never stops early: the driver is asked for as many successes
    as there are attempts, so it can only return once every attempt has finished or timed out.
    """

    # MINIMAL, the driver's default chat filter, drops the message that carries the final token accounting.
    # MAXIMAL keeps it. Grading reads only the final answer, so the filter does not change a verdict.
    SCORING_CHAT_FILTER = "MAXIMAL"

    def __init__(self, fixture_path: str, repeats: int, agent: str | None = None) -> None:
        """
        Initialize the scorer for one fixture.

        :param fixture_path: Path to the fixture HOCON file.
        :param repeats: How many attempts to run; at least 1.
        :param agent: The network to run the fixture against, or `None` to use the fixture's own `agent`. Comparing
            two networks runs the same fixture with a different agent.
        """
        self._fixture_path = fixture_path
        self._fixture_name = os.path.basename(fixture_path)
        self._repeats = max(1, repeats)
        self._agent = agent

    def score(self) -> list[AttemptResult]:
        """
        Run every attempt and return the results in attempt order.

        :return: One AttemptResult per attempt.
        """
        test_case = TestsUtil.parse_hocon_test_case(None, self._fixture_path)
        test_cases = self.attempt_test_cases(test_case)
        # Neuro SAN's UnitTestAssertForwarder requires a TestCase that supplies assertion implementations.
        driver = ScoringTestsDriver(UnitTestAssertForwarder(TestCase()), test_name=self._fixture_name)
        captures = driver.run_tests(test_cases, len(test_cases))
        results = self.attempt_results(captures)
        logger.info(
            "Scored %s: %d of %d attempts passed",
            self._fixture_name,
            sum(1 for result in results if result.passed),
            len(results),
        )
        return results

    def attempt_test_cases(self, test_case: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Make one independent copy of the test case per attempt, set up for scoring.

        :param test_case: The parsed fixture test case.
        :return: Deep copies with the agent override and scoring chat filter applied.
        """
        test_cases: list[dict[str, Any]] = []
        for _index in range(self._repeats):
            attempt = deepcopy(test_case)
            if self._agent is not None:
                attempt.update({"agent": self._agent})
            for interaction in attempt.get("interactions", []):
                # A fixture that sets its own chat filter keeps it; its attempts then report no tokens.
                if interaction.get("chat_filter") is None:
                    interaction.update({"chat_filter": self.SCORING_CHAT_FILTER})
            test_cases.append(attempt)
        return test_cases

    def attempt_results(self, captures: list[TokenTimedAssertCapture]) -> list[AttemptResult]:
        """
        Turn the driver's captures into attempt results ordered by attempt index.

        The driver returns captures in completion order, and gives a single attempt no index, so both are
        normalized here. The captures are TokenTimedAssertCaptures made by ScoringTestsDriver.

        :param captures: The captures returned by ScoringTestsDriver.run_tests().
        :return: One AttemptResult per capture, sorted by attempt.
        """
        results: list[AttemptResult] = []
        for capture in captures:
            attempt = capture.get_test_index() or 0
            results.append(
                AttemptResult(
                    fixture=self._fixture_name,
                    attempt=attempt,
                    passed=not capture.get_asserts(),
                    total_tokens=capture.get_total_tokens(),
                    total_cost=capture.get_total_cost(),
                )
            )
        results.sort(key=lambda result: result.attempt)
        return results
