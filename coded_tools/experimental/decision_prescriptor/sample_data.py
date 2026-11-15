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

from typing import Any

import numpy as np


class SampleData:
    """
    A synthetic dataset so the agent network runs out of the box.

    The scenario is delivery staffing on a portfolio of engagements. It is synthetic
    on purpose: the point of the example is the method, and inventing figures about
    real companies to dress it up would make the output look like evidence when it
    is not.

    The generator builds in two genuine conflicts, because a trade-off front is only
    interesting when the objectives actually disagree:

    * senior staffing lowers delivery risk but costs margin;
    * automation lifts margin but pushes out time to value while it is set up.

    It also builds in two interactions, because a prescriptor policy is only worth
    evolving when the best decision depends on the situation:

    * senior staff cut risk far more on urgent engagements than on calm ones;
    * automation pays off on large accounts, while on small ones its set-up costs
      more margin than it saves.

    So spreading senior staff evenly, or automating everywhere, is beaten by a policy
    that targets them. Those benefits exist because they are written into
    expected_outcomes below, not because they were discovered in real data.
    """

    CONTEXT_FIELDS: tuple[str, ...] = ("account_size", "urgency")
    ACTION_FIELDS: tuple[str, ...] = ("senior_staff_ratio", "automation_investment")
    OUTCOME_FIELDS: tuple[str, ...] = ("margin_pct", "delivery_risk", "time_to_value_weeks")
    OUTCOME_MAXIMIZE: tuple[bool, ...] = (True, False, False)

    # Standard deviation of the noise added to each outcome, in OUTCOME_FIELDS order.
    NOISE: tuple[float, ...] = (0.8, 0.02, 0.5)

    @staticmethod
    def expected_outcomes(context: np.ndarray, action: np.ndarray) -> np.ndarray:
        """
        The noise-free outcomes the example is generated from: its ground truth.

        Kept separate from generate so a test can check whether a strategy is better in
        truth, not merely according to the surrogate fitted on the noisy records.

        :param context: Rows of (account_size, urgency), shape (num_rows, 2).
        :param action: Rows of (senior_staff_ratio, automation_investment), shape (num_rows, 2).
        :return: Rows of (margin_pct, delivery_risk, time_to_value_weeks), shape (num_rows, 3).
        """
        account_size: np.ndarray = context[:, 0]  # $M of annual revenue
        urgency: np.ndarray = context[:, 1]
        senior_staff_ratio: np.ndarray = action[:, 0]
        automation_investment: np.ndarray = action[:, 1]

        margin_pct: np.ndarray = (
            22.0
            - 14.0 * senior_staff_ratio
            + 0.45 * account_size
            # Automation amortizes over revenue, with diminishing returns on the investment itself.
            + 1.2 * automation_investment * account_size
            - 3.0 * automation_investment**2
        )
        delivery_risk: np.ndarray = (
            0.50
            + 0.30 * urgency
            # Senior staff matter most where the engagement is urgent.
            - 0.10 * senior_staff_ratio
            - 0.50 * senior_staff_ratio * urgency
        )
        time_to_value_weeks: np.ndarray = (
            14.0 - 5.0 * senior_staff_ratio + 7.0 * automation_investment + 0.35 * account_size
        )
        return np.column_stack([margin_pct, delivery_risk, time_to_value_weeks])

    @staticmethod
    def generate(num_rows: int = 400, seed: int = 7) -> list[dict[str, float]]:
        """
        Generate historical engagement records: the expected outcomes plus noise.

        :param num_rows: Number of records to produce.
        :param seed: Seed controlling both the sampled decisions and the noise.
        :return: List of dicts holding every context, action and outcome field.
        """
        rng: np.random.Generator = np.random.default_rng(seed)

        context: np.ndarray = np.column_stack([rng.uniform(0.5, 10.0, num_rows), rng.uniform(0.0, 1.0, num_rows)])
        # Historical decisions vary widely, which is what gives the surrogate
        # something to learn from across the whole action space.
        action: np.ndarray = np.column_stack([rng.uniform(0.05, 0.95, num_rows), rng.uniform(0.0, 1.0, num_rows)])
        outcome: np.ndarray = SampleData.expected_outcomes(context, action) + rng.normal(
            0.0, SampleData.NOISE, size=(num_rows, len(SampleData.OUTCOME_FIELDS))
        )

        names: tuple[str, ...] = SampleData.CONTEXT_FIELDS + SampleData.ACTION_FIELDS + SampleData.OUTCOME_FIELDS
        table: np.ndarray = np.hstack([context, action, outcome])
        return [{name: float(value) for name, value in zip(names, row)} for row in table]

    @staticmethod
    def specification() -> dict[str, Any]:
        """
        Describe the sample problem in the shape LoadDecisionProblem stores.

        :return: Dict naming the context, action and outcome fields plus their direction.
        """
        return {
            "context_fields": list(SampleData.CONTEXT_FIELDS),
            "action_fields": list(SampleData.ACTION_FIELDS),
            "outcome_fields": list(SampleData.OUTCOME_FIELDS),
            "maximize": list(SampleData.OUTCOME_MAXIMIZE),
        }
