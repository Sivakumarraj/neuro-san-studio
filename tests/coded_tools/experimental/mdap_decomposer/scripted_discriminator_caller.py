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
from typing import Any

from neuro_san_studio.coded_tools.agent_caller import AgentCaller


class ScriptedDiscriminatorCaller(AgentCaller):
    """
    AgentCaller test double that answers each call with the next scripted vote.

    It also records how the calls were batched: calls made together (for example through
    asyncio.gather) are all in flight at once, so each burst of concurrent calls is one round.
    """

    def __init__(self, answers: list[str]):
        """
        Constructor.

        :param answers: The answers to return, in call order
        """
        self._answers: list[str] = list(answers)
        self._calls: list[dict[str, Any]] = []
        self._round_sizes: list[int] = []
        self._in_flight: int = 0

    def get_name(self) -> str:
        """
        Get the name of the agent. Overrides AgentCaller.get_name().

        :return: The name of the agent this caller stands in for
        """
        return "scripted_discriminator"

    async def call_agent(self, tool_args: dict[str, Any], sly_data: dict[str, Any] = None) -> str:
        """
        Return the next scripted answer. Overrides AgentCaller.call_agent().

        :param tool_args: The arguments the voter passes to the discriminator
        :param sly_data: Not used by a scripted vote
        :return: The next scripted answer
        """
        if len(self._calls) >= len(self._answers):
            raise AssertionError(
                f"Discriminator called {len(self._calls) + 1} times; only {len(self._answers)} answers scripted"
            )
        if self._in_flight == 0:
            self._round_sizes.append(0)
        self._in_flight += 1
        self._round_sizes[-1] += 1
        self._calls.append(tool_args)
        answer: str = self._answers[len(self._calls) - 1]

        # Yield once so that every call gathered into the same round starts before any finishes.
        await asyncio.sleep(0)
        self._in_flight -= 1
        return answer

    def call_count(self) -> int:
        """
        :return: How many times the discriminator was called
        """
        return len(self._calls)

    def round_sizes(self) -> list[int]:
        """
        :return: The number of calls in each burst of concurrent calls, in order
        """
        return list(self._round_sizes)

    def first_call_args(self) -> dict[str, Any]:
        """
        :return: The tool_args of the first call
        """
        return self._calls[0]
