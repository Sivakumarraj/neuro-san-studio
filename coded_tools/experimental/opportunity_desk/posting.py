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


# A data-only holder, normalized across providers by BoardParser.
# pylint: disable=too-many-instance-attributes
@dataclass(frozen=True)
class Posting:
    """
    One opening read from a public board: a role from a careers board, or an open
    issue from a repository the profile tracks for contributions.
    """

    # Stable across scans, so the store can tell a new posting from one already seen:
    # "<provider>:<board or repo>:<the provider's own id>".
    posting_id: str
    # "role" for a careers-board posting, "contribution" for a repository issue.
    kind: str
    # "greenhouse", "lever", "ashby" or "github".
    source: str
    title: str
    company: str
    location: str
    url: str
    # Plain text, HTML already stripped.
    description: str
    # ISO 8601 when the provider gives one, otherwise empty.
    posted_at: str
