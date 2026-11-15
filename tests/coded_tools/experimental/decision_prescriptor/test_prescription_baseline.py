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

from collections.abc import Callable
from unittest import TestCase

import numpy as np

from coded_tools.experimental.decision_prescriptor.decision_keys import DecisionKeys
from coded_tools.experimental.decision_prescriptor.evolve_prescriptors import EvolvePrescriptors
from coded_tools.experimental.decision_prescriptor.fit_surrogate import FitSurrogate
from coded_tools.experimental.decision_prescriptor.hypervolume import Hypervolume
from coded_tools.experimental.decision_prescriptor.load_decision_problem import LoadDecisionProblem
from coded_tools.experimental.decision_prescriptor.pareto_ranking import ParetoRanking
from coded_tools.experimental.decision_prescriptor.sample_data import SampleData
from coded_tools.experimental.decision_prescriptor.training_arrays import TrainingArrays


class TestPrescriptionBaseline(TestCase):
    """
    Does evolving a context-to-action policy beat simply choosing one fixed action?

    That is the claim the network rests on, so it is tested against the simplest
    baseline that could replace it: a dense grid of fixed actions, each applied to
    every engagement. The search runs on the bundled example with the tool's own
    defaults, wired through EvolvePrescriptors.search exactly as the tool runs it.

    A policy "wins" in two senses. Its front's hypervolume is larger, and it dominates
    most of the best fixed actions outright: for each of those, some evolved strategy is
    at least as good on every outcome and strictly better on one. The bar of a majority
    was set with the measured shares in view (61% on the surrogate, 58% in truth), not derived.
    """

    # Points per action axis in the fixed-action grid; 41 x 41 is 1681 surrogate calls,
    # about half the 3060 the default search makes.
    GRID_STEPS: int = 41

    # Monte Carlo samples for comparing two fronts; both are measured on the same set.
    SAMPLES: int = 50000

    @classmethod
    def setUpClass(cls):
        """Load the example, fit the surrogate and run the default search once for every test."""
        sly_data: dict = {}
        LoadDecisionProblem().invoke({}, sly_data)
        FitSurrogate().invoke({}, sly_data)
        spec = sly_data.get(DecisionKeys.SPEC)
        arrays = TrainingArrays.build(
            sly_data.get(DecisionKeys.DATASET),
            spec.get("context_fields"),
            spec.get("action_fields"),
            spec.get("outcome_fields"),
        )
        cls.surrogate = sly_data.get(DecisionKeys.SURROGATE)
        cls.context = arrays.get("context")
        cls.action = arrays.get("action")
        cls.signs = np.array([-1.0 if flag else 1.0 for flag in spec.get("maximize")])
        cls.network, cls.network_context, cls.result = EvolvePrescriptors.search(
            arrays, spec.get("maximize"), cls.surrogate
        )
        low = cls.action.min(axis=0)
        high = cls.action.max(axis=0)
        axes = [np.linspace(low[index], high[index], cls.GRID_STEPS) for index in range(low.shape[0])]
        cls.grid = np.array(np.meshgrid(*axes)).reshape(low.shape[0], -1).T

    def test_evolved_policies_beat_the_best_fixed_actions_on_the_surrogate(self):
        """Measured by the model the search optimized against."""
        evolved = self.result.get("front_objectives")
        fixed = self._fixed_action_objectives(self._predict)
        self._assert_beats(evolved, fixed)

    def test_the_advantage_holds_under_the_true_outcomes(self):
        """
        Measured by the example's noise-free ground truth, which the search never saw.

        This separates finding better decisions from exploiting the surrogate's errors.
        """
        evolved = np.array(
            [
                self._mean_objectives(SampleData.expected_outcomes, self.network.actions(genes, self.network_context))
                for genes in self.result.get("front_genes")
            ]
        )
        fixed = self._fixed_action_objectives(SampleData.expected_outcomes)
        self._assert_beats(evolved, fixed)

    def test_a_policy_is_not_just_its_mean_action(self):
        """
        Under an additive surrogate, every policy scored exactly like the fixed action at its
        mean, to within rounding. With interactions, applying the mean action instead must
        change the outcome for at least some evolved strategies.
        """
        largest_change = 0.0
        span = np.ptp(self.result.get("front_objectives"), axis=0)
        for genes, objectives in zip(self.result.get("front_genes"), self.result.get("front_objectives")):
            mean_action = self.network.actions(genes, self.network_context).mean(axis=0)
            as_fixed = self._mean_objectives(self._predict, np.tile(mean_action, (self.context.shape[0], 1)))
            largest_change = max(largest_change, float(np.max(np.abs(as_fixed - objectives) / span)))
        self.assertGreater(largest_change, 0.01)

    def _assert_beats(self, evolved: np.ndarray, fixed: np.ndarray) -> None:
        """
        Assert that the evolved front beats the front of the fixed actions.

        :param evolved: Minimization objectives of the evolved strategies.
        :param fixed: Minimization objectives of every fixed action in the grid.
        """
        fixed_front = fixed[ParetoRanking.non_dominated_mask(fixed)]
        best = np.minimum(evolved.min(axis=0), fixed_front.min(axis=0))
        worst = np.maximum(evolved.max(axis=0), fixed_front.max(axis=0))
        # A shared reference just past the worst of either front, in units of each objective's span.
        reference = worst + 0.1 * (worst - best)
        samples = np.random.default_rng(0).uniform(best, reference, size=(self.SAMPLES, best.shape[0]))
        box_volume = float(np.prod(reference - best))

        evolved_volume = Hypervolume.compute(evolved, reference, samples, box_volume)
        fixed_volume = Hypervolume.compute(fixed_front, reference, samples, box_volume)
        share_beaten = float(np.mean(ParetoRanking.beaten_by(fixed_front, evolved)))

        self.assertGreater(evolved_volume, fixed_volume)
        self.assertGreater(share_beaten, 0.5)

    def _fixed_action_objectives(self, predict: Callable[[np.ndarray, np.ndarray], np.ndarray]) -> np.ndarray:
        """
        Score every grid action applied to every engagement.

        :param predict: Maps (context, action) arrays to outcome rows.
        :return: Minimization objectives, one row per grid action.
        """
        rows: list[np.ndarray] = []
        for fixed_action in self.grid:
            rows.append(self._mean_objectives(predict, np.tile(fixed_action, (self.context.shape[0], 1))))
        return np.array(rows)

    def _mean_objectives(
        self, predict: Callable[[np.ndarray, np.ndarray], np.ndarray], actions: np.ndarray
    ) -> np.ndarray:
        """
        Average the outcomes of one action per engagement, oriented for minimization.

        :param predict: Maps (context, action) arrays to outcome rows.
        :param actions: One action row per engagement, shape (num_rows, action_dim).
        :return: Objective vector of shape (num_outcomes,).
        """
        return predict(self.context, actions).mean(axis=0) * self.signs

    def _predict(self, context: np.ndarray, actions: np.ndarray) -> np.ndarray:
        """
        Adapt the surrogate, which reads raw (context, action) rows side by side, to predict(context, actions).

        :param context: Context rows, shape (num_rows, context_dim).
        :param actions: Action rows, shape (num_rows, action_dim).
        :return: Predicted outcome rows.
        """
        return self.surrogate.predict(np.hstack([context, actions]))
