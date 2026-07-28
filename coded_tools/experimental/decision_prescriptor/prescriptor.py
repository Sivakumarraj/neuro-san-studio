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
The prescriptor: the "prescription" half of Evolutionary Surrogate-assisted
Prescription.

A prescriptor is a small neural network mapping context to action. Its weights
are never trained by gradient descent, because there are no labels to descend
against: nobody knows the optimal action for a given context, which is the reason
the problem exists at all. Instead the whole weight vector is evolved, and a
candidate is judged by the outcomes the surrogate predicts when its actions are
applied across the dataset.

Evolving a policy rather than a fixed action matters. The result is a rule that
responds to circumstances, so a new situation gets its own action rather than a
lookup of whatever suited the average case.
"""

from typing import Callable
from typing import List

import numpy as np


class PrescriptorNetwork:
    """
    A one-hidden-layer network mapping context to bounded actions.

    The network is intentionally tiny. Evolution searches the weight space
    directly, so every added weight enlarges the search space, and a small
    network also stays interpretable enough to inspect after the fact.
    """

    # The architecture and the action bounds are all genuinely independent inputs.
    # pylint: disable=too-many-positional-arguments
    def __init__(
        self,
        context_dim: int,
        action_dim: int,
        action_lower: np.ndarray,
        action_upper: np.ndarray,
        hidden_dim: int = 4,
    ):
        """
        :param context_dim: Number of context features fed to the network.
        :param action_dim: Number of action values the network emits.
        :param action_lower: Per-action lower bound, shape (action_dim,).
        :param action_upper: Per-action upper bound, shape (action_dim,).
        :param hidden_dim: Width of the single hidden layer.
        """
        if context_dim <= 0 or action_dim <= 0 or hidden_dim <= 0:
            raise ValueError("context_dim, action_dim and hidden_dim must all be positive")

        self.context_dim = int(context_dim)
        self.action_dim = int(action_dim)
        self.hidden_dim = int(hidden_dim)
        self.action_lower = np.asarray(action_lower, dtype=float)
        self.action_upper = np.asarray(action_upper, dtype=float)

        if self.action_lower.shape != (self.action_dim,) or self.action_upper.shape != (self.action_dim,):
            raise ValueError("action bounds must each have shape (action_dim,)")
        if np.any(self.action_upper < self.action_lower):
            raise ValueError("every action upper bound must be at least its lower bound")

    @property
    def num_weights(self) -> int:
        """
        :return: Length of the flat weight vector that evolution searches over.
        """
        return (
            self.context_dim * self.hidden_dim  # input to hidden
            + self.hidden_dim  # hidden bias
            + self.hidden_dim * self.action_dim  # hidden to output
            + self.action_dim  # output bias
        )

    def actions(self, weights: np.ndarray, context: np.ndarray) -> np.ndarray:
        """
        Apply one prescriptor to a batch of contexts.

        A tanh hidden layer keeps activations bounded, and a logistic output
        squashed into the action range guarantees every prescribed action is
        feasible by construction. Evolution therefore never wastes effort on
        candidates that would have to be clipped or repaired.

        :param weights: Flat weight vector of length num_weights.
        :param context: Context rows of shape (num_rows, context_dim).
        :return: Actions of shape (num_rows, action_dim), inside the bounds.
        """
        weights = np.asarray(weights, dtype=float)
        if weights.shape != (self.num_weights,):
            raise ValueError(f"expected {self.num_weights} weights, got {weights.shape}")

        cursor = 0

        def take(count: int, shape: tuple) -> np.ndarray:
            nonlocal cursor
            chunk = weights[cursor : cursor + count].reshape(shape)
            cursor += count
            return chunk

        input_to_hidden = take(self.context_dim * self.hidden_dim, (self.context_dim, self.hidden_dim))
        hidden_bias = take(self.hidden_dim, (self.hidden_dim,))
        hidden_to_output = take(self.hidden_dim * self.action_dim, (self.hidden_dim, self.action_dim))
        output_bias = take(self.action_dim, (self.action_dim,))

        hidden = np.tanh(context @ input_to_hidden + hidden_bias)
        # Logistic squash, then rescale onto [action_lower, action_upper].
        unit = 1.0 / (1.0 + np.exp(-(hidden @ hidden_to_output + output_bias)))
        return self.action_lower + unit * (self.action_upper - self.action_lower)


def standardize(values: np.ndarray) -> Callable[[np.ndarray], np.ndarray]:
    """
    Build a reusable standardizer from a reference array.

    Context features are standardized before reaching the network so that a
    feature measured in millions does not swamp one measured in single digits
    purely because of its units.

    :param values: Reference array of shape (num_rows, num_features).
    :return: Function applying the same shift and scale to any matching array.
    """
    mean = values.mean(axis=0)
    scale = values.std(axis=0)
    scale = np.where(scale < 1e-12, 1.0, scale)

    def apply(other: np.ndarray) -> np.ndarray:
        return (other - mean) / scale

    return apply


def make_evaluator(
    network: PrescriptorNetwork,
    network_context: np.ndarray,
    raw_context: np.ndarray,
    predict_outcomes: Callable[[np.ndarray], np.ndarray],
    maximize: List[bool],
) -> Callable[[np.ndarray], np.ndarray]:
    """
    Build the objective function that the evolutionary search calls.

    Each candidate prescriptor is applied across every context row, the surrogate
    predicts the outcome of those actions, and the predictions are averaged into
    one objective vector. Averaging over the whole dataset is what stops a
    prescriptor from winning by exploiting a single lucky situation.

    Two views of the same contexts are needed and must not be mixed up. The
    network reads standardized context, so no feature dominates on units alone.
    The surrogate reads raw context, because it standardizes internally using the
    statistics it was fit with. Actions come out in raw units either way.

    The returned objectives are always minimization-oriented, because that is the
    convention the NSGA-II module works in; objectives the user wants maximized
    are negated here and negated back for display.

    :param network: The prescriptor architecture being evolved.
    :param network_context: Standardized context rows, shape (num_rows, context_dim).
    :param raw_context: The same rows in original units, shape (num_rows, context_dim).
    :param predict_outcomes: Maps raw (context, action) features to predicted outcomes.
    :param maximize: One flag per outcome; True where larger is better.
    :return: Function mapping a population of weight vectors to minimized objectives.
    """
    if network_context.shape != raw_context.shape:
        raise ValueError("standardized and raw context must have the same shape")

    signs = np.array([-1.0 if flag else 1.0 for flag in maximize], dtype=float)

    def evaluate(population: np.ndarray) -> np.ndarray:
        objectives = np.empty((population.shape[0], signs.shape[0]), dtype=float)
        for index, weights in enumerate(population):
            actions = network.actions(weights, network_context)
            predicted = predict_outcomes(np.hstack([raw_context, actions]))
            objectives[index] = predicted.mean(axis=0) * signs
        return objectives

    return evaluate
