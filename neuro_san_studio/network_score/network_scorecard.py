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

"""Pass rate and spend of one network over every attempt of its fixtures."""

from typing import Any

from neuro_san_studio.network_score.attempt_result import AttemptResult


class NetworkScorecard:
    """
    Summarize every attempt of one network.

    The pass rate counts all attempts, not fixtures that met their `success_ratio`. Cost figures use only the
    attempts that reported token accounting, and say how many those were, so a missing count is never read as free.
    """

    def __init__(self, network: str, attempts: list[AttemptResult]) -> None:
        """
        Initialize the scorecard.

        :param network: The network name, as used in `ns chat` and fixtures.
        :param attempts: Every attempt of every fixture for this network.
        """
        self._network = network
        self._attempts = list(attempts)

    def network(self) -> str:
        """
        Return the network name.

        :return: The network name.
        """
        return self._network

    def attempts(self) -> list[AttemptResult]:
        """
        Return every attempt.

        :return: A copy of the attempt list.
        """
        return list(self._attempts)

    def attempt_count(self) -> int:
        """
        Return the number of attempts.

        :return: The attempt count.
        """
        return len(self._attempts)

    def passed_count(self) -> int:
        """
        Return the number of passing attempts.

        :return: The passing attempt count.
        """
        return sum(1 for attempt in self._attempts if attempt.passed)

    def pass_rate(self) -> float | None:
        """
        Return the share of attempts that passed.

        :return: Passed over attempted, or `None` with no attempts.
        """
        if not self._attempts:
            return None
        return self.passed_count() / len(self._attempts)

    def costed_attempts(self) -> list[AttemptResult]:
        """
        Return the attempts that reported a cost.

        :return: Attempts whose total cost is known.
        """
        return [attempt for attempt in self._attempts if attempt.total_cost is not None]

    def mean_cost_per_question(self) -> float | None:
        """
        Return the mean cost of one attempt, over the attempts that reported a cost.

        :return: Mean US dollars per attempt, or `None` when no attempt reported a cost.
        """
        costed = self.costed_attempts()
        if not costed:
            return None
        return sum(attempt.total_cost for attempt in costed) / len(costed)

    def mean_tokens_per_question(self) -> float | None:
        """
        Return the mean tokens of one attempt, over the attempts that reported tokens.

        :return: Mean tokens per attempt, or `None` when no attempt reported tokens.
        """
        counted = [attempt for attempt in self._attempts if attempt.total_tokens is not None]
        if not counted:
            return None
        return sum(attempt.total_tokens for attempt in counted) / len(counted)

    def cost_per_correct_answer(self) -> float | None:
        """
        Return total spend divided by passing attempts, over the attempts that reported a cost.

        This charges failed attempts to the correct ones, which is what a user pays for each good answer.

        :return: US dollars per passing attempt, or `None` when nothing costed passed.
        """
        costed = self.costed_attempts()
        passed = sum(1 for attempt in costed if attempt.passed)
        if passed == 0:
            return None
        return sum(attempt.total_cost for attempt in costed) / passed

    def fixture_rows(self) -> list[dict[str, Any]]:
        """
        Return one summary row per fixture, in first-seen order.

        :return: Rows with the fixture name, passes, attempts and mean cost.
        """
        by_fixture: dict[str, list[AttemptResult]] = {}
        for attempt in self._attempts:
            by_fixture.setdefault(attempt.fixture, []).append(attempt)
        rows: list[dict[str, Any]] = []
        for fixture, attempts in by_fixture.items():
            fixture_card = NetworkScorecard(self._network, attempts)
            rows.append(
                {
                    "fixture": fixture,
                    "passed": fixture_card.passed_count(),
                    "attempts": fixture_card.attempt_count(),
                    "mean_cost_per_question": fixture_card.mean_cost_per_question(),
                    "mean_tokens_per_question": fixture_card.mean_tokens_per_question(),
                }
            )
        return rows

    def to_dict(self) -> dict[str, Any]:
        """
        Return the scorecard as JSON-ready data.

        :return: Totals and per-fixture rows.
        """
        return {
            "network": self._network,
            "attempts": self.attempt_count(),
            "passed": self.passed_count(),
            "pass_rate": self.pass_rate(),
            "costed_attempts": len(self.costed_attempts()),
            "mean_cost_per_question": self.mean_cost_per_question(),
            "mean_tokens_per_question": self.mean_tokens_per_question(),
            "cost_per_correct_answer": self.cost_per_correct_answer(),
            "fixtures": self.fixture_rows(),
        }
