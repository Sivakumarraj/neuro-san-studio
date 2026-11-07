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

from unittest import TestCase

import numpy as np

from coded_tools.experimental.decision_prescriptor.svg_charts import SvgCharts


class TestSvgCharts(TestCase):
    """
    Tests for the axis and number formatting the charts rely on.
    """

    def test_ticks_land_on_round_numbers_covering_the_range(self):
        """Steps snap to 1, 2 or 5 times a power of ten."""
        self.assertEqual(SvgCharts.nice_ticks(0.0, 10.0), [0.0, 2.0, 4.0, 6.0, 8.0, 10.0])

    def test_degenerate_range_still_yields_two_ticks(self):
        """A flat axis must still be drawable."""
        self.assertEqual(SvgCharts.nice_ticks(3.0, 3.0), [3.0, 4.0])

    def test_numbers_are_formatted_compactly(self):
        """Large values get a suffix and tiny ones scientific notation."""
        self.assertEqual(SvgCharts.format_number(0), "0")
        self.assertEqual(SvgCharts.format_number(2_500_000), "2.50M")
        self.assertEqual(SvgCharts.format_number(1_500), "1.5k")
        self.assertEqual(SvgCharts.format_number(0.25), "0.25")
        self.assertEqual(SvgCharts.format_number(0.001), "1.00e-03")

    def test_empty_convergence_history_renders_an_empty_chart(self):
        """A run with no generations must not break the report."""
        self.assertTrue(SvgCharts.convergence([]).startswith("<svg"))

    def test_scatter_tooltips_number_strategies_by_row(self) -> None:
        """
        Points are drawn in x order, but each tooltip names the strategy by its row,
        the number the table and the report text use.
        """
        front = np.array([[3.0, 1.0], [1.0, 3.0], [2.0, 2.0]])
        svg = SvgCharts.pareto_scatter(front, np.empty((0, 2)), 0, 1, ["x", "y"])
        self.assertIn("strategy 1 — x 3", svg)
        self.assertIn("strategy 2 — x 1", svg)
        self.assertIn("strategy 3 — x 2", svg)
