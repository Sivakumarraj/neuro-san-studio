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

"""Paired comparison of two networks run on the same fixture attempts."""

from typing import Any

from neuro_san_studio.network_score.network_scorecard import NetworkScorecard
from neuro_san_studio.network_score.sign_test import SignTest


class PairedComparison:
    """
    Compare a baseline and a candidate network attempt by attempt.

    Attempt i of a fixture on the baseline is paired with attempt i of the same fixture on the candidate. Attempts
    are independent repeats, so the pairing order carries no meaning; it only makes each pair share a fixture.
    Fixtures or attempts present on one side only are left out of the pairs and counted as unpaired.
    """

    def __init__(self, baseline: NetworkScorecard, candidate: NetworkScorecard) -> None:
        """
        Pair the two scorecards' attempts.

        :param baseline: The network being compared against.
        :param candidate: The network being evaluated.
        """
        self._baseline = baseline
        self._candidate = candidate
        candidate_passes: dict[tuple[str, int], bool] = {}
        for attempt in candidate.attempts():
            candidate_passes.update({(attempt.fixture, attempt.attempt): attempt.passed})
        self._baseline_only = 0
        self._candidate_only = 0
        self._paired = 0
        for attempt in baseline.attempts():
            candidate_passed = candidate_passes.get((attempt.fixture, attempt.attempt))
            if candidate_passed is None:
                continue
            self._paired += 1
            if attempt.passed and not candidate_passed:
                self._baseline_only += 1
            elif candidate_passed and not attempt.passed:
                self._candidate_only += 1

    def paired_count(self) -> int:
        """
        Return the number of attempt pairs.

        :return: The pair count.
        """
        return self._paired

    def baseline_only_passes(self) -> int:
        """
        Return the pairs where only the baseline passed.

        :return: The count of such pairs.
        """
        return self._baseline_only

    def candidate_only_passes(self) -> int:
        """
        Return the pairs where only the candidate passed.

        :return: The count of such pairs.
        """
        return self._candidate_only

    def p_value(self) -> float:
        """
        Return the exact two-sided sign-test p-value on the discordant pairs.

        :return: The p-value.
        """
        return SignTest.two_sided_p_value(self._baseline_only, self._candidate_only)

    def to_dict(self) -> dict[str, Any]:
        """
        Return the comparison as JSON-ready data.

        :return: Both pass rates, the cost difference and the sign test.
        """
        baseline_cost = self._baseline.mean_cost_per_question()
        candidate_cost = self._candidate.mean_cost_per_question()
        cost_difference = None
        if baseline_cost is not None and candidate_cost is not None:
            cost_difference = candidate_cost - baseline_cost
        unpaired = self._baseline.attempt_count() + self._candidate.attempt_count() - 2 * self._paired
        return {
            "baseline": self._baseline.network(),
            "candidate": self._candidate.network(),
            "baseline_pass_rate": self._baseline.pass_rate(),
            "candidate_pass_rate": self._candidate.pass_rate(),
            "mean_cost_difference_per_question": cost_difference,
            "paired_attempts": self._paired,
            "unpaired_attempts": unpaired,
            "baseline_only_passes": self._baseline_only,
            "candidate_only_passes": self._candidate_only,
            "sign_test_p_value": self.p_value(),
        }
