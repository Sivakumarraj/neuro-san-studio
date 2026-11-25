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

from coded_tools.experimental.decision_prescriptor.quadratic_surrogate import QuadraticSurrogate
from coded_tools.experimental.decision_prescriptor.ridge_surrogate import RidgeSurrogate


class TestQuadraticSurrogate(TestCase):
    """
    Tests for the second-order predictor the search runs against.
    """

    def test_recovers_an_interaction_and_a_square_exactly(self):
        """With no noise and a quadratic truth, predictions on unseen rows should match the truth."""
        rng = np.random.default_rng(0)
        features = rng.uniform(-1.0, 1.0, size=(200, 2))
        fresh = rng.uniform(-1.0, 1.0, size=(50, 2))

        surrogate = QuadraticSurrogate(alpha=1e-9).fit(features, self._quadratic_truth(features))

        np.testing.assert_allclose(surrogate.predict(fresh), self._quadratic_truth(fresh), atol=1e-6)
        self.assertGreater(
            float(surrogate.leave_one_out_r_squared(features, self._quadratic_truth(features))[0]), 0.999999
        )

    def test_the_effect_of_an_action_depends_on_the_context(self):
        """
        This is the property that makes a context-to-action policy worth evolving.

        The truth is outcome = context * action, so raising the action helps in one context
        and hurts in the other. The quadratic model sees that; an additive model gives the
        action one effect everywhere, which is why every policy scored like its mean action.
        """
        rng = np.random.default_rng(1)
        features = rng.uniform(-1.0, 1.0, size=(300, 2))
        targets = (features[:, 0] * features[:, 1])[:, None]
        quadratic = QuadraticSurrogate(alpha=1e-9).fit(features, targets)
        additive = RidgeSurrogate(alpha=1e-9).fit(features, targets)

        for context, expected_effect in ((1.0, 1.0), (-1.0, -1.0)):
            low_and_high = np.array([[context, 0.0], [context, 1.0]])
            effect = float(np.diff(quadratic.predict(low_and_high)[:, 0])[0])
            self.assertAlmostEqual(effect, expected_effect, places=5)

        additive_effects = [
            float(np.diff(additive.predict(np.array([[context, 0.0], [context, 1.0]]))[:, 0])[0])
            for context in (1.0, -1.0)
        ]
        self.assertAlmostEqual(additive_effects[0], additive_effects[1], places=9)

    def test_predict_before_fit_is_refused(self):
        """Predicting from an unfitted model would silently return nonsense."""
        with self.assertRaises(RuntimeError):
            QuadraticSurrogate().predict(np.zeros((2, 2)))

    def test_negative_alpha_is_refused(self):
        """A negative penalty is not regularization and must not be accepted."""
        with self.assertRaises(ValueError):
            QuadraticSurrogate(alpha=-1.0)

    def test_zero_rows_are_refused(self):
        """There is nothing to standardize or fit with no rows."""
        with self.assertRaises(ValueError):
            QuadraticSurrogate().fit(np.zeros((0, 2)), np.zeros((0, 1)))

    @staticmethod
    def _quadratic_truth(features: np.ndarray) -> np.ndarray:
        """
        A noise-free target with a linear part, an interaction and a square.

        :param features: Rows of (x0, x1), shape (num_rows, 2).
        :return: Targets of shape (num_rows, 1).
        """
        first: np.ndarray = features[:, 0]
        second: np.ndarray = features[:, 1]
        return (1.0 + 2.0 * first - 3.0 * second + 4.0 * first * second - 2.0 * second**2)[:, None]
