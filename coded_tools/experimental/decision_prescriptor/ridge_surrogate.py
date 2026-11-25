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


class RidgeSurrogate:
    """
    Closed-form ridge regression from features to outcomes: the regression core of the
    "predictor" half of Evolutionary Surrogate-assisted Prescription.

    QuadraticSurrogate feeds it a second-order expansion of (context, action), and the
    fitted model then stands in for reality during the search. That substitution is the
    whole point: evolution needs to score hundreds of thousands of candidate strategies,
    which is only affordable against a model, never against the real world.

    Ridge regression is used deliberately. It has a closed-form solution, so a fit is
    exact and reproducible with no training loop, no learning rate and no random
    seed to explain away. The regularization term also keeps the model finite when
    features are collinear, which is common in small decision datasets.

    Features are standardized internally so a single regularization strength is
    meaningful across columns measured in different units.
    """

    EPSILON: float = 1e-12

    # A row with leverage this close to 1 is interpolated, and leaving it out is undefined.
    MAX_LEVERAGE: float = 1.0 - 1e-9

    def __init__(self, alpha: float = 1.0):
        """
        :param alpha: Regularization strength. Larger values shrink coefficients
            harder, trading fit for stability. Must be non-negative.
        """
        if alpha < 0.0:
            raise ValueError("alpha must be non-negative")
        self.alpha: float = float(alpha)
        self.coefficients: np.ndarray | None = None
        self.feature_mean: np.ndarray | None = None
        self.feature_scale: np.ndarray | None = None

    def fit(self, features: np.ndarray, targets: np.ndarray) -> Self:
        """
        Solve for the ridge coefficients in closed form.

        Uses (X'X + alpha*I)^-1 X'Y on standardized features with an unpenalized
        bias column appended, which is why the identity block skips that column.
        With alpha = 0 it is ordinary least squares, solved so that a rank-deficient
        design still fits.

        :param features: Array of shape (num_rows, num_features).
        :param targets: Array of shape (num_rows, num_targets).
        :return: self, so a fit can be chained.
        """
        features = np.asarray(features, dtype=float)
        targets = np.asarray(targets, dtype=float)

        if features.shape[0] != targets.shape[0]:
            raise ValueError(f"features has {features.shape[0]} rows but targets has {targets.shape[0]}")
        if features.shape[0] == 0:
            raise ValueError("cannot fit a surrogate on zero rows")

        self.feature_mean = features.mean(axis=0)
        scale: np.ndarray = features.std(axis=0)
        # A constant column carries no information; scaling it by 1 leaves it at zero.
        self.feature_scale = np.where(scale < self.EPSILON, 1.0, scale)

        design: np.ndarray = self._design_matrix(features)
        num_columns: int = design.shape[1]

        if self.alpha == 0.0:
            # With no penalty the normal equations are singular whenever the design is
            # rank-deficient, as it is when a feature column is constant (standardized to
            # zeros). Least squares handles that, giving such a column a zero coefficient.
            self.coefficients = np.linalg.lstsq(design, targets, rcond=None)[0]
            return self

        self.coefficients = np.linalg.solve(design.T @ design + self._penalty(num_columns), design.T @ targets)
        return self

    def predict(self, features: np.ndarray) -> np.ndarray:
        """
        Predict outcomes for new (context, action) rows.

        :param features: Array of shape (num_rows, num_features).
        :return: Predictions of shape (num_rows, num_targets).
        """
        if self.coefficients is None:
            raise RuntimeError("surrogate must be fit before predict is called")
        return self._design_matrix(np.asarray(features, dtype=float)) @ self.coefficients

    def r_squared(self, features: np.ndarray, targets: np.ndarray) -> np.ndarray:
        """
        Coefficient of determination per target, on the given rows.

        Reported back to the user because a prescriptor is only ever as
        trustworthy as the surrogate it was evolved against. A weak fit here means
        the Pareto front is a picture of the model, not of the world.

        :param features: Array of shape (num_rows, num_features).
        :param targets: Array of shape (num_rows, num_targets).
        :return: R-squared per target, shape (num_targets,).
        """
        targets = np.asarray(targets, dtype=float)
        return self._explained(targets - self.predict(features), targets)

    def leave_one_out_r_squared(self, features: np.ndarray, targets: np.ndarray) -> np.ndarray:
        """
        Coefficient of determination per target when every row is predicted by a model
        fitted without that row.

        In-sample R² rewards memorizing: with nearly as many features as rows it is high
        even when the outcomes are pure noise. Leaving each row out measures how well the
        model predicts records it has not seen, which is what the search relies on.

        No refitting is needed. Ridge is a linear smoother, so the prediction for row i
        from a fit without row i differs from the full fit's residual by a closed-form
        factor: residual_i / (1 - h_ii), where h_ii is the row's leverage. That identity is
        exact whenever alpha > 0 or the design has full column rank. The standardization
        statistics are still taken from every row, so it is leave-one-out for the
        regression given that standardization.

        :param features: The rows the model was fit on, shape (num_rows, num_features).
            Leverage is a property of the training design, so other rows give a meaningless answer.
        :param targets: Their targets, shape (num_rows, num_targets).
        :return: Leave-one-out R-squared per target, shape (num_targets,).
        :raises RuntimeError: If the model has not been fit.
        :raises ValueError: If some row is fitted exactly, so its held-out error cannot be estimated.
        """
        if self.coefficients is None:
            raise RuntimeError("surrogate must be fit before its leave-one-out fit is measured")

        targets = np.asarray(targets, dtype=float)
        design: np.ndarray = self._design_matrix(np.asarray(features, dtype=float))
        leverage: np.ndarray = self._leverage(design)
        if np.any(leverage > self.MAX_LEVERAGE):
            raise ValueError(
                f"{int(np.sum(leverage > self.MAX_LEVERAGE))} of {design.shape[0]} rows are fitted exactly, so "
                "the model's error on unseen records cannot be estimated. Supply more rows or fewer fields."
            )

        held_out_residuals: np.ndarray = (targets - design @ self.coefficients) / (1.0 - leverage)[:, None]
        return self._explained(held_out_residuals, targets)

    def _penalty(self, num_columns: int) -> np.ndarray:
        """
        Build the ridge penalty matrix for a design with a trailing bias column.

        :param num_columns: Number of design columns, the bias column included.
        :return: alpha times the identity, with the bias entry zeroed.
        """
        penalty: np.ndarray = self.alpha * np.eye(num_columns)
        # Do not penalize the bias column: shrinking the intercept would bias predictions.
        penalty[-1, -1] = 0.0
        return penalty

    def _leverage(self, design: np.ndarray) -> np.ndarray:
        """
        Compute each row's leverage: the diagonal of the hat matrix that maps targets to fitted values.

        :param design: Standardized design matrix with its bias column, shape (num_rows, num_columns).
        :return: Leverage per row, shape (num_rows,), each between 0 and 1.
        """
        if self.alpha == 0.0:
            # Least squares fits through the pseudo-inverse, so its hat matrix is design @ pinv(design).
            return np.sum(design * np.linalg.pinv(design).T, axis=1)
        projection: np.ndarray = np.linalg.solve(design.T @ design + self._penalty(design.shape[1]), design.T)
        return np.sum(design * projection.T, axis=1)

    def _explained(self, residuals: np.ndarray, targets: np.ndarray) -> np.ndarray:
        """
        Turn residuals into R-squared per target.

        :param residuals: Prediction errors, shape (num_rows, num_targets).
        :param targets: The targets they were measured against, same shape.
        :return: 1 - residual sum of squares / total sum of squares per target; 0 for a constant target.
        """
        residual: np.ndarray = np.sum(residuals**2, axis=0)
        total: np.ndarray = np.sum((targets - targets.mean(axis=0)) ** 2, axis=0)
        return np.where(total < self.EPSILON, 0.0, 1.0 - residual / np.where(total < self.EPSILON, 1.0, total))

    def _design_matrix(self, features: np.ndarray) -> np.ndarray:
        """
        Standardize features and append the bias column.

        :param features: Raw feature array of shape (num_rows, num_features).
        :return: Design matrix of shape (num_rows, num_features + 1).
        """
        standardized: np.ndarray = (features - self.feature_mean) / self.feature_scale
        return np.hstack([standardized, np.ones((standardized.shape[0], 1))])
