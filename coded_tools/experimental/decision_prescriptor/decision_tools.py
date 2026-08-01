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
The CodedTools that expose Evolutionary Surrogate-assisted Prescription to an
agent network.

The division of labour is the point of this network. Everything numeric —
fitting, searching, ranking, drawing — happens in deterministic Python here. The
agents above decide what to model, read the resulting front and explain the
trade-off in words. An LLM is never asked to invent a number, because a
confidently invented number is indistinguishable from a real one, and the whole
value of a decision tool is that its numbers can be trusted.

State moves between these tools through `sly_data`, neuro-san's channel for
values that must never enter an LLM prompt. A fitted model and a few hundred
candidate strategies belong there: they are large, they are exact, and passing
them as chat text would both blow the context window and risk mangling them.
"""

import asyncio
import json
import os
import time
from typing import Any
from typing import Dict
from typing import List

import numpy as np
from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.experimental.decision_prescriptor import sample_data
from coded_tools.experimental.decision_prescriptor.charts import render_report
from coded_tools.experimental.decision_prescriptor.nsga2 import evolve
from coded_tools.experimental.decision_prescriptor.nsga2 import select_spread
from coded_tools.experimental.decision_prescriptor.prescriptor import PrescriptorNetwork
from coded_tools.experimental.decision_prescriptor.prescriptor import make_evaluator
from coded_tools.experimental.decision_prescriptor.prescriptor import standardize
from coded_tools.experimental.decision_prescriptor.surrogate import RidgeSurrogate
from coded_tools.experimental.decision_prescriptor.surrogate import build_training_arrays

# Keys used to hand state between the tools in this module via sly_data.
_DATASET_KEY = "decision_dataset"
_SPEC_KEY = "decision_spec"
_SURROGATE_KEY = "decision_surrogate"
_RESULT_KEY = "decision_result"

# How many strategies a human is actually shown. The archive behind it stays whole.
_DISPLAY_LIMIT = 24


class LoadDecisionProblem(CodedTool):
    """
    Load the decision problem: historical records plus which fields play which role.
    """

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        """
        Put a dataset and its field specification into sly_data.

        Supplying no rows loads the bundled synthetic delivery-staffing example,
        so the network is runnable without any data preparation.

        :param args: May contain "rows" (list of record dicts), "context_fields",
            "action_fields", "outcome_fields" and "maximize" (list of booleans).
        :param sly_data: Out-of-band channel; the dataset and spec are written here.
        :return: A short human-readable confirmation, or an error message.
        """
        rows = args.get("rows")

        if not rows:
            rows = sample_data.generate()
            spec = sample_data.specification()
        else:
            spec = {
                "context_fields": args.get("context_fields") or [],
                "action_fields": args.get("action_fields") or [],
                "outcome_fields": args.get("outcome_fields") or [],
                "maximize": args.get("maximize") or [],
            }
            missing = [name for name in ("context_fields", "action_fields", "outcome_fields") if not spec[name]]
            if missing:
                return f"Error: must name {', '.join(missing)} when supplying your own rows."
            if len(spec["maximize"]) != len(spec["outcome_fields"]):
                return (
                    f"Error: 'maximize' has {len(spec['maximize'])} entries but there are "
                    f"{len(spec['outcome_fields'])} outcome fields; one direction is needed per outcome."
                )

        try:
            build_training_arrays(rows, spec["context_fields"], spec["action_fields"], spec["outcome_fields"])
        except ValueError as error:
            return f"Error: {error}"

        sly_data[_DATASET_KEY] = rows
        sly_data[_SPEC_KEY] = spec

        directions = ", ".join(
            f"{name} ({'maximize' if flag else 'minimize'})"
            for name, flag in zip(spec["outcome_fields"], spec["maximize"])
        )
        return (
            f"Loaded {len(rows)} records. "
            f"Context: {', '.join(spec['context_fields'])}. "
            f"Decisions: {', '.join(spec['action_fields'])}. "
            f"Outcomes: {directions}."
        )

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        """Run invoke asynchronously."""
        return await asyncio.to_thread(self.invoke, args, sly_data)


class FitSurrogate(CodedTool):
    """
    Fit the predictor that stands in for reality during the search.
    """

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        """
        Fit ridge regression from (context, action) to outcomes and report its fit.

        The R-squared per outcome is returned rather than hidden, because it is
        the honest ceiling on everything downstream: a prescriptor evolved against
        a weak surrogate has optimized a bad map of the world, and the resulting
        front should not be trusted just because it is drawn precisely.

        :param args: May contain "alpha", the ridge regularization strength.
        :param sly_data: Must already hold the dataset; the fitted model is written here.
        :return: A human-readable summary of fit quality, or an error message.
        """
        rows = sly_data.get(_DATASET_KEY)
        spec = sly_data.get(_SPEC_KEY)
        if not rows or not spec:
            return "Error: no decision problem loaded yet. Load the problem first."

        try:
            alpha = float(args.get("alpha", 1.0))
        except (TypeError, ValueError):
            return "Error: 'alpha' must be a number."
        if alpha < 0:
            return "Error: 'alpha' must be non-negative."

        arrays = build_training_arrays(rows, spec["context_fields"], spec["action_fields"], spec["outcome_fields"])
        features = np.hstack([arrays["context"], arrays["action"]])

        surrogate = RidgeSurrogate(alpha=alpha).fit(features, arrays["outcome"])
        scores = surrogate.r_squared(features, arrays["outcome"])

        sly_data[_SURROGATE_KEY] = surrogate

        reported = ", ".join(f"{name} R²={score:.3f}" for name, score in zip(spec["outcome_fields"], scores))
        weakest = float(np.min(scores))
        caveat = (
            " Fit is weak, so treat the front as indicative only."
            if weakest < 0.5
            else " Fit is strong enough to search against."
        )
        return f"Surrogate fitted on {len(rows)} records (alpha={alpha:g}). {reported}.{caveat}"

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        """Run invoke asynchronously."""
        return await asyncio.to_thread(self.invoke, args, sly_data)


class EvolvePrescriptors(CodedTool):
    """
    Evolve a Pareto front of prescriptor policies against the fitted surrogate.
    """

    # Wiring the dataset, network, evaluator, bounds and result together happens here.
    # pylint: disable=too-many-locals
    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        """
        Run NSGA-II over prescriptor weights and summarize the resulting front.

        :param args: May contain "population_size", "generations", "hidden_dim" and "seed".
        :param sly_data: Must hold the dataset, spec and fitted surrogate; the
            front and its history are written here.
        :return: A human-readable summary of the trade-off found, or an error message.
        """
        rows = sly_data.get(_DATASET_KEY)
        spec = sly_data.get(_SPEC_KEY)
        surrogate = sly_data.get(_SURROGATE_KEY)
        if not rows or not spec:
            return "Error: no decision problem loaded yet. Load the problem first."
        if surrogate is None:
            return "Error: the surrogate has not been fitted yet. Fit it before evolving prescriptors."

        try:
            population_size = int(args.get("population_size", 60))
            generations = int(args.get("generations", 50))
            hidden_dim = int(args.get("hidden_dim", 4))
            seed = int(args.get("seed", 0))
        except (TypeError, ValueError):
            return "Error: population_size, generations, hidden_dim and seed must all be whole numbers."
        if min(population_size, generations, hidden_dim) < 1:
            return "Error: population_size, generations and hidden_dim must all be at least 1."

        arrays = build_training_arrays(rows, spec["context_fields"], spec["action_fields"], spec["outcome_fields"])
        context, action = arrays["context"], arrays["action"]

        # Actions are held inside the range the historical data actually covers.
        # Outside it the surrogate is extrapolating, and its predictions there are
        # a property of the model rather than evidence about the world.
        network = PrescriptorNetwork(
            context_dim=context.shape[1],
            action_dim=action.shape[1],
            action_lower=action.min(axis=0),
            action_upper=action.max(axis=0),
            hidden_dim=hidden_dim,
        )

        to_standard = standardize(context)
        evaluate = make_evaluator(network, to_standard(context), context, surrogate.predict, spec["maximize"])

        bounds = np.full(network.num_weights, 3.0)
        started = time.time()
        result = evolve(
            evaluate,
            -bounds,
            bounds,
            population_size=population_size,
            generations=generations,
            seed=seed,
        )
        elapsed = time.time() - started

        # Back to display orientation: undo the negation applied to maximized outcomes.
        signs = np.array([-1.0 if flag else 1.0 for flag in spec["maximize"]], dtype=float)
        front = result["front_objectives"] * signs

        keep = select_spread(result["front_objectives"], _DISPLAY_LIMIT)
        shown_front = front[keep]
        shown_actions = np.array(
            [network.actions(weights, to_standard(context)).mean(axis=0) for weights in result["front_genes"][keep]]
        )

        sly_data[_RESULT_KEY] = {
            "front": shown_front,
            "actions": shown_actions,
            "population": result["objectives"] * signs,
            "hypervolume_history": result["hypervolume_history"],
            "archive_size": int(front.shape[0]),
            "generations": generations,
            "elapsed_seconds": elapsed,
        }

        return json.dumps(
            {
                "strategies_found": int(front.shape[0]),
                "strategies_shown": int(shown_front.shape[0]),
                "generations": generations,
                "seconds": round(elapsed, 2),
                "achievable_range": {
                    name: {
                        "best": round(float(shown_front[:, i].max() if flag else shown_front[:, i].min()), 4),
                        "worst": round(float(shown_front[:, i].min() if flag else shown_front[:, i].max()), 4),
                    }
                    for i, (name, flag) in enumerate(zip(spec["outcome_fields"], spec["maximize"]))
                },
                "note": (
                    "Every strategy listed is non-dominated: none can be improved on one outcome "
                    "without giving something up on another. Choosing between them is a judgement "
                    "call, not a calculation."
                ),
            },
            indent=2,
        )

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        """Run invoke asynchronously."""
        return await asyncio.to_thread(self.invoke, args, sly_data)


class RenderParetoReport(CodedTool):
    """
    Write the trade-off front out as a self-contained HTML report.
    """

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        """
        Render the charts and return the path to the file written.

        :param args: May contain "title" and "output_path".
        :param sly_data: Must hold the evolved result.
        :return: The path written, or an error message.
        """
        spec = sly_data.get(_SPEC_KEY)
        result = sly_data.get(_RESULT_KEY)
        if not spec or not result:
            return "Error: nothing to render yet. Evolve the prescriptors first."

        title = str(args.get("title") or "Decision trade-off front")
        output_path = str(args.get("output_path") or "decision_prescriptor_report.html")

        front = result["front"]
        balanced = self._balanced_index(front)

        summary = {
            "Strategies on front": f"{result['archive_size']:,}",
            "Shown here": str(front.shape[0]),
            "Generations": str(result["generations"]),
            "Search time": f"{result['elapsed_seconds']:.1f}s",
        }

        document = render_report(
            title=title,
            front=front,
            dominated=result["population"],
            actions=result["actions"],
            objective_labels=spec["outcome_fields"],
            action_labels=spec["action_fields"],
            hypervolume_history=result["hypervolume_history"],
            summary=summary,
            balanced_index=balanced,
        )

        try:
            directory = os.path.dirname(os.path.abspath(output_path))
            os.makedirs(directory, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as handle:
                handle.write(document)
        except OSError as error:
            return f"Error writing the report: {error}"

        return (
            f"Wrote the trade-off report to {os.path.abspath(output_path)} "
            f"({front.shape[0]} strategies charted, balanced pick highlighted as strategy {balanced + 1})."
        )

    @staticmethod
    def _balanced_index(front: np.ndarray) -> int:
        """
        Pick the strategy closest to the centre of the front, in normalized units.

        This is offered as a starting point for discussion, not a recommendation.
        Nothing in the mathematics prefers the middle of a front; only a human who
        knows what the objectives are worth can rank them.

        :param front: Objective values per strategy, in display orientation.
        :return: Row index of the most central strategy.
        """
        low = front.min(axis=0)
        high = front.max(axis=0)
        span = np.where((high - low) < 1e-12, 1.0, high - low)
        normalized = (front - low) / span
        return int(np.argmin(np.linalg.norm(normalized - 0.5, axis=1)))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        """Run invoke asynchronously."""
        return await asyncio.to_thread(self.invoke, args, sly_data)


def describe_front(front: np.ndarray, labels: List[str], maximize: List[bool]) -> str:
    """
    Summarize a front in plain language, for use in tests and documentation.

    :param front: Objective values per strategy, in display orientation.
    :param labels: Objective display names.
    :param maximize: True where larger is better, per objective.
    :return: One line per objective describing the achievable range.
    """
    lines = []
    for index, (name, flag) in enumerate(zip(labels, maximize)):
        column = front[:, index]
        best = column.max() if flag else column.min()
        worst = column.min() if flag else column.max()
        lines.append(f"{name}: best {best:.3f}, worst {worst:.3f} across the front")
    return "\n".join(lines)
