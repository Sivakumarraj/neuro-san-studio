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

"""One scored attempt of one fixture."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AttemptResult:
    """
    The outcome and spend of one fixture attempt.

    Token and cost fields are `None` when the attempt reported no token accounting, for example when it timed out
    before the final message. They are never guessed as zero.
    """

    fixture: str
    attempt: int
    passed: bool
    total_tokens: int | None
    total_cost: float | None
