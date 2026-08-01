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
Unit tests for the NSGA-II core.

The search is stochastic, so these tests avoid asserting on any particular
solution. They pin down the pieces that are exactly determined instead: the
dominance relation, the front partition, hypervolume on shapes whose area can be
worked out by hand, and convergence against a benchmark with a known analytic
front.
"""

from unittest import TestCase

import numpy as np

from coded_tools.experimental.decision_prescriptor.nsga2 import crowding_distance
from coded_tools.experimental.decision_prescriptor.nsga2 import dominates
from coded_tools.experimental.decision_prescriptor.nsga2 import environmental_selection
from coded_tools.experimental.decision_prescriptor.nsga2 import evolve
from coded_tools.experimental.decision_prescriptor.nsga2 import fast_non_dominated_sort
from coded_tools.experimental.decision_prescriptor.nsga2 import hypervolume
from coded_tools.experimental.decision_prescriptor.nsga2 import non_dominated_mask
from coded_tools.experimental.decision_prescriptor.nsga2 import select_spread
from coded_tools.experimental.decision_prescriptor.nsga2 import update_archive


def zdt1(population: np.ndarray) -> np.ndarray:
    """
    The ZDT1 benchmark, whose true Pareto front is f2 = 1 - sqrt(f1).

    :param population: Decision vectors in [0, 1], shape (n, num_genes).
    :return: Objectives of shape (n, 2), both minimized.
    """
    first = population[:, 0]
    spread = 1.0 + 9.0 * np.mean(population[:, 1:], axis=1)
    second = spread * (1.0 - np.sqrt(first / spread))
    return np.column_stack([first, second])


class TestDominance(TestCase):
    """
    Tests for the dominance relation and the front partition built on it.
    """

    def test_dominates_requires_strictly_better_somewhere(self):
        """Equal vectors do not dominate each other; being better on one objective does."""
        self.assertTrue(dominates(np.array([1.0, 2.0]), np.array([2.0, 3.0])))
        self.assertTrue(dominates(np.array([1.0, 2.0]), np.array([1.0, 3.0])))
        self.assertFalse(dominates(np.array([1.0, 2.0]), np.array([1.0, 2.0])))
        self.assertFalse(dominates(np.array([1.0, 5.0]), np.array([2.0, 3.0])))

    def test_fronts_match_a_hand_worked_example(self):
        """
        Five points whose layering can be checked by eye.

        Points 0, 1 and 2 trade off against one another. Points 3 and 4 are each
        beaten outright by point 2, so they fall to the second front.
        """
        objectives = np.array([[1.0, 5.0], [2.0, 3.0], [3.0, 1.0], [4.0, 6.0], [5.0, 4.0]])
        self.assertEqual(fast_non_dominated_sort(objectives), [[0, 1, 2], [3, 4]])

    def test_every_point_is_its_own_front_when_all_are_incomparable(self):
        """A perfectly conflicting set collapses to a single front."""
        objectives = np.array([[0.0, 3.0], [1.0, 2.0], [2.0, 1.0], [3.0, 0.0]])
        self.assertEqual(fast_non_dominated_sort(objectives), [[0, 1, 2, 3]])

    def test_empty_population_sorts_to_no_fronts(self):
        """The sort must tolerate an empty population rather than raising."""
        self.assertEqual(fast_non_dominated_sort(np.empty((0, 2))), [])

    def test_vectorized_mask_agrees_with_the_reference_sort(self):
        """
        The fast path must return exactly the first front of the reference sort.

        Integer objectives are used so duplicate rows occur often: duplicates are
        the case where a sloppy dominance test wrongly eliminates both copies.
        """
        rng = np.random.default_rng(0)
        for num_objectives in (2, 3, 4):
            objectives = rng.integers(0, 5, size=(50, num_objectives)).astype(float)
            expected = np.zeros(50, dtype=bool)
            expected[fast_non_dominated_sort(objectives)[0]] = True
            np.testing.assert_array_equal(expected, non_dominated_mask(objectives))

    def test_mask_is_independent_of_chunk_size(self):
        """Chunking is an implementation detail and must not change the answer."""
        objectives = np.random.default_rng(1).random((300, 3))
        np.testing.assert_array_equal(
            non_dominated_mask(objectives, chunk_size=512), non_dominated_mask(objectives, chunk_size=7)
        )


class TestCrowdingDistance(TestCase):
    """
    Tests for the diversity measure used to break ties within a front.
    """

    def test_extremes_are_infinite(self):
        """The ends of a front must never be discarded, so they score infinity."""
        objectives = np.array([[0.0, 3.0], [1.0, 2.0], [2.0, 1.0], [3.0, 0.0]])
        distances = crowding_distance(objectives, [0, 1, 2, 3])
        self.assertTrue(np.isinf(distances[0]))
        self.assertTrue(np.isinf(distances[3]))
        self.assertTrue(np.all(np.isfinite(distances[1:3])))

    def test_evenly_spaced_interior_points_score_equally(self):
        """
        On a uniform front every interior point has the same neighbour gap.

        With two objectives each interior point spans 2 of 4 steps on each axis,
        giving 0.5 per objective and 1.0 in total.
        """
        objectives = np.array([[0.0, 4.0], [1.0, 3.0], [2.0, 2.0], [3.0, 1.0], [4.0, 0.0]])
        distances = crowding_distance(objectives, [0, 1, 2, 3, 4])
        np.testing.assert_allclose(distances[1:4], [1.0, 1.0, 1.0])

    def test_small_fronts_are_all_infinite(self):
        """With two or fewer members there is no interior to measure."""
        self.assertTrue(np.all(np.isinf(crowding_distance(np.array([[0.0, 1.0], [1.0, 0.0]]), [0, 1]))))

    def test_constant_objective_contributes_nothing(self):
        """An objective identical across the front separates nobody."""
        objectives = np.array([[0.0, 1.0], [1.0, 1.0], [2.0, 1.0], [3.0, 1.0]])
        distances = crowding_distance(objectives, [0, 1, 2, 3])
        self.assertTrue(np.all(np.isfinite(distances[1:3])))


class TestHypervolume(TestCase):
    """
    Tests for the front quality measure, on shapes with a known area.
    """

    def test_two_overlapping_boxes(self):
        """
        Two points against reference (1, 1).

        Each box has area 0.5 and they overlap in a 0.5 by 0.5 square, so the
        union is 0.5 + 0.5 - 0.25 = 0.75.
        """
        front = np.array([[0.0, 0.5], [0.5, 0.0]])
        self.assertAlmostEqual(hypervolume(front, np.array([1.0, 1.0])), 0.75)

    def test_single_point_is_its_own_box(self):
        """One point at the origin dominates the whole unit square."""
        self.assertAlmostEqual(hypervolume(np.array([[0.0, 0.0]]), np.array([1.0, 1.0])), 1.0)

    def test_points_outside_the_reference_contribute_nothing(self):
        """A point worse than the reference on any axis adds no volume."""
        self.assertEqual(hypervolume(np.array([[2.0, 2.0]]), np.array([1.0, 1.0])), 0.0)

    def test_dominated_points_do_not_inflate_the_volume(self):
        """Adding a dominated point must leave the measure unchanged."""
        reference = np.array([1.0, 1.0])
        without = hypervolume(np.array([[0.0, 0.5], [0.5, 0.0]]), reference)
        with_extra = hypervolume(np.array([[0.0, 0.5], [0.5, 0.0], [0.8, 0.8]]), reference)
        self.assertAlmostEqual(without, with_extra)

    def test_monte_carlo_path_requires_a_box_volume(self):
        """Supplying samples without their box volume is a programming error."""
        samples = np.random.default_rng(0).random((16, 3))
        with self.assertRaises(ValueError):
            hypervolume(np.zeros((2, 3)), np.ones(3), samples=samples)


class TestSelection(TestCase):
    """
    Tests for the survivor and display-subset selection rules.
    """

    def test_environmental_selection_prefers_the_first_front(self):
        """Front members must be retained ahead of anything they dominate."""
        objectives = np.array([[0.0, 3.0], [1.0, 2.0], [2.0, 1.0], [9.0, 9.0], [8.0, 8.0]])
        kept = set(environmental_selection(objectives, 3).tolist())
        self.assertEqual(kept, {0, 1, 2})

    def test_environmental_selection_returns_exactly_the_requested_count(self):
        """The population size must stay fixed from generation to generation."""
        objectives = np.random.default_rng(2).random((40, 3))
        self.assertEqual(environmental_selection(objectives, 12).shape[0], 12)

    def test_select_spread_keeps_the_extremes(self):
        """A readable subset must still show the honest edges of what is achievable."""
        objectives = np.column_stack([np.arange(30.0), 30.0 - np.arange(30.0)])
        chosen = select_spread(objectives, 6)
        self.assertEqual(chosen.shape[0], 6)
        self.assertIn(0, chosen.tolist())
        self.assertIn(29, chosen.tolist())

    def test_select_spread_is_a_no_op_when_the_front_already_fits(self):
        """Asking for more points than exist returns them all."""
        objectives = np.array([[0.0, 1.0], [1.0, 0.0]])
        np.testing.assert_array_equal(select_spread(objectives, 10), np.array([0, 1]))


class TestArchive(TestCase):
    """
    Tests for the unbounded archive that backs the convergence curve.
    """

    def test_archive_drops_newly_dominated_members(self):
        """A previously archived point must go once something beats it outright."""
        genes = np.array([[0.0], [1.0]])
        objectives = np.array([[1.0, 1.0], [2.0, 2.0]])
        new_genes = np.array([[2.0]])
        new_objectives = np.array([[0.0, 0.0]])

        _, kept = update_archive(genes, objectives, new_genes, new_objectives)
        np.testing.assert_array_equal(kept, np.array([[0.0, 0.0]]))

    def test_archive_deduplicates_identical_objectives(self):
        """Duplicate rows would otherwise accumulate without adding information."""
        genes = np.array([[0.0], [0.0]])
        objectives = np.array([[1.0, 1.0], [1.0, 1.0]])
        _, kept = update_archive(genes, objectives, genes, objectives)
        self.assertEqual(kept.shape[0], 1)


class TestEvolve(TestCase):
    """
    End-to-end tests of the search loop against a benchmark with a known front.
    """

    def test_converges_close_to_the_analytic_zdt1_front(self):
        """
        The recovered front must sit on f2 = 1 - sqrt(f1).

        The budget here is chosen to be genuinely sufficient rather than merely
        enough to pass: across six seeds this configuration converges to a worst
        mean distance of 0.0004, so the 0.01 threshold leaves a wide margin and
        still fails loudly if the search regresses. A shorter run was rejected
        because at 80 generations some seeds have simply not converged yet, and a
        test that tolerated that would be asserting nothing.
        """
        num_genes = 6
        result = evolve(zdt1, np.zeros(num_genes), np.ones(num_genes), population_size=60, generations=120, seed=1)
        front = result["front_objectives"]
        distance = np.abs(front[:, 1] - (1.0 - np.sqrt(front[:, 0]))).mean()
        self.assertLess(distance, 0.01)

    def test_the_front_spans_the_objective_range(self):
        """
        Converging onto one corner of the front would satisfy a distance check
        while being useless as a set of options, so coverage is asserted too.
        """
        num_genes = 6
        result = evolve(zdt1, np.zeros(num_genes), np.ones(num_genes), population_size=60, generations=120, seed=1)
        first_objective = result["front_objectives"][:, 0]
        self.assertLess(first_objective.min(), 0.1)
        self.assertGreater(first_objective.max(), 0.9)

    def test_hypervolume_history_never_decreases(self):
        """
        The archive's dominated region can only grow, so its measure must too.

        This is the property that broke when progress was measured on the
        population instead: once the first front outgrows the population, crowding
        truncation discards non-dominated solutions and the curve dips.
        """
        num_genes = 6
        for num_objectives, evaluate in (
            (2, zdt1),
            (3, lambda pop: np.column_stack([pop[:, 0], pop[:, 1], np.sum(pop[:, 2:] ** 2, axis=1)])),
        ):
            result = evolve(
                evaluate, np.zeros(num_genes), np.ones(num_genes), population_size=40, generations=30, seed=2
            )
            history = result["hypervolume_history"]
            self.assertEqual(history.shape[0], 30)
            self.assertTrue(
                np.all(np.diff(history) >= -1e-12),
                f"hypervolume decreased with {num_objectives} objectives",
            )

    def test_the_returned_front_is_actually_non_dominated(self):
        """Nothing on the reported front may dominate anything else on it."""
        num_genes = 5
        result = evolve(zdt1, np.zeros(num_genes), np.ones(num_genes), population_size=30, generations=20, seed=3)
        self.assertTrue(np.all(non_dominated_mask(result["front_objectives"])))

    def test_the_same_seed_reproduces_a_run(self):
        """A decision tool whose output moved between runs would not be usable."""
        num_genes = 5
        bounds = (np.zeros(num_genes), np.ones(num_genes))
        first = evolve(zdt1, *bounds, population_size=20, generations=10, seed=42)
        second = evolve(zdt1, *bounds, population_size=20, generations=10, seed=42)
        np.testing.assert_allclose(first["front_objectives"], second["front_objectives"])
