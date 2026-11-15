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

from typing import Self

import numpy as np

from coded_tools.experimental.decision_prescriptor.ridge_surrogate import RidgeSurrogate
from coded_tools.experimental.decision_prescriptor.standardizer import Standardizer


class QuadraticSurrogate:
    """
    Ridge regression on a second-order expansion of the (context, action) inputs: every
    input, every pairwise product and every square. This is the "predictor" half of
    Evolutionary Surrogate-assisted Prescription in this network.

    The products are what make a prescriptor policy worth evolving. PrescriptorEvaluator
    scores a policy by averaging predictions over every context. Under a model that is
    additive in context and action, that average depends on the policy only through its
    mean action, so every policy scores exactly like one fixed action and mapping
    context to action buys nothing. A context x action product lets the best action
    depend on the situation. A square lets a decision show diminishing returns, so
    that past some point more of it is simply worse.

    It stays closed form, so a fit is exact and reproducible. Inputs are standardized
    before products are taken, which keeps each product from being nearly collinear
    with its own factors.
    """

    def __init__(self, alpha: float = 1.0):
        """
        :param alpha: Ridge regularization strength, passed to RidgeSurrogate. Must be non-negative.
        """
        self.ridge: RidgeSurrogate = RidgeSurrogate(alpha=alpha)
        self.input_scaler: Standardizer | None = None

    def fit(self, features: np.ndarray, targets: np.ndarray) -> Self:
        """
        Fit ridge regression on the second-order expansion of the features.

        :param features: Raw (context, action) rows, shape (num_rows, num_inputs).
        :param targets: Outcomes, shape (num_rows, num_targets).
        :return: self, so a fit can be chained.
        :raises ValueError: If the row counts differ or there are no rows.
        """
        features = np.asarray(features, dtype=float)
        if features.shape[0] == 0:
            raise ValueError("cannot fit a surrogate on zero rows")
        self.input_scaler = Standardizer(features)
        self.ridge.fit(self._expand(features), targets)
        return self

    def predict(self, features: np.ndarray) -> np.ndarray:
        """
        Predict outcomes for raw (context, action) rows.

        :param features: Array of shape (num_rows, num_inputs).
        :return: Predictions of shape (num_rows, num_targets).
        :raises RuntimeError: If the model has not been fit.
        """
        return self.ridge.predict(self._expand(features))

    def r_squared(self, features: np.ndarray, targets: np.ndarray) -> np.ndarray:
        """
        In-sample coefficient of determination per target, on the given rows.

        :param features: Raw (context, action) rows, shape (num_rows, num_inputs).
        :param targets: Their outcomes, shape (num_rows, num_targets).
        :return: R-squared per target, shape (num_targets,).
        :raises RuntimeError: If the model has not been fit.
        """
        return self.ridge.r_squared(self._expand(features), targets)

    def leave_one_out_r_squared(self, features: np.ndarray, targets: np.ndarray) -> np.ndarray:
        """
        Held-out coefficient of determination per target; see RidgeSurrogate.leave_one_out_r_squared.

        :param features: The raw rows the model was fit on, shape (num_rows, num_inputs).
        :param targets: Their outcomes, shape (num_rows, num_targets).
        :return: Leave-one-out R-squared per target, shape (num_targets,).
        :raises RuntimeError: If the model has not been fit.
        :raises ValueError: If some row is fitted exactly, so its held-out error cannot be estimated.
        """
        return self.ridge.leave_one_out_r_squared(self._expand(features), targets)

    def _expand(self, features: np.ndarray) -> np.ndarray:
        """
        Standardize the inputs, then append every pairwise product and every square.

        :param features: Raw (context, action) rows, shape (num_rows, num_inputs).
        :return: Array of shape (num_rows, num_inputs + num_inputs * (num_inputs + 1) / 2).
        :raises RuntimeError: If the model has not been fit, so there is no standardization yet.
        """
        if self.input_scaler is None:
            raise RuntimeError("surrogate must be fit before it can expand features")
        standardized: np.ndarray = self.input_scaler.transform(np.asarray(features, dtype=float))
        num_inputs: int = standardized.shape[1]
        columns: list[np.ndarray] = [standardized]
        for first in range(num_inputs):
            # Start at `first` so each square is included once and each product once.
            for second in range(first, num_inputs):
                columns.append(standardized[:, first : first + 1] * standardized[:, second : second + 1])
        return np.hstack(columns)
