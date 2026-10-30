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

"""Tests for one network's scorecard."""

from unittest import TestCase

from neuro_san_studio.network_score.attempt_result import AttemptResult
from neuro_san_studio.network_score.network_scorecard import NetworkScorecard


class TestNetworkScorecard(TestCase):
    """Verify pass rate and cost figures over every attempt."""

    ATTEMPTS = [
        AttemptResult(fixture="a.hocon", attempt=0, passed=True, total_tokens=100, total_cost=0.002),
        AttemptResult(fixture="a.hocon", attempt=1, passed=False, total_tokens=300, total_cost=0.004),
        AttemptResult(fixture="b.hocon", attempt=0, passed=True, total_tokens=200, total_cost=0.003),
        AttemptResult(fixture="b.hocon", attempt=1, passed=False, total_tokens=None, total_cost=None),
    ]

    def test_pass_rate_counts_every_attempt(self) -> None:
        """Two of four attempts passed, whatever the fixtures' success ratios say."""
        scorecard = NetworkScorecard("basic/net", self.ATTEMPTS)

        self.assertEqual(4, scorecard.attempt_count())
        self.assertEqual(2, scorecard.passed_count())
        self.assertAlmostEqual(0.5, scorecard.pass_rate())

    def test_costs_use_only_attempts_that_reported_one(self) -> None:
        """The attempt with no accounting is left out of the cost figures, not counted as free."""
        scorecard = NetworkScorecard("basic/net", self.ATTEMPTS)

        self.assertEqual(3, len(scorecard.costed_attempts()))
        self.assertAlmostEqual(0.003, scorecard.mean_cost_per_question())
        self.assertAlmostEqual(200.0, scorecard.mean_tokens_per_question())
        # 0.009 spent on the costed attempts, two of which passed.
        self.assertAlmostEqual(0.0045, scorecard.cost_per_correct_answer())

    def test_fixture_rows_keep_first_seen_order(self) -> None:
        """Each fixture gets one row with its own passes and mean cost."""
        rows = NetworkScorecard("basic/net", self.ATTEMPTS).fixture_rows()

        self.assertEqual(["a.hocon", "b.hocon"], [row.get("fixture") for row in rows])
        self.assertEqual(1, rows[0].get("passed"))
        self.assertEqual(2, rows[0].get("attempts"))
        self.assertAlmostEqual(0.003, rows[1].get("mean_cost_per_question"))

    def test_empty_scorecard_reports_unknown(self) -> None:
        """With no attempts every rate and cost is unknown."""
        scorecard = NetworkScorecard("basic/net", [])

        self.assertIsNone(scorecard.pass_rate())
        self.assertIsNone(scorecard.mean_cost_per_question())
        self.assertIsNone(scorecard.cost_per_correct_answer())
        self.assertEqual([], scorecard.to_dict().get("fixtures"))
