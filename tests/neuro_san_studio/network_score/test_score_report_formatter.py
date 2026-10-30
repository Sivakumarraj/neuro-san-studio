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

"""Tests for the `ns score` text report."""

from unittest import TestCase

from neuro_san_studio.network_score.attempt_result import AttemptResult
from neuro_san_studio.network_score.network_scorecard import NetworkScorecard
from neuro_san_studio.network_score.paired_comparison import PairedComparison
from neuro_san_studio.network_score.score_report_formatter import ScoreReportFormatter


class TestScoreReportFormatter(TestCase):
    """Verify the report shows the figures and marks unknown values."""

    SCORECARD = NetworkScorecard(
        "basic/net",
        [
            AttemptResult(fixture="a.hocon", attempt=0, passed=True, total_tokens=10, total_cost=0.00125),
            AttemptResult(fixture="a.hocon", attempt=1, passed=False, total_tokens=None, total_cost=None),
        ],
    )

    def test_scorecard_text_shows_rate_and_cost(self) -> None:
        """The pass rate, the costed-attempt count and the per-fixture row are shown."""
        text = ScoreReportFormatter.scorecard_text(self.SCORECARD)

        self.assertIn("50.0% (1 of 2)", text)
        self.assertIn("$0.00125", text)
        self.assertIn("1 of 2 attempts reported a cost", text)
        self.assertIn("a.hocon: 1/2 passed", text)

    def test_comparison_text_shows_the_sign_test(self) -> None:
        """The comparison shows the discordant counts and the p-value."""
        text = ScoreReportFormatter.comparison_text(PairedComparison(self.SCORECARD, self.SCORECARD))

        self.assertIn("p = 1.0000", text)
        self.assertIn("only the candidate passed: 0", text)

    def test_unknown_values_are_marked(self) -> None:
        """Missing values print as n/a instead of zero."""
        self.assertEqual("n/a", ScoreReportFormatter.dollars(None))
        self.assertEqual("n/a", ScoreReportFormatter.percent(None))
