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
NSGA-II, implemented from the original description in Deb et al. (2002),
"A Fast and Elitist Multiobjective Genetic Algorithm: NSGA-II".

This module is deliberately dependency-light (numpy only) and free of any
neuro-san import, so the search behaviour can be unit-tested on its own.

Convention: every objective in this module is MINIMIZED. Callers that want to
maximize an objective negate it at the boundary and negate the result back.
"""

from typing import Callable
from typing import Dict
from typing import List
from typing import Tuple

import numpy as np

# Guards a division by zero when an objective is constant across a front.
_EPSILON = 1e-12


def dominates(objectives_a: np.ndarray, objectives_b: np.ndarray) -> bool:
    """
    Determine whether one objective vector Pareto-dominates another.

    Under minimization, a dominates b when a is no worse on every objective and
    strictly better on at least one. If neither dominates the other the two
    solutions are incomparable, which is what makes the trade-off real.

    :param objectives_a: Objective vector of the candidate solution.
    :param objectives_b: Objective vector it is compared against.
    :return: True if objectives_a dominates objectives_b.
    """
    return bool(np.all(objectives_a <= objectives_b) and np.any(objectives_a < objectives_b))


def non_dominated_mask(objectives: np.ndarray, chunk_size: int = 512) -> np.ndarray:
    """
    Flag the solutions that nothing else dominates.

    This answers the same question as the first front of `fast_non_dominated_sort`
    but computes it with array operations instead of a Python double loop. The
    archive is re-derived every generation and grows into the thousands, which is
    exactly where the elementwise version becomes the cost of the whole run.

    Work is done in row blocks so peak memory stays proportional to
    `chunk_size * num_points` rather than the square of the population.

    :param objectives: Array of shape (num_points, num_objectives), minimized.
    :param chunk_size: Number of candidates compared per block.
    :return: Boolean mask, True where the solution is non-dominated.
    """
    num_points = objectives.shape[0]
    mask = np.ones(num_points, dtype=bool)
    if num_points == 0:
        return mask

    for start in range(0, num_points, chunk_size):
        stop = min(start + chunk_size, num_points)
        block = objectives[start:stop]

        # no_worse[i, j] : solution i is no worse than block j on every objective.
        no_worse = np.all(objectives[:, None, :] <= block[None, :, :], axis=2)
        # strictly_better[i, j] : solution i beats block j on at least one objective.
        strictly_better = np.any(objectives[:, None, :] < block[None, :, :], axis=2)
        mask[start:stop] = ~np.any(no_worse & strictly_better, axis=0)

    return mask


def fast_non_dominated_sort(objectives: np.ndarray) -> List[List[int]]:
    """
    Partition a population into Pareto fronts.

    Front 0 holds the solutions nothing dominates. Front 1 holds those dominated
    only by front 0, and so on. This is Deb's O(M*N^2) formulation: for each
    solution count how many dominate it, then peel off the zero-count layer and
    decrement the counts of everything it dominated.

    :param objectives: Array of shape (population_size, num_objectives), minimized.
    :return: List of fronts, each a list of row indices into objectives, best front first.
    """
    population_size = objectives.shape[0]
    if population_size == 0:
        return []

    # dominated_by[i] lists the solutions that i dominates.
    dominated_by: List[List[int]] = [[] for _ in range(population_size)]
    # domination_count[i] is how many solutions dominate i.
    domination_count = np.zeros(population_size, dtype=int)

    for i in range(population_size):
        for j in range(i + 1, population_size):
            if dominates(objectives[i], objectives[j]):
                dominated_by[i].append(j)
                domination_count[j] += 1
            elif dominates(objectives[j], objectives[i]):
                dominated_by[j].append(i)
                domination_count[i] += 1

    fronts: List[List[int]] = []
    current_front = [i for i in range(population_size) if domination_count[i] == 0]

    while current_front:
        fronts.append(current_front)
        next_front: List[int] = []
        for i in current_front:
            for j in dominated_by[i]:
                domination_count[j] -= 1
                if domination_count[j] == 0:
                    next_front.append(j)
        current_front = sorted(next_front)

    return fronts


def crowding_distance(objectives: np.ndarray, front: List[int]) -> np.ndarray:
    """
    Measure how isolated each solution is within its own front.

    For every objective the front is sorted and each solution receives the
    normalized gap between its two neighbours. The two extremes get infinity so
    elitist selection never discards the ends of the front. Summing across
    objectives gives a diversity score used as the tie-break inside a front:
    crowded regions lose, sparse regions survive, and the front stays spread out.

    :param objectives: Array of shape (population_size, num_objectives), minimized.
    :param front: Row indices belonging to a single Pareto front.
    :return: Array of distances aligned with the order of `front`.
    """
    front_size = len(front)
    distances = np.zeros(front_size, dtype=float)
    if front_size <= 2:
        return np.full(front_size, np.inf)

    front_objectives = objectives[front]
    num_objectives = front_objectives.shape[1]

    for objective_index in range(num_objectives):
        values = front_objectives[:, objective_index]
        order = np.argsort(values, kind="stable")
        spread = values[order[-1]] - values[order[0]]

        # A constant objective separates nobody, so it contributes nothing.
        if spread < _EPSILON:
            continue

        distances[order[0]] = np.inf
        distances[order[-1]] = np.inf
        for position in range(1, front_size - 1):
            neighbour_gap = values[order[position + 1]] - values[order[position - 1]]
            distances[order[position]] += neighbour_gap / spread

    return distances


def rank_and_crowding(objectives: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute the front index and crowding distance of every solution.

    :param objectives: Array of shape (population_size, num_objectives), minimized.
    :return: Tuple of (rank per solution, crowding distance per solution).
    """
    population_size = objectives.shape[0]
    ranks = np.zeros(population_size, dtype=int)
    crowding = np.zeros(population_size, dtype=float)

    for front_index, front in enumerate(fast_non_dominated_sort(objectives)):
        ranks[front] = front_index
        crowding[front] = crowding_distance(objectives, front)

    return ranks, crowding


def binary_tournament(
    ranks: np.ndarray,
    crowding: np.ndarray,
    num_winners: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Select parents by the crowded-comparison operator.

    Two random candidates compete. The lower front wins; on a tie the less
    crowded one wins. This is the only place selection pressure enters, and it
    pushes on both convergence (rank) and diversity (crowding) at once.

    :param ranks: Front index per solution.
    :param crowding: Crowding distance per solution.
    :param num_winners: How many parent indices to draw.
    :param rng: Seeded generator, so a run is reproducible.
    :return: Array of selected indices of length num_winners.
    """
    population_size = ranks.shape[0]
    left = rng.integers(0, population_size, size=num_winners)
    right = rng.integers(0, population_size, size=num_winners)

    left_wins = (ranks[left] < ranks[right]) | ((ranks[left] == ranks[right]) & (crowding[left] > crowding[right]))
    return np.where(left_wins, left, right)


# Deb's operators take their distribution index and rates as explicit parameters
# so a run can be tuned without editing the module.
# pylint: disable=too-many-arguments,too-many-positional-arguments
def sbx_crossover(
    parents_a: np.ndarray,
    parents_b: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    rng: np.random.Generator,
    eta: float = 15.0,
    probability: float = 0.9,
) -> np.ndarray:
    """
    Simulated binary crossover.

    SBX mimics the behaviour of single-point crossover on binary strings while
    operating on real numbers: children land near their parents, and the spread
    parameter eta controls how near. Large eta keeps children tight to the
    parents, small eta explores further out.

    :param parents_a: First parent per pairing, shape (num_pairs, num_genes).
    :param parents_b: Second parent per pairing, same shape.
    :param lower: Per-gene lower bound.
    :param upper: Per-gene upper bound.
    :param rng: Seeded generator.
    :param eta: Distribution index; higher means children closer to parents.
    :param probability: Chance that a given pairing is crossed at all.
    :return: One child per pairing, shape (num_pairs, num_genes).
    """
    num_pairs, num_genes = parents_a.shape
    children = parents_a.copy()

    # Draw the spread factor betaq from the SBX distribution.
    uniform = rng.random(size=(num_pairs, num_genes))
    beta_q = np.where(
        uniform <= 0.5,
        (2.0 * uniform) ** (1.0 / (eta + 1.0)),
        (1.0 / (2.0 * (1.0 - uniform))) ** (1.0 / (eta + 1.0)),
    )

    blended = 0.5 * ((1.0 + beta_q) * parents_a + (1.0 - beta_q) * parents_b)

    # Apply per-pair, then per-gene, so some genes pass through untouched.
    pair_mask = rng.random(size=(num_pairs, 1)) <= probability
    gene_mask = rng.random(size=(num_pairs, num_genes)) <= 0.5
    children = np.where(pair_mask & gene_mask, blended, children)

    return np.clip(children, lower, upper)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def polynomial_mutation(
    population: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    rng: np.random.Generator,
    eta: float = 20.0,
    probability: float = None,
) -> np.ndarray:
    """
    Polynomial mutation.

    Perturbs a gene by an amount drawn from a polynomial distribution centred on
    zero and scaled to the gene's own range, so a mutation is small far more
    often than it is large. The default per-gene rate of 1/num_genes means about
    one gene changes per individual.

    :param population: Array of shape (population_size, num_genes).
    :param lower: Per-gene lower bound.
    :param upper: Per-gene upper bound.
    :param rng: Seeded generator.
    :param eta: Distribution index; higher means smaller perturbations.
    :param probability: Per-gene mutation rate. Defaults to 1/num_genes.
    :return: Mutated copy of the population.
    """
    _, num_genes = population.shape
    if probability is None:
        probability = 1.0 / num_genes

    span = np.where((upper - lower) < _EPSILON, _EPSILON, upper - lower)
    uniform = rng.random(size=population.shape)

    delta = np.where(
        uniform < 0.5,
        (2.0 * uniform) ** (1.0 / (eta + 1.0)) - 1.0,
        1.0 - (2.0 * (1.0 - uniform)) ** (1.0 / (eta + 1.0)),
    )

    mutation_mask = rng.random(size=population.shape) <= probability
    mutated = np.where(mutation_mask, population + delta * span, population)

    return np.clip(mutated, lower, upper)


def environmental_selection(objectives: np.ndarray, survivors: int) -> np.ndarray:
    """
    Keep the best `survivors` solutions, front by front.

    Whole fronts are admitted while they fit. The front that straddles the cut is
    admitted partially, ordered by descending crowding distance, which is how
    NSGA-II preserves a spread-out front instead of collapsing onto one corner.

    :param objectives: Array of shape (population_size, num_objectives), minimized.
    :param survivors: Number of solutions to retain.
    :return: Indices of the retained solutions.
    """
    selected: List[int] = []

    for front in fast_non_dominated_sort(objectives):
        if len(selected) + len(front) <= survivors:
            selected.extend(front)
            continue

        remaining = survivors - len(selected)
        if remaining > 0:
            distances = crowding_distance(objectives, front)
            # Descending crowding distance: the most isolated solutions survive.
            order = np.argsort(-distances, kind="stable")
            selected.extend(int(front[position]) for position in order[:remaining])
        break

    return np.array(selected, dtype=int)


def select_spread(objectives: np.ndarray, count: int) -> np.ndarray:
    """
    Pick a readable subset of a front that still spans its full extent.

    An unbounded archive is the right thing to measure progress against but the
    wrong thing to hand a reader: a thousand strategies is not a choice, it is a
    haystack. Selecting by crowding distance keeps the extremes, because they are
    the honest edges of what is achievable, and then fills in from the most
    isolated points inward, so the sample tracks the shape of the curve rather
    than bunching where solutions happen to be dense.

    :param objectives: Front objectives, shape (num_points, num_objectives).
    :param count: Maximum number of points to keep.
    :return: Indices into objectives, ordered as given.
    """
    num_points = objectives.shape[0]
    if count <= 0:
        return np.empty(0, dtype=int)
    if num_points <= count:
        return np.arange(num_points)

    distances = crowding_distance(objectives, list(range(num_points)))
    chosen = np.argsort(-distances, kind="stable")[:count]
    return np.sort(chosen)


def hypervolume(
    objectives: np.ndarray,
    reference: np.ndarray,
    samples: np.ndarray = None,
    box_volume: float = None,
) -> float:
    """
    Volume of objective space dominated by a front, bounded by a reference point.

    Hypervolume is the standard single-number quality measure for a front because
    it rewards convergence and spread together. Exact for one or two objectives via
    a sweep; estimated by Monte Carlo above that, where exact computation becomes
    expensive.

    For the Monte Carlo path the caller should pass a fixed `samples` array reused
    across a whole run. Re-drawing samples each call would make successive
    estimates differ by sampling noise as well as by real progress, which is
    enough to put visible dips in a curve that is supposed to be monotone.

    :param objectives: Array of shape (num_points, num_objectives), minimized.
    :param reference: Worst-case point that bounds the volume; must be dominated by the front.
    :param samples: Optional fixed sample points for the Monte Carlo path.
    :param box_volume: Volume of the box `samples` was drawn from. Required with `samples`.
    :return: The dominated hypervolume. Zero when no point beats the reference.
    """
    if objectives.size == 0:
        return 0.0

    # Only points strictly inside the reference box contribute.
    inside = np.all(objectives < reference, axis=1)
    points = objectives[inside]
    if points.shape[0] == 0:
        return 0.0

    num_objectives = points.shape[1]

    if num_objectives == 1:
        return float(reference[0] - np.min(points))

    if num_objectives == 2:
        # Sweep in ascending first objective, accumulating disjoint rectangles.
        order = np.argsort(points[:, 0], kind="stable")
        volume = 0.0
        best_second = reference[1]
        for index in order:
            if points[index, 1] < best_second:
                volume += (reference[0] - points[index, 0]) * (best_second - points[index, 1])
                best_second = points[index, 1]
        return float(volume)

    if samples is None:
        lower = np.min(points, axis=0)
        box_volume = float(np.prod(reference - lower))
        samples = np.random.default_rng(0).uniform(low=lower, high=reference, size=(8000, num_objectives))
    if box_volume is None:
        raise ValueError("box_volume must accompany a supplied samples array")
    if box_volume <= 0.0:
        return 0.0

    # A sample counts if at least one front point dominates it. Chunked over
    # samples so a large archive does not build a points-by-samples array at once.
    dominated_count = 0
    for start in range(0, samples.shape[0], 2048):
        block = samples[start : start + 2048]
        dominated_count += int(
            np.count_nonzero(np.any(np.all(points[:, None, :] <= block[None, :, :], axis=2), axis=0))
        )

    return float(box_volume * dominated_count / samples.shape[0])


def update_archive(
    archive_genes: np.ndarray,
    archive_objectives: np.ndarray,
    new_genes: np.ndarray,
    new_objectives: np.ndarray,
    decimals: int = 9,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Merge new solutions into an unbounded archive of non-dominated solutions.

    The archive exists because the population alone is not a reliable record of
    progress. Once the first front grows past the population size, NSGA-II's
    crowding truncation has to discard genuinely non-dominated solutions, so the
    population's hypervolume can fall from one generation to the next. Anything
    dropped from the archive, by contrast, was dominated by something that
    remains, so the region the archive dominates can only ever grow.

    :param archive_genes: Current archive decision vectors, shape (n, num_genes).
    :param archive_objectives: Their objectives, shape (n, num_objectives).
    :param new_genes: Candidate decision vectors to merge in.
    :param new_objectives: Their objectives.
    :param decimals: Rounding used to drop duplicate objective vectors.
    :return: Tuple of (archive genes, archive objectives) after the merge.
    """
    merged_genes = np.vstack([archive_genes, new_genes]) if archive_genes.size else new_genes
    merged_objectives = np.vstack([archive_objectives, new_objectives]) if archive_objectives.size else new_objectives

    # Drop exact duplicates first, so the O(N^2) sort below stays small.
    _, unique_indices = np.unique(np.round(merged_objectives, decimals), axis=0, return_index=True)
    unique_indices = np.sort(unique_indices)
    merged_genes = merged_genes[unique_indices]
    merged_objectives = merged_objectives[unique_indices]

    keep = non_dominated_mask(merged_objectives)
    return merged_genes[keep], merged_objectives[keep]


# The search loop legitimately juggles population, archive, bounds and history.
# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
def evolve(
    evaluate: Callable[[np.ndarray], np.ndarray],
    lower: np.ndarray,
    upper: np.ndarray,
    population_size: int = 60,
    generations: int = 40,
    seed: int = 0,
) -> Dict[str, np.ndarray]:
    """
    Run NSGA-II and return the archived Pareto front plus its convergence history.

    The returned front comes from the unbounded archive rather than the final
    population, so it is never worse than the population's own front and the
    reported hypervolume history is non-decreasing by construction.

    :param evaluate: Maps a population of shape (n, num_genes) to objectives of
        shape (n, num_objectives). Must be minimization-oriented.
    :param lower: Per-gene lower bound.
    :param upper: Per-gene upper bound.
    :param population_size: Number of individuals carried between generations.
    :param generations: Number of generations to run.
    :param seed: Seed for the generator, so a run reproduces exactly.
    :return: Dict with the archived front's decision vectors and objectives, the
        final population and its objectives, and hypervolume per generation.
    """
    rng = np.random.default_rng(seed)
    num_genes = lower.shape[0]

    population = rng.uniform(low=lower, high=upper, size=(population_size, num_genes))
    objectives = evaluate(population)

    # Fixed across the run so the history is comparable generation to generation.
    num_objectives = objectives.shape[1]
    reference = np.max(objectives, axis=0) + 1.0

    # For three or more objectives, fix the Monte Carlo sample set once. Reusing
    # the same points every generation is what makes the history exactly
    # non-decreasing instead of merely trending upward: a sample that is dominated
    # once stays dominated, because the archive's dominated region only grows.
    hypervolume_samples = None
    sample_box_volume = None
    if num_objectives > 2:
        sample_lower = np.min(objectives, axis=0)
        sample_box_volume = float(np.prod(reference - sample_lower))
        hypervolume_samples = rng.uniform(low=sample_lower, high=reference, size=(8000, num_objectives))

    archive_genes = np.empty((0, num_genes))
    archive_objectives = np.empty((0, num_objectives))
    archive_genes, archive_objectives = update_archive(archive_genes, archive_objectives, population, objectives)

    history: List[float] = []

    for _ in range(generations):
        ranks, crowding = rank_and_crowding(objectives)

        parent_indices_a = binary_tournament(ranks, crowding, population_size, rng)
        parent_indices_b = binary_tournament(ranks, crowding, population_size, rng)
        children = sbx_crossover(population[parent_indices_a], population[parent_indices_b], lower, upper, rng)
        children = polynomial_mutation(children, lower, upper, rng)

        # Elitist: parents and children compete for the next generation together,
        # so a good solution can never be lost to chance.
        combined = np.vstack([population, children])
        combined_objectives = np.vstack([objectives, evaluate(children)])

        keep = environmental_selection(combined_objectives, population_size)
        population = combined[keep]
        objectives = combined_objectives[keep]

        archive_genes, archive_objectives = update_archive(archive_genes, archive_objectives, population, objectives)
        history.append(hypervolume(archive_objectives, reference, hypervolume_samples, sample_box_volume))

    return {
        "front_genes": archive_genes,
        "front_objectives": archive_objectives,
        "population": population,
        "objectives": objectives,
        "hypervolume_history": np.array(history, dtype=float),
        "reference": reference,
    }
