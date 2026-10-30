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

"""Exact two-sided sign test."""

from math import comb


class SignTest:  # pylint: disable=too-few-public-methods
    """
    Exact two-sided sign test on discordant pairs.

    When two networks run the same attempts, only the pairs where exactly one passed carry information. If the
    networks were equally good, each such pair would be a fair coin flip. The p-value is the chance of a split at
    least as lopsided as the one observed, in either direction.
    """

    @staticmethod
    def two_sided_p_value(first_only: int, second_only: int) -> float:
        """
        Return the exact two-sided p-value for a split of discordant pairs.

        :param first_only: Pairs where only the first network passed.
        :param second_only: Pairs where only the second network passed.
        :return: The p-value, capped at 1.0. With no discordant pairs there is no evidence either way, so 1.0.
        :raises ValueError: If either count is negative.
        """
        if first_only < 0 or second_only < 0:
            raise ValueError(f"Pair counts must not be negative, got {first_only} and {second_only}.")
        discordant = first_only + second_only
        if discordant == 0:
            return 1.0
        smaller = min(first_only, second_only)
        tail = 0
        for count in range(smaller + 1):
            tail += comb(discordant, count)
        return min(1.0, 2 * tail / 2**discordant)
