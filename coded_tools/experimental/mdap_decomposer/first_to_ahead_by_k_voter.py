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

import logging
from asyncio import Future
from asyncio import gather
from typing import Any

from coded_tools.experimental.mdap_decomposer.voter import Voter
from neuro_san_studio.coded_tools.agent_caller import AgentCaller


# pylint: disable=too-few-public-methods
class FirstToAheadByKVoter(Voter):
    """
    Voter for the first-to-ahead-by-K rule of the MAKER paper (https://arxiv.org/abs/2511.09030):
    keep asking the discriminator until one candidate has K more votes than any other candidate.

    Unlike FirstToKVoter, which asks for all of its votes at once, this voter asks in rounds.
    Each round asks only for as many votes as could still end the vote, so a clear decision
    stops after K calls and a contested one keeps sampling, up to max_votes calls.

    A malformed or out-of-range vote is red-flagged: logged and discarded. It still counts
    toward max_votes, because it cost a discriminator call.
    """

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    def __init__(
        self,
        source: str,
        discriminator_name: str,
        candidates_key: str,
        discriminator_caller: AgentCaller,
        lead_required: int = 2,
        max_votes: int = 9,
    ):
        """
        Constructor.

        :param source: A label that prefixes every log message
        :param discriminator_name: The name of the discriminator agent, for log messages
        :param candidates_key: The tool_args key under which the candidates are passed
        :param discriminator_caller: The AgentCaller that asks the discriminator for one vote
        :param lead_required: K, the number of votes by which the winner must lead every other candidate
        :param max_votes: The most discriminator calls this voter makes for one decision
        """
        if lead_required < 1:
            raise ValueError(f"lead_required must be at least 1, got {lead_required}")
        if max_votes < lead_required:
            raise ValueError(f"max_votes ({max_votes}) must be at least lead_required ({lead_required})")

        self.source: str = source
        self.discriminator_name: str = discriminator_name
        self.candidates_key: str = candidates_key
        self.discriminator_caller: AgentCaller = discriminator_caller
        self.lead_required: int = lead_required
        self.max_votes: int = max_votes

    async def vote(self, problem: str, candidates: list[str]) -> tuple[list[int], int]:
        """
        Ask the discriminator in rounds until one candidate leads by lead_required votes,
        or until max_votes calls have been made. Overrides Voter.vote().

        :param problem: The problem to be solved
        :param candidates: The candidate solutions
        :return: A tuple of (list of number of votes per candidate, winner index)
        """
        if not candidates:
            raise ValueError(f"{self.source} cannot vote on an empty list of candidates")

        votes: list[int] = [0] * len(candidates)
        if len(candidates) == 1:
            # A lone candidate wins outright; asking the discriminator would only cost calls.
            logging.info("%s single candidate wins without a vote", self.source)
            return votes, 0

        tool_args: dict[str, Any] = {"problem": problem, self.candidates_key: candidates}
        logging.info("%s %s votes on %d candidates", self.source, self.discriminator_name, len(candidates))

        calls_made: int = 0
        winner_idx: int | None = None
        while winner_idx is None and calls_made < self.max_votes:
            round_size: int = min(self._votes_that_could_decide(votes), self.max_votes - calls_made)
            coroutines: list[Future] = []
            for _ in range(round_size):
                coroutines.append(self.discriminator_caller.call_agent(tool_args))
            results: list[str] = await gather(*coroutines)
            calls_made += round_size

            for vote_txt in results:
                idx: int | None = self._parse_vote(vote_txt, len(candidates))
                if idx is not None:
                    votes[idx] += 1
            logging.info("%s tally after %d calls: %s", self.source, calls_made, str(votes))
            winner_idx = self._leader(votes)

        if winner_idx is None:
            # No candidate reached the lead within max_votes. Fall back to the plurality,
            # breaking ties toward the lowest index, as FirstToKVoter does.
            winner_idx = votes.index(max(votes))
            logging.warning(
                "%s no candidate led by %d within %d calls; plurality winner: %d",
                self.source,
                self.lead_required,
                self.max_votes,
                winner_idx + 1,
            )

        logging.info("%s final winner: %d -> %s", self.source, winner_idx + 1, candidates[winner_idx])
        return votes, winner_idx

    def _votes_that_could_decide(self, votes: list[int]) -> int:
        """
        The fewest further votes that could end the vote: if every one of them goes to the
        current leader, the leader reaches the required lead. Asking for more in one round
        could waste calls on a vote that is already decided.

        :param votes: The current tally, one entry per candidate (at least two)
        :return: The number of votes to ask for in the next round, at least 1
        """
        ranked: list[int] = sorted(votes, reverse=True)
        lead: int = ranked[0] - ranked[1]
        return max(self.lead_required - lead, 1)

    def _leader(self, votes: list[int]) -> int | None:
        """
        :param votes: The current tally, one entry per candidate (at least two)
        :return: The index of the candidate that leads every other by lead_required votes, or None
        """
        ranked: list[int] = sorted(votes, reverse=True)
        if ranked[0] - ranked[1] >= self.lead_required:
            return votes.index(ranked[0])
        return None

    def _parse_vote(self, vote_txt: str, candidate_count: int) -> int | None:
        """
        Red-flag filter for one discriminator answer, which should be a 1-based candidate number.

        :param vote_txt: The raw answer from the discriminator
        :param candidate_count: The number of candidates being voted on
        :return: The 0-based index of the candidate voted for, or None if the vote is red-flagged
        """
        logging.info("%s raw vote: %s", self.source, vote_txt)
        try:
            idx: int = int(vote_txt) - 1
        except (TypeError, ValueError):
            logging.error("%s malformed vote ignored: %s", self.source, vote_txt)
            return None

        if not 0 <= idx < candidate_count:
            logging.error(
                "%s out-of-range vote ignored: %s (expected 1 to %d)", self.source, vote_txt, candidate_count
            )
            return None
        return idx
