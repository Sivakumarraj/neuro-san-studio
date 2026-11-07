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

import asyncio
from unittest import TestCase

from coded_tools.experimental.mdap_decomposer.neuro_san_solver import NeuroSanSolver
from tests.coded_tools.experimental.mdap_decomposer.scripted_discriminator_caller import ScriptedDiscriminatorCaller


class TestNeuroSanSolver(TestCase):
    """
    Tests for how NeuroSanSolver picks a voting rule. Each test runs one vote from
    make_voter() against a scripted discriminator, so the batching of the calls shows
    which rule ran: first_to_k asks for all its votes at once, first_to_ahead_by_k in rounds.
    """

    def _run_vote(
        self, solver: NeuroSanSolver, answers: list[str]
    ) -> tuple[list[int], int, ScriptedDiscriminatorCaller]:
        """
        Run one vote on two candidates with the solver's voter.

        :param solver: The solver whose voting rule is under test
        :param answers: The votes the discriminator returns, in call order
        :return: A tuple of (votes per candidate, winner index, the scripted caller)
        """
        caller = ScriptedDiscriminatorCaller(answers)
        voter = solver.make_voter("test", "discriminator", "candidates", caller)
        votes, winner_idx = asyncio.run(voter.vote("pick one", ["a", "b"]))
        return votes, winner_idx, caller

    def test_first_to_k_is_the_default(self) -> None:
        """With no voting_rule, all number_of_votes calls are made at once, as before."""
        votes, winner_idx, caller = self._run_vote(NeuroSanSolver(), ["1", "2", "1"])
        self.assertEqual(caller.round_sizes(), [3])
        self.assertEqual(winner_idx, 0)
        self.assertEqual(votes, [2, 1])

    def test_first_to_ahead_by_k_asks_in_rounds_until_one_candidate_leads(self) -> None:
        """With first_to_ahead_by_k and K = 2, a 1-1 split asks for 2 more votes, then stops."""
        solver = NeuroSanSolver(winning_vote_count=2, voting_rule="first_to_ahead_by_k")
        votes, winner_idx, caller = self._run_vote(solver, ["1", "2", "1", "1"])
        self.assertEqual(caller.round_sizes(), [2, 2])
        self.assertEqual(winner_idx, 0)
        self.assertEqual(votes, [3, 1])

    def test_max_votes_defaults_to_four_k_plus_one(self) -> None:
        """With K = 2 and votes that never pull ahead, the vote stops after 9 calls."""
        solver = NeuroSanSolver(winning_vote_count=2, voting_rule="first_to_ahead_by_k")
        with self.assertLogs(level="WARNING"):
            _, _, caller = self._run_vote(solver, ["1", "2"] * 5)
        self.assertEqual(caller.call_count(), 9)

    def test_max_votes_can_be_set(self) -> None:
        """An explicit max_votes caps the calls."""
        solver = NeuroSanSolver(winning_vote_count=2, voting_rule="first_to_ahead_by_k", max_votes=4)
        with self.assertLogs(level="WARNING"):
            _, _, caller = self._run_vote(solver, ["1", "2"] * 5)
        self.assertEqual(caller.call_count(), 4)

    def test_unknown_voting_rule_is_rejected(self) -> None:
        """An unknown rule is an error that names the rules there are, not a silent fallback."""
        with self.assertRaises(ValueError) as raised_error:
            NeuroSanSolver(voting_rule="majority")
        self.assertIn("first_to_k", str(raised_error.exception))
        self.assertIn("first_to_ahead_by_k", str(raised_error.exception))
