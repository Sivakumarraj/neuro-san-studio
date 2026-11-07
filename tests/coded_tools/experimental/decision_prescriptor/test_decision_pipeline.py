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

        message = RenderParetoReport().invoke({"output_path": "report.html"}, sly_data)
        self.assertIn("Wrote the trade-off report", message)
        written = os.listdir(RenderParetoReport.REPORT_DIRECTORY)
        self.assertEqual(len(written), 1)
        self.assertTrue(written[0].startswith("report-") and written[0].endswith(".html"), written[0])
        with open(os.path.join(RenderParetoReport.REPORT_DIRECTORY, written[0]), encoding="utf-8") as handle:
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

    def test_oversized_search_is_rejected(self):
        """A search past the caps would hold the server for an unbounded time."""
        sly_data = {}
        LoadDecisionProblem().invoke({}, sly_data)
        FitSurrogate().invoke({}, sly_data)
        self.assertTrue(EvolvePrescriptors().invoke({"generations": 100000}, sly_data).startswith("Error:"))

    def _evolved_sly_data(self) -> dict:
        """
        Run the first three stages on the built-in example with a short search.

        :return: sly_data ready for the report stage.
        """
        sly_data = {}
        LoadDecisionProblem().invoke({}, sly_data)
        FitSurrogate().invoke({}, sly_data)
        EvolvePrescriptors().invoke({"generations": 2}, sly_data)
        return sly_data

    def test_report_name_is_confined_to_its_folder(self) -> None:
        """The name comes from an LLM, so its folders are dropped and nothing outside the report folder is written."""
        sly_data = self._evolved_sly_data()

        outside = os.path.join(os.path.dirname(os.getcwd()), "escaped.html")
        template = os.path.join("apps", "ui", "index.html")
        self.assertIn("Wrote the trade-off report", RenderParetoReport().invoke({"output_path": outside}, sly_data))
        self.assertIn("Wrote the trade-off report", RenderParetoReport().invoke({"output_path": template}, sly_data))
        self.assertTrue(RenderParetoReport().invoke({"output_path": "report.txt"}, sly_data).startswith("Error:"))
        self.assertFalse(os.path.exists(outside))
        self.assertFalse(os.path.exists(template))
        self.assertEqual(sorted(os.listdir(".")), [RenderParetoReport.REPORT_DIRECTORY])

    def test_each_report_is_a_new_file(self) -> None:
        """Two renders with the same name write two files, so two sessions never share or overwrite one."""
        sly_data = self._evolved_sly_data()
        RenderParetoReport().invoke({}, sly_data)
        RenderParetoReport().invoke({}, sly_data)
        self.assertEqual(len(os.listdir(RenderParetoReport.REPORT_DIRECTORY)), 2)

    def test_non_finite_alpha_is_rejected(self) -> None:
        """A NaN alpha would fit a NaN model, and the fit would still be called strong."""
        sly_data = {}
        LoadDecisionProblem().invoke({}, sly_data)
        for alpha in ("nan", "inf"):
            with self.subTest(alpha=alpha):
                self.assertTrue(FitSurrogate().invoke({"alpha": alpha}, sly_data).startswith("Error:"))

    def test_non_finite_values_in_rows_are_rejected(self) -> None:
        """A nan or inf value would poison the fit, so the load names the row instead."""
        rows = [{"a": float(i), "b": 1.0, "c": 2.0} for i in range(4)]
        rows[2]["c"] = "nan"
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
        self.assertTrue(message.startswith("Error:"), message)
        self.assertIn("row 2", message)

    def test_loading_a_new_problem_drops_the_old_model_and_front(self) -> None:
        """A model or front from the earlier problem must not be used for the new one."""
        sly_data = self._evolved_sly_data()
        rows = [{"a": float(i), "b": float(i % 3), "c": float(2 * i)} for i in range(10)]
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
        self.assertTrue(EvolvePrescriptors().invoke({}, sly_data).startswith("Error:"))
        self.assertTrue(RenderParetoReport().invoke({}, sly_data).startswith("Error:"))

    def test_refitting_drops_the_old_front(self) -> None:
        """A front evolved against the previous fit must be evolved again before it is drawn."""
        sly_data = self._evolved_sly_data()
        FitSurrogate().invoke({"alpha": 0.1}, sly_data)
        self.assertTrue(RenderParetoReport().invoke({}, sly_data).startswith("Error:"))

    def test_negative_seed_is_rejected(self) -> None:
        """A negative seed would raise inside numpy instead of coming back as an error message."""
        sly_data = {}
        LoadDecisionProblem().invoke({}, sly_data)
        FitSurrogate().invoke({}, sly_data)
        self.assertTrue(EvolvePrescriptors().invoke({"seed": -1}, sly_data).startswith("Error:"))

    def test_field_names_without_rows_are_rejected(self) -> None:
        """Named fields with no rows mean the user's data went missing, so the example must not stand in."""
        message = LoadDecisionProblem().invoke({"rows": [], "outcome_fields": ["revenue"]}, {})
        self.assertTrue(message.startswith("Error:"), message)

    def test_maximize_must_hold_booleans(self) -> None:
        """The string "false" is truthy and would flip the objective, so it is refused."""
        message = LoadDecisionProblem().invoke(
            {
                "rows": [{"a": 1.0, "b": 2.0, "c": 3.0}],
                "context_fields": ["a"],
                "action_fields": ["b"],
                "outcome_fields": ["c"],
                "maximize": ["false"],
            },
            {},
        )
        self.assertTrue(message.startswith("Error:"), message)
