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

from dataclasses import dataclass


@dataclass(frozen=True)
class FitResult:
    """
    How well one posting fits the profile, as decided by FitAssessor. Data only.

    The score ranks; eligible gates. A posting that fails a hard requirement (too
    many years asked, the wrong graduation year, an excluded term) keeps its score
    for the record but is never put in front of the user as a match.
    """

    # 0 to 100.
    score: int
    eligible: bool
    # Plain-language reasons, so every number the user sees can be traced back.
    reasons: tuple[str, ...]
