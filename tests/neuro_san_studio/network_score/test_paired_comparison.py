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

"""Tests for the paired comparison of two networks."""

from unittest import TestCase

from neuro_san_studio.network_score.attempt_result import AttemptResult
from neuro_san_studio.network_score.network_scorecard import NetworkScorecard
from neuro_san_studio.network_score.paired_comparison import PairedComparison
from neuro_san_studio.network_score.sign_test import SignTest


class TestPairedComparison(TestCase):
    """Verify pairing by fixture and attempt, and the sign test on discordant pairs."""

    BASELINE = NetworkScorecard(
        "basic/old",
        [
            AttemptResult(fixture="a.hocon", attempt=0, passed=True, total_tokens=10, total_cost=0.001),
            AttemptResult(fixture="a.hocon", attempt=1, passed=False, total_tokens=10, total_cost=0.001),
            AttemptResult(fixture="b.hocon", attempt=0, passed=False, total_tokens=10, total_cost=0.001),
            AttemptResult(fixture="c.hocon", attempt=0, passed=True, total_tokens=10, total_cost=0.001),
        ],
    )
    CANDIDATE = NetworkScorecard(
        "basic/new",
        [
            AttemptResult(fixture="a.hocon", attempt=0, passed=True, total_tokens=20, total_cost=0.003),
            AttemptResult(fixture="a.hocon", attempt=1, passed=True, total_tokens=20, total_cost=0.003),
            AttemptResult(fixture="b.hocon", attempt=0, passed=True, total_tokens=20, total_cost=0.003),
        ],
    )

    def test_discordant_pairs_are_counted(self) -> None:
        """Only pairs where exactly one network passed count; c.hocon has no partner."""
        comparison = PairedComparison(self.BASELINE, self.CANDIDATE)

        self.assertEqual(3, comparison.paired_count())
        self.assertEqual(0, comparison.baseline_only_passes())
        self.assertEqual(2, comparison.candidate_only_passes())
        self.assertEqual(SignTest.two_sided_p_value(0, 2), comparison.p_value())

    def test_summary_reports_rates_cost_and_unpaired(self) -> None:
        """The JSON summary carries both pass rates, the cost difference and the unpaired count."""
        summary = PairedComparison(self.BASELINE, self.CANDIDATE).to_dict()

        self.assertAlmostEqual(0.5, summary.get("baseline_pass_rate"))
        self.assertAlmostEqual(1.0, summary.get("candidate_pass_rate"))
        self.assertAlmostEqual(0.002, summary.get("mean_cost_difference_per_question"))
        self.assertEqual(1, summary.get("unpaired_attempts"))

    def test_unknown_cost_gives_unknown_difference(self) -> None:
        """When one side reported no cost, the difference is unknown rather than a guess."""
        uncosted = NetworkScorecard(
            "basic/new", [AttemptResult(fixture="a.hocon", attempt=0, passed=True, total_tokens=None, total_cost=None)]
        )

        summary = PairedComparison(self.BASELINE, uncosted).to_dict()

        self.assertIsNone(summary.get("mean_cost_difference_per_question"))
