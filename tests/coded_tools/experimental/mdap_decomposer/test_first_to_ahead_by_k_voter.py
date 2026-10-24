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
Unit tests for FirstToAheadByKVoter: when it stops asking, how it sizes each round,
how it red-flags bad votes, and how it falls back when no candidate reaches the lead.
The discriminator is scripted, so every test knows exactly which vote each call returns,
and it records how the calls were batched into rounds.
"""

import asyncio
from unittest import TestCase

from coded_tools.experimental.mdap_decomposer.first_to_ahead_by_k_voter import FirstToAheadByKVoter
from tests.coded_tools.experimental.mdap_decomposer.scripted_discriminator_caller import ScriptedDiscriminatorCaller


class TestFirstToAheadByKVoter(TestCase):
    """
    Tests for FirstToAheadByKVoter.
    """

    def _run_vote(
        self, answers: list[str], candidates: list[str], lead_required: int = 2, max_votes: int = 9
    ) -> tuple[list[int], int, ScriptedDiscriminatorCaller]:
        """
        Run one vote against a scripted discriminator.

        :param answers: The votes the discriminator returns, in call order
        :param candidates: The candidates being voted on
        :param lead_required: K for the voter
        :param max_votes: The voter's call cap
        :return: A tuple of (votes per candidate, winner index, the scripted caller)
        """
        caller = ScriptedDiscriminatorCaller(answers)
        voter = FirstToAheadByKVoter(
            "test", "discriminator", "candidates", caller, lead_required=lead_required, max_votes=max_votes
        )
        votes, winner_idx = asyncio.run(voter.vote("pick one", candidates))
        return votes, winner_idx, caller

    def test_unanimous_votes_stop_after_one_round_of_lead_required_calls(self):
        """
        Three agreeing votes give a lead of 3, so one round of 3 calls decides.
        """
        votes, winner_idx, caller = self._run_vote(["2", "2", "2"], ["a", "b"], lead_required=3)
        self.assertEqual(votes, [0, 3])
        self.assertEqual(winner_idx, 1)
        self.assertEqual(caller.round_sizes(), [3])

    def test_contested_vote_keeps_sampling_until_one_candidate_leads(self):
        """
        Round 1 asks 2 votes and splits them; round 2 asks 2 more, both for the first candidate.
        """
        votes, winner_idx, caller = self._run_vote(["1", "2", "1", "1"], ["a", "b"])
        self.assertEqual(votes, [3, 1])
        self.assertEqual(winner_idx, 0)
        self.assertEqual(caller.round_sizes(), [2, 2])

    def test_each_round_asks_only_for_votes_that_could_decide(self):
        """
        With three candidates and a lead of 2 the rounds are 2, 2 and 1 votes:
        [1, 1, 0] has no lead, [2, 1, 1] leads by 1, and [3, 1, 1] leads by 2.
        """
        votes, winner_idx, caller = self._run_vote(["1", "2", "1", "3", "1"], ["a", "b", "c"])
        self.assertEqual(votes, [3, 1, 1])
        self.assertEqual(winner_idx, 0)
        self.assertEqual(caller.round_sizes(), [2, 2, 1])

    def test_stops_at_max_votes_and_falls_back_to_plurality(self):
        """
        With a lead of 3 and a cap of 5, round 2 is cut to the 2 calls left and the tally
        ends at [3, 2]: no lead of 3, so the plurality wins.
        """
        with self.assertLogs(level="WARNING"):
            votes, winner_idx, caller = self._run_vote(
                ["1", "2", "1", "2", "1"], ["a", "b"], lead_required=3, max_votes=5
            )
        self.assertEqual(votes, [3, 2])
        self.assertEqual(winner_idx, 0)
        self.assertEqual(caller.round_sizes(), [3, 2])

    def test_red_flagged_votes_are_logged_and_discarded_but_counted(self):
        """
        "abc" is malformed and "0" is out of range: both are logged, neither is tallied,
        and both use up a call toward max_votes.
        """
        with self.assertLogs(level="ERROR") as logs:
            votes, winner_idx, caller = self._run_vote(["abc", "0", "2", "2"], ["a", "b"], max_votes=4)
        self.assertEqual(len(logs.records), 2)
        self.assertEqual(votes, [0, 2])
        self.assertEqual(winner_idx, 1)
        self.assertEqual(caller.call_count(), 4)

    def test_no_valid_votes_falls_back_to_first_candidate(self):
        """
        When every vote is red-flagged, the tally stays at zero and the first candidate wins.
        """
        with self.assertLogs(level="WARNING"):
            votes, winner_idx, _ = self._run_vote(["x", "9"], ["a", "b"], max_votes=2)
        self.assertEqual(votes, [0, 0])
        self.assertEqual(winner_idx, 0)

    def test_single_candidate_wins_without_asking(self):
        """
        A lone candidate wins without a discriminator call.
        """
        votes, winner_idx, caller = self._run_vote([], ["only"])
        self.assertEqual(votes, [0])
        self.assertEqual(winner_idx, 0)
        self.assertEqual(caller.call_count(), 0)

    def test_empty_candidates_are_rejected(self):
        """
        Voting on no candidates is a caller error, reported rather than guessed at.
        """
        with self.assertRaises(ValueError):
            self._run_vote([], [])

    def test_invalid_settings_are_rejected(self):
        """
        A lead below 1, or a cap smaller than the lead, can never produce a decision.
        """
        caller = ScriptedDiscriminatorCaller([])
        with self.assertRaises(ValueError):
            FirstToAheadByKVoter("test", "discriminator", "candidates", caller, lead_required=0)
        with self.assertRaises(ValueError):
            FirstToAheadByKVoter("test", "discriminator", "candidates", caller, lead_required=3, max_votes=2)

    def test_discriminator_receives_problem_and_candidates(self):
        """
        Every call passes the problem and the candidates under the configured key.
        """
        _, _, caller = self._run_vote(["1", "1"], ["a", "b"])
        self.assertEqual(caller.first_call_args(), {"problem": "pick one", "candidates": ["a", "b"]})
