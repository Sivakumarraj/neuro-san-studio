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

"""Input values for one `ns score` run."""

from typing import NamedTuple


class ScoreOptions(NamedTuple):
    """Carry the user-selected values for one `ns score` run."""

    DEFAULT_REPEATS = 3

    hocon_file: str
    compare_hocon_file: str | None = None
    repeats: int = DEFAULT_REPEATS
    only_fixtures: list[str] | None = None
    output: str | None = None
