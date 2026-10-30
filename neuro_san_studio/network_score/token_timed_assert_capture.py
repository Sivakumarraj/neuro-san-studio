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

"""Assert capture that also keeps the token accounting of one fixture attempt."""

from typing import Any

from neuro_san.test.driver.timed_assert_capture import TimedAssertCapture


class TokenTimedAssertCapture(TimedAssertCapture):
    """
    A TimedAssertCapture that sums the token accounting of every interaction in one attempt.

    Neuro SAN's driver gives each attempt its own capture and uses it from one worker thread only, so the running
    totals need no lock.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize the capture with no token accounting seen yet.

        :param args: Positional arguments for TimedAssertCapture.
        :param kwargs: Keyword arguments for TimedAssertCapture.
        """
        super().__init__(*args, **kwargs)
        self._total_tokens: int | None = None
        self._total_cost: float | None = None

    def add_token_accounting(self, token_accounting: dict[str, Any] | None) -> None:
        """
        Add one interaction's final token accounting to the attempt totals.

        :param token_accounting: The accounting dictionary from the message processor, or `None` when the server
            sent none.
        """
        if not token_accounting:
            return
        self._total_tokens = (self._total_tokens or 0) + int(token_accounting.get("total_tokens", 0))
        self._total_cost = (self._total_cost or 0.0) + float(token_accounting.get("total_cost", 0.0))

    def get_total_tokens(self) -> int | None:
        """
        Return the tokens used by this attempt.

        :return: The summed total tokens, or `None` when no interaction reported token accounting.
        """
        return self._total_tokens

    def get_total_cost(self) -> float | None:
        """
        Return the cost of this attempt in US dollars.

        :return: The summed total cost, or `None` when no interaction reported token accounting.
        """
        return self._total_cost
