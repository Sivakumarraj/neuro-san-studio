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

"""Plain-text report for `ns score`."""

from neuro_san_studio.network_score.network_scorecard import NetworkScorecard
from neuro_san_studio.network_score.paired_comparison import PairedComparison


class ScoreReportFormatter:
    """Format scorecards and an optional comparison as a short terminal report."""

    @staticmethod
    def scorecard_text(scorecard: NetworkScorecard) -> str:
        """
        Format one network's scorecard.

        :param scorecard: The scorecard to format.
        :return: The report lines joined by newlines.
        """
        lines: list[str] = [
            f"Network: {scorecard.network()}",
            f"  Pass rate over all attempts: {ScoreReportFormatter.percent(scorecard.pass_rate())} "
            f"({scorecard.passed_count()} of {scorecard.attempt_count()})",
            f"  Mean cost per question: {ScoreReportFormatter.dollars(scorecard.mean_cost_per_question())} "
            f"({len(scorecard.costed_attempts())} of {scorecard.attempt_count()} attempts reported a cost)",
            f"  Cost per correct answer: {ScoreReportFormatter.dollars(scorecard.cost_per_correct_answer())}",
        ]
        for row in scorecard.fixture_rows():
            lines.append(
                f"    {row.get('fixture')}: {row.get('passed')}/{row.get('attempts')} passed, "
                f"{ScoreReportFormatter.dollars(row.get('mean_cost_per_question'))} per question"
            )
        return "\n".join(lines)

    @staticmethod
    def comparison_text(comparison: PairedComparison) -> str:
        """
        Format a paired comparison.

        :param comparison: The comparison to format.
        :return: The report lines joined by newlines.
        """
        summary = comparison.to_dict()
        return "\n".join(
            [
                f"Compare: {summary.get('candidate')} against {summary.get('baseline')}",
                f"  Paired attempts: {comparison.paired_count()} ({summary.get('unpaired_attempts')} unpaired)",
                f"  Only the baseline passed: {comparison.baseline_only_passes()}; "
                f"only the candidate passed: {comparison.candidate_only_passes()}",
                f"  Sign test, two-sided: p = {comparison.p_value():.4f}",
                "  Mean cost difference per question (candidate minus baseline): "
                f"{ScoreReportFormatter.dollars(summary.get('mean_cost_difference_per_question'))}",
            ]
        )

    @staticmethod
    def percent(value: float | None) -> str:
        """
        Format a share as a percentage.

        :param value: A share between 0 and 1, or `None`.
        :return: The percentage text, or "n/a".
        """
        if value is None:
            return "n/a"
        return f"{value * 100:.1f}%"

    @staticmethod
    def dollars(value: float | None) -> str:
        """
        Format a US dollar amount with enough places for per-question costs.

        :param value: The amount, or `None`.
        :return: The dollar text, or "n/a".
        """
        if value is None:
            return "n/a"
        return f"${value:.5f}"
