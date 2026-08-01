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
"""
Unit tests for the surrogate, the prescriptor network and the rendered report.

The surrogate is checked against the closed-form ridge solution written out
independently, so the test would catch a sign slip or a missing intercept rather
than simply re-running the implementation and agreeing with itself.
"""

import json
import os
import tempfile
from unittest import TestCase

import numpy as np

from coded_tools.experimental.decision_prescriptor import decision_tools
from coded_tools.experimental.decision_prescriptor import sample_data
from coded_tools.experimental.decision_prescriptor.charts import render_report
from coded_tools.experimental.decision_prescriptor.prescriptor import PrescriptorNetwork
from coded_tools.experimental.decision_prescriptor.prescriptor import make_evaluator
from coded_tools.experimental.decision_prescriptor.prescriptor import standardize
from coded_tools.experimental.decision_prescriptor.surrogate import RidgeSurrogate
from coded_tools.experimental.decision_prescriptor.surrogate import build_training_arrays


class TestRidgeSurrogate(TestCase):
    """
    Tests for the closed-form predictor.
    """

    def test_matches_an_independently_written_closed_form(self):
        """
        Compare predictions against the ridge solution computed from scratch.

        The reference below repeats the standardization, the unpenalized bias
        column and the solve explicitly, so agreement is evidence about the
        formula rather than a tautology.
        """
        rng = np.random.default_rng(0)
        features = rng.normal(size=(50, 3))
        targets = rng.normal(size=(50, 2))
        alpha = 0.7

        surrogate = RidgeSurrogate(alpha=alpha).fit(features, targets)

        mean = features.mean(axis=0)
        scale = np.where(features.std(axis=0) < 1e-12, 1.0, features.std(axis=0))
        design = np.hstack([(features - mean) / scale, np.ones((features.shape[0], 1))])
        penalty = alpha * np.eye(design.shape[1])
        penalty[-1, -1] = 0.0
        expected = design @ np.linalg.solve(design.T @ design + penalty, design.T @ targets)

        np.testing.assert_allclose(surrogate.predict(features), expected, rtol=1e-9, atol=1e-9)

    def test_recovers_a_clean_linear_relationship(self):
        """With no noise and a linear truth, the fit should be near perfect."""
        rng = np.random.default_rng(1)
        features = rng.uniform(0.0, 1.0, size=(200, 2))
        targets = np.column_stack([3.0 * features[:, 0] - 2.0 * features[:, 1] + 5.0])

        surrogate = RidgeSurrogate(alpha=1e-6).fit(features, targets)
        self.assertGreater(float(surrogate.r_squared(features, targets)[0]), 0.999)

    def test_constant_target_scores_zero_rather_than_dividing_by_zero(self):
        """A target with no variance has no variance to explain."""
        features = np.random.default_rng(2).normal(size=(20, 2))
        targets = np.full((20, 1), 4.0)
        surrogate = RidgeSurrogate(alpha=1.0).fit(features, targets)
        self.assertEqual(float(surrogate.r_squared(features, targets)[0]), 0.0)

    def test_predict_before_fit_is_refused(self):
        """Predicting from an unfitted model would silently return nonsense."""
        with self.assertRaises(RuntimeError):
            RidgeSurrogate().predict(np.zeros((2, 2)))

    def test_negative_alpha_is_refused(self):
        """A negative penalty is not regularization and must not be accepted."""
        with self.assertRaises(ValueError):
            RidgeSurrogate(alpha=-1.0)

    def test_row_count_mismatch_is_reported(self):
        """Mismatched features and targets are a caller error worth naming."""
        with self.assertRaises(ValueError):
            RidgeSurrogate().fit(np.zeros((5, 2)), np.zeros((4, 1)))


class TestBuildTrainingArrays(TestCase):
    """
    Tests for turning records into arrays.
    """

    def test_names_the_missing_field_and_the_row(self):
        """A vague failure here would be hard to debug from an agent transcript."""
        rows = [{"a": 1.0, "b": 2.0}, {"a": 3.0}]
        with self.assertRaises(ValueError) as caught:
            build_training_arrays(rows, ["a"], ["b"], [])
        message = str(caught.exception)
        self.assertIn("row 1", message)
        self.assertIn("b", message)

    def test_empty_input_is_refused(self):
        """There is nothing to fit on, so say so rather than failing later."""
        with self.assertRaises(ValueError):
            build_training_arrays([], ["a"], ["b"], ["c"])


class TestPrescriptorNetwork(TestCase):
    """
    Tests for the evolved policy network.
    """

    def setUp(self):
        """Build a small network shared by the tests below."""
        self.network = PrescriptorNetwork(
            context_dim=2, action_dim=3, action_lower=np.zeros(3), action_upper=np.array([1.0, 5.0, 0.5])
        )

    def test_weight_count_matches_the_layer_shapes(self):
        """2*4 + 4 + 4*3 + 3 = 27."""
        self.assertEqual(self.network.num_weights, 27)

    def test_actions_always_land_inside_the_bounds(self):
        """
        Feasibility must hold by construction, including for extreme weights.

        If it did not, the search would spend effort on candidates that could
        never be carried out.
        """
        rng = np.random.default_rng(0)
        context = rng.normal(size=(40, 2)) * 100.0
        for scale in (1.0, 50.0):
            actions = self.network.actions(rng.normal(size=27) * scale, context)
            self.assertTrue(np.all(actions >= self.network.action_lower - 1e-12))
            self.assertTrue(np.all(actions <= self.network.action_upper + 1e-12))

    def test_wrong_weight_length_is_refused(self):
        """A silent reshape here would scramble the policy."""
        with self.assertRaises(ValueError):
            self.network.actions(np.zeros(5), np.zeros((3, 2)))

    def test_inverted_bounds_are_refused(self):
        """An upper bound below its lower bound describes no feasible action."""
        with self.assertRaises(ValueError):
            PrescriptorNetwork(1, 1, np.array([1.0]), np.array([0.0]))

    def test_standardize_produces_zero_mean_unit_scale(self):
        """The network's inputs must not be dominated by a feature's units."""
        values = np.array([[1000.0, 0.1], [2000.0, 0.2], [3000.0, 0.3]])
        standardized = standardize(values)(values)
        np.testing.assert_allclose(standardized.mean(axis=0), [0.0, 0.0], atol=1e-12)
        np.testing.assert_allclose(standardized.std(axis=0), [1.0, 1.0], atol=1e-12)


class TestEvaluator(TestCase):
    """
    Tests for the bridge between a policy and the objectives the search minimizes.
    """

    def test_maximized_outcomes_are_negated_for_minimization(self):
        """
        The search minimizes, so a maximized outcome must arrive negated.

        Getting this backwards would produce a front that is confidently the worst
        available set of options, which is the kind of error a chart makes look
        authoritative.
        """
        network = PrescriptorNetwork(1, 1, np.zeros(1), np.ones(1))
        context = np.zeros((4, 1))
        weights = np.zeros((1, network.num_weights))

        def predict(features: np.ndarray) -> np.ndarray:
            return np.column_stack([np.full(features.shape[0], 3.0), np.full(features.shape[0], 7.0)])

        maximized = make_evaluator(network, context, context, predict, [True, False])(weights)
        np.testing.assert_allclose(maximized, [[-3.0, 7.0]])

    def test_mismatched_context_views_are_refused(self):
        """Mixing the standardized and raw views would corrupt every prediction."""
        network = PrescriptorNetwork(1, 1, np.zeros(1), np.ones(1))
        with self.assertRaises(ValueError):
            make_evaluator(network, np.zeros((4, 1)), np.zeros((5, 1)), lambda x: x, [True])


class TestSampleData(TestCase):
    """
    Tests for the bundled example.
    """

    def test_generates_every_declared_field(self):
        """The spec and the rows have to agree or nothing downstream will run."""
        rows = sample_data.generate(num_rows=25)
        spec = sample_data.specification()
        self.assertEqual(len(rows), 25)
        for name in spec["context_fields"] + spec["action_fields"] + spec["outcome_fields"]:
            self.assertIn(name, rows[0])
        self.assertEqual(len(spec["maximize"]), len(spec["outcome_fields"]))

    def test_contains_the_intended_conflict(self):
        """
        Senior staffing must genuinely pull margin and delivery risk apart.

        Without a real conflict the example would produce a degenerate front and
        quietly stop demonstrating anything.
        """
        rows = sample_data.generate(num_rows=400)
        staffing = np.array([row["senior_staff_ratio"] for row in rows])
        margin = np.array([row["margin_pct"] for row in rows])
        risk = np.array([row["delivery_risk"] for row in rows])

        self.assertLess(float(np.corrcoef(staffing, margin)[0, 1]), -0.5)
        self.assertLess(float(np.corrcoef(staffing, risk)[0, 1]), -0.5)

    def test_is_reproducible(self):
        """The same seed must give the same example."""
        self.assertEqual(sample_data.generate(10, seed=3), sample_data.generate(10, seed=3))


class TestRenderReport(TestCase):
    """
    Tests for the HTML report.
    """

    def setUp(self):
        """Build a small front to render."""
        self.front = np.array([[10.0, 0.2, 12.0], [20.0, 0.4, 16.0], [30.0, 0.6, 20.0]])
        self.actions = np.array([[0.9, 0.1], [0.5, 0.5], [0.1, 0.9]])
        self.labels = ["margin_pct", "delivery_risk", "time_to_value_weeks"]
        self.action_labels = ["senior_staff_ratio", "automation_investment"]

    def render(self) -> str:
        """
        :return: A rendered report for the fixture front.
        """
        return render_report(
            title="Test front",
            front=self.front,
            dominated=np.array([[5.0, 0.9, 30.0]]),
            actions=self.actions,
            objective_labels=self.labels,
            action_labels=self.action_labels,
            hypervolume_history=[1.0, 2.0, 3.0],
            summary={"Strategies": "3"},
            balanced_index=1,
        )

    def test_report_is_self_contained(self):
        """
        No external stylesheet, script or image may be referenced.

        A report that silently needs the network would render broken for anyone
        reading it from disk, which is the main way these files get read.
        """
        document = self.render()
        for marker in ("http://", "https://", "<script", "@import", "src="):
            self.assertNotIn(marker, document, f"report should not contain {marker!r}")

    def test_every_strategy_reaches_the_table(self):
        """The table is the accessibility path, so it must be complete."""
        document = self.render()
        self.assertEqual(document.count("<tr><th scope='row'>"), self.front.shape[0])

    def test_both_themes_are_defined(self):
        """Dark mode is a selected set of steps, and must survive a theme toggle."""
        document = self.render()
        self.assertIn("prefers-color-scheme: dark", document)
        self.assertIn("[data-theme='dark']", document)

    def test_labels_are_escaped(self):
        """A field name is user-supplied and must not be able to inject markup."""
        document = render_report(
            title="<script>alert(1)</script>",
            front=self.front,
            dominated=np.empty((0, 3)),
            actions=self.actions,
            objective_labels=["<b>x</b>", "y", "z"],
            action_labels=self.action_labels,
            hypervolume_history=[1.0],
            summary={},
        )
        self.assertNotIn("<script>alert(1)</script>", document)
        self.assertNotIn("<b>x</b>", document)

    def test_two_objective_reports_render(self):
        """The two-objective path uses a single connected chart and must not break."""
        document = render_report(
            title="Two",
            front=np.array([[1.0, 4.0], [2.0, 3.0]]),
            dominated=np.empty((0, 2)),
            actions=np.array([[0.1], [0.2]]),
            objective_labels=["a", "b"],
            action_labels=["act"],
            hypervolume_history=[1.0, 1.5],
            summary={"n": "2"},
            balanced_index=0,
        )
        self.assertIn("<svg", document)
        self.assertIn("front-line", document)


class TestCodedTools(TestCase):
    """
    End-to-end tests of the four CodedTools, exercised through sly_data.
    """

    def test_full_pipeline_writes_a_report(self):
        """Load, fit, evolve and render, exactly as the agent network drives it."""
        sly_data = {}

        loaded = decision_tools.LoadDecisionProblem().invoke({}, sly_data)
        self.assertIn("Loaded 400 records", loaded)

        fitted = decision_tools.FitSurrogate().invoke({}, sly_data)
        self.assertIn("R²", fitted)

        evolved = json.loads(decision_tools.EvolvePrescriptors().invoke({"generations": 8}, sly_data))
        self.assertGreater(evolved["strategies_found"], 0)
        self.assertIn("margin_pct", evolved["achievable_range"])

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "report.html")
            message = decision_tools.RenderParetoReport().invoke({"output_path": path}, sly_data)
            self.assertIn("Wrote the trade-off report", message)
            self.assertTrue(os.path.exists(path))
            with open(path, encoding="utf-8") as handle:
                self.assertIn("<svg", handle.read())

    def test_stages_refuse_to_run_out_of_order(self):
        """
        Each stage depends on the last, so a skipped stage must be reported
        rather than producing an empty or misleading result.
        """
        self.assertTrue(decision_tools.FitSurrogate().invoke({}, {}).startswith("Error:"))
        self.assertTrue(decision_tools.EvolvePrescriptors().invoke({}, {}).startswith("Error:"))
        self.assertTrue(decision_tools.RenderParetoReport().invoke({}, {}).startswith("Error:"))

        sly_data = {}
        decision_tools.LoadDecisionProblem().invoke({}, sly_data)
        self.assertTrue(decision_tools.EvolvePrescriptors().invoke({}, sly_data).startswith("Error:"))

    def test_mismatched_maximize_length_is_rejected(self):
        """One direction per outcome, or the objectives get silently mis-signed."""
        message = decision_tools.LoadDecisionProblem().invoke(
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
        decision_tools.LoadDecisionProblem().invoke({}, sly_data)
        self.assertTrue(decision_tools.FitSurrogate().invoke({"alpha": "wide"}, sly_data).startswith("Error:"))
