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

from coded_tools.experimental.decision_prescriptor.sample_data import SampleData


class TestSampleData(TestCase):
    """
    Tests for the bundled example.
    """

    def test_generates_every_declared_field(self):
        """The spec and the rows have to agree or nothing downstream will run."""
        rows = SampleData.generate(num_rows=25)
        spec = SampleData.specification()
        self.assertEqual(len(rows), 25)
        for name in spec.get("context_fields") + spec.get("action_fields") + spec.get("outcome_fields"):
            self.assertIn(name, rows[0])
        self.assertEqual(len(spec.get("maximize")), len(spec.get("outcome_fields")))

    def test_contains_the_intended_conflict(self):
        """
        Senior staffing must genuinely pull margin and delivery risk apart.

        Without a real conflict the example would produce a degenerate front and
        quietly stop demonstrating anything.
        """
        rows = SampleData.generate(num_rows=400)
        staffing = np.array([row.get("senior_staff_ratio") for row in rows])
        margin = np.array([row.get("margin_pct") for row in rows])
        risk = np.array([row.get("delivery_risk") for row in rows])

        self.assertLess(float(np.corrcoef(staffing, margin)[0, 1]), -0.5)
        self.assertLess(float(np.corrcoef(staffing, risk)[0, 1]), -0.5)

    def test_targeting_senior_staff_at_urgent_work_beats_spreading_them(self):
        """
        With the same average senior ratio, putting senior staff on the urgent engagements
        keeps margin and time to value and cuts delivery risk.

        That is the interaction that gives a context-aware policy something to find; without
        it every policy would score the same as one fixed action.
        """
        urgency = np.linspace(0.0, 1.0, 101)
        context = np.column_stack([np.full(101, 5.0), urgency])
        targeted_ratio = np.where(urgency > 0.5, 0.9, 0.1)
        spread_ratio = np.full(101, targeted_ratio.mean())
        automation = np.full(101, 0.5)

        targeted = SampleData.expected_outcomes(context, np.column_stack([targeted_ratio, automation])).mean(axis=0)
        spread = SampleData.expected_outcomes(context, np.column_stack([spread_ratio, automation])).mean(axis=0)

        self.assertAlmostEqual(float(targeted[0]), float(spread[0]), places=9)
        self.assertAlmostEqual(float(targeted[2]), float(spread[2]), places=9)
        self.assertLess(float(targeted[1]), float(spread[1]) - 0.05)

    def test_automation_pays_on_large_accounts_and_costs_on_small_ones(self):
        """The second interaction: automating a small account loses margin, automating a large one gains it."""
        context = np.array([[0.5, 0.5], [10.0, 0.5]])
        senior = np.full(2, 0.5)
        without = SampleData.expected_outcomes(context, np.column_stack([senior, np.zeros(2)]))
        with_automation = SampleData.expected_outcomes(context, np.column_stack([senior, np.ones(2)]))

        self.assertLess(float(with_automation[0, 0]), float(without[0, 0]))
        self.assertGreater(float(with_automation[1, 0]), float(without[1, 0]))

    def test_is_reproducible(self):
        """The same seed must give the same example."""
        self.assertEqual(SampleData.generate(10, seed=3), SampleData.generate(10, seed=3))
