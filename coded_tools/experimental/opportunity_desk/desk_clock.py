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

from datetime import date
from datetime import datetime
from datetime import timezone


class DeskClock:
    """
    The one place the opportunity desk tools read the time, so tests can pin it.
    """

    @staticmethod
    def now_iso() -> str:
        """
        :return: The current UTC time, ISO 8601 to the second.
        """
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def today() -> date:
        """
        :return: Today's UTC date.
        """
        return datetime.now(timezone.utc).date()
