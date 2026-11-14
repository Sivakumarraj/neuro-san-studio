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

import json
import os
import tempfile
from unittest import TestCase

import numpy as np

from coded_tools.experimental.decision_prescriptor.decision_keys import DecisionKeys
from coded_tools.experimental.decision_prescriptor.evolve_prescriptors import EvolvePrescriptors
from coded_tools.experimental.decision_prescriptor.fit_surrogate import FitSurrogate
from coded_tools.experimental.decision_prescriptor.load_decision_problem import LoadDecisionProblem
from coded_tools.experimental.decision_prescriptor.render_pareto_report import RenderParetoReport


class TestDecisionPipeline(TestCase):
    """
    End-to-end tests of the four CodedTools, exercised through sly_data as the
    agent network in registries/experimental/decision_prescriptor.hocon drives them.
    """

    def setUp(self):
        """Run each test from a scratch working directory, where the report tool may write."""
        self.original_directory = os.getcwd()
        self.scratch = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        os.chdir(self.scratch.name)

    def tearDown(self):
        """Return to the original working directory and remove the scratch one."""
        os.chdir(self.original_directory)
        self.scratch.cleanup()

    def test_full_pipeline_writes_a_report(self):
        """Load, fit, evolve and render, in the order the front man runs them."""
        sly_data = {}

        loaded = LoadDecisionProblem().invoke({}, sly_data)
        self.assertIn("Loaded 400 records", loaded)

        fitted = FitSurrogate().invoke({}, sly_data)
        self.assertIn("R²", fitted)

        evolved = json.loads(EvolvePrescriptors().invoke({"generations": 8}, sly_data))
        self.assertGreater(evolved.get("strategies_found"), 0)
        self.assertIn("margin_pct", evolved.get("achievable_range"))

        message = RenderParetoReport().invoke({"output_path": "reports/report.html"}, sly_data)
        self.assertIn("Wrote the trade-off report", message)
        with open(os.path.join("reports", "report.html"), encoding="utf-8") as handle:
            self.assertIn("<svg", handle.read())

    def test_stages_refuse_to_run_out_of_order(self):
        """
        Each stage depends on the last, so a skipped stage must be reported
        rather than producing an empty or misleading result.
        """
        self.assertTrue(FitSurrogate().invoke({}, {}).startswith("Error:"))
        self.assertTrue(EvolvePrescriptors().invoke({}, {}).startswith("Error:"))
        self.assertTrue(RenderParetoReport().invoke({}, {}).startswith("Error:"))

        sly_data = {}
        LoadDecisionProblem().invoke({}, sly_data)
        self.assertTrue(EvolvePrescriptors().invoke({}, sly_data).startswith("Error:"))

    def test_user_supplied_rows_are_loaded(self):
        """Rows passed by the user replace the built-in example."""
        rows = [{"a": float(i), "b": float(i % 3), "c": float(2 * i)} for i in range(10)]
        message = LoadDecisionProblem().invoke(
            {
                "rows": rows,
                "context_fields": ["a"],
                "action_fields": ["b"],
                "outcome_fields": ["c"],
                "maximize": [True],
            },
            {},
        )
        self.assertIn("Loaded 10 records", message)
        self.assertIn("c (maximize)", message)

    def test_mismatched_maximize_length_is_rejected(self):
        """One direction per outcome, or the objectives get silently mis-signed."""
        message = LoadDecisionProblem().invoke(
            {
                "rows": [{"a": 1.0, "b": 2.0, "c": 3.0}],
                "context_fields": ["a"],
                "action_fields": ["b"],
                "outcome_fields": ["c"],
                "maximize": [True, False],
            },
            {},
        )
        self.assertTrue(message.startswith("Error:"))

    def test_bad_alpha_is_rejected(self):
        """A non-numeric alpha should be named, not raise out of the tool."""
        sly_data = {}
        LoadDecisionProblem().invoke({}, sly_data)
        self.assertTrue(FitSurrogate().invoke({"alpha": "wide"}, sly_data).startswith("Error:"))

    def test_memorized_noise_is_reported_as_a_weak_fit(self):
        """
        Sixty records of pure noise with eight inputs: the second-order model has 44 terms,
        enough to look strong in-sample. The held-out fit must expose it.
        """
        rng = np.random.default_rng(5)
        rows = []
        for _ in range(60):
            values = rng.normal(size=10)
            rows.append({f"x{index}": float(value) for index, value in enumerate(values)})
        sly_data = {}
        LoadDecisionProblem().invoke(
            {
                "rows": rows,
                "context_fields": [f"x{index}" for index in range(6)],
                "action_fields": ["x6", "x7"],
                "outcome_fields": ["x8", "x9"],
                "maximize": [True, False],
            },
            sly_data,
        )
        message = FitSurrogate().invoke({}, sly_data)
        self.assertIn("Held-out R²", message)
        self.assertIn("Fit is weak", message)

    def test_an_unmeasurable_fit_is_refused_and_drops_the_earlier_model(self):
        """
        Five records against six model columns with no penalty: the model fits every record
        exactly, so its held-out error cannot be measured. The tool must say so, and must not
        leave a model from an earlier fit behind for the search to use.
        """
        sly_data = {}
        LoadDecisionProblem().invoke({}, sly_data)
        FitSurrogate().invoke({}, sly_data)
        self.assertIn(DecisionKeys.SURROGATE, sly_data)

        rows = [{"a": float(i), "b": float(i * i % 4), "c": float(3 * i % 5)} for i in range(5)]
        LoadDecisionProblem().invoke(
            {
                "rows": rows,
                "context_fields": ["a"],
                "action_fields": ["b"],
                "outcome_fields": ["c"],
                "maximize": [True],
            },
            sly_data,
        )
        self.assertTrue(FitSurrogate().invoke({"alpha": 0}, sly_data).startswith("Error:"))
        self.assertNotIn(DecisionKeys.SURROGATE, sly_data)

    def test_oversized_search_is_rejected(self):
        """A search past the caps would hold the server for an unbounded time."""
        sly_data = {}
        LoadDecisionProblem().invoke({}, sly_data)
        FitSurrogate().invoke({}, sly_data)
        self.assertTrue(EvolvePrescriptors().invoke({"generations": 100000}, sly_data).startswith("Error:"))

    def test_report_outside_the_working_directory_is_refused(self):
        """The path comes from an LLM, so it must not be able to write anywhere on disk."""
        sly_data = {}
        LoadDecisionProblem().invoke({}, sly_data)
        FitSurrogate().invoke({}, sly_data)
        EvolvePrescriptors().invoke({"generations": 2}, sly_data)

        outside = os.path.join(os.path.dirname(os.getcwd()), "escaped.html")
        self.assertTrue(RenderParetoReport().invoke({"output_path": outside}, sly_data).startswith("Error:"))
        self.assertTrue(RenderParetoReport().invoke({"output_path": "report.txt"}, sly_data).startswith("Error:"))
        self.assertFalse(os.path.exists(outside))
