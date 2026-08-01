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
A synthetic dataset so the agent network runs out of the box.

The scenario is delivery staffing on a portfolio of engagements. It is synthetic
on purpose: the point of the example is the method, and inventing figures about
real companies to dress it up would make the output look like evidence when it
is not.

The generator builds in two genuine conflicts, because a trade-off front is only
interesting when the objectives actually disagree:

* senior staffing lowers delivery risk but costs margin;
* automation lifts margin but pushes out time to value while it is set up.

An optimizer that returned a single answer here would be hiding one of those
exchanges. The Pareto front surfaces both and leaves the choice with a human.
"""

from typing import Dict
from typing import List

import numpy as np

CONTEXT_FIELDS = ["account_size", "urgency"]
ACTION_FIELDS = ["senior_staff_ratio", "automation_investment"]
OUTCOME_FIELDS = ["margin_pct", "delivery_risk", "time_to_value_weeks"]

# True where a larger outcome value is better.
OUTCOME_MAXIMIZE = [True, False, False]


def generate(num_rows: int = 400, seed: int = 7) -> List[Dict[str, float]]:
    """
    Generate historical engagement records.

    :param num_rows: Number of records to produce.
    :param seed: Seed controlling both the sampled decisions and the noise.
    :return: List of dicts holding every context, action and outcome field.
    """
    rng = np.random.default_rng(seed)

    account_size = rng.uniform(0.5, 10.0, num_rows)  # $M of annual revenue
    urgency = rng.uniform(0.0, 1.0, num_rows)

    # Historical decisions vary widely, which is what gives the surrogate
    # something to learn from across the whole action space.
    senior_staff_ratio = rng.uniform(0.05, 0.95, num_rows)
    automation_investment = rng.uniform(0.0, 1.0, num_rows)

    margin_pct = (
        22.0
        + 6.0 * automation_investment
        - 14.0 * senior_staff_ratio
        + 0.45 * account_size
        + rng.normal(0.0, 0.8, num_rows)
    )
    delivery_risk = (
        0.55
        - 0.38 * senior_staff_ratio
        - 0.10 * automation_investment
        + 0.22 * urgency
        + rng.normal(0.0, 0.02, num_rows)
    )
    time_to_value_weeks = (
        14.0
        - 5.0 * senior_staff_ratio
        + 7.0 * automation_investment
        + 0.35 * account_size
        + rng.normal(0.0, 0.5, num_rows)
    )

    return [
        {
            "account_size": float(account_size[i]),
            "urgency": float(urgency[i]),
            "senior_staff_ratio": float(senior_staff_ratio[i]),
            "automation_investment": float(automation_investment[i]),
            "margin_pct": float(margin_pct[i]),
            "delivery_risk": float(delivery_risk[i]),
            "time_to_value_weeks": float(time_to_value_weeks[i]),
        }
        for i in range(num_rows)
    ]


def specification() -> Dict[str, object]:
    """
    Describe the sample problem in the shape the prescriptor tool expects.

    :return: Dict naming the context, action and outcome fields plus their direction.
    """
    return {
        "context_fields": list(CONTEXT_FIELDS),
        "action_fields": list(ACTION_FIELDS),
        "outcome_fields": list(OUTCOME_FIELDS),
        "maximize": list(OUTCOME_MAXIMIZE),
    }
