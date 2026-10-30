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

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

from coded_tools.experimental.opportunity_desk.desk_profile import EXAMPLE_PROFILE
from coded_tools.experimental.opportunity_desk.desk_profile import PROFILE_ENV
from coded_tools.experimental.opportunity_desk.desk_store import DATA_DIR_ENV


class DeskTestEnvironment:
    """
    A throwaway profile and data directory for one test, wired in through the same
    environment variables production uses, so the tools under test run unmodified.

    Use as a context manager. The profile starts from the bundled example and takes
    the given overrides on top.
    """

    def __init__(self, **overrides: Any):
        """
        :param overrides: Top-level profile keys to replace in the example profile.
        """
        with open(EXAMPLE_PROFILE, encoding="utf-8") as example:
            self.profile: dict[str, Any] = json.load(example) | overrides
        self._directory: tempfile.TemporaryDirectory | None = None
        self._patch: Any = None
        self.data_dir: str = ""

    def __enter__(self) -> "DeskTestEnvironment":
        """
        :return: This environment, with the profile written and the variables set.
        """
        self._directory = tempfile.TemporaryDirectory()
        root: Path = Path(self._directory.name)
        profile_path: Path = root / "profile.json"
        profile_path.write_text(json.dumps(self.profile), encoding="utf-8")
        self.data_dir = str(root / "data")
        self._patch = mock.patch.dict(os.environ, {PROFILE_ENV: str(profile_path), DATA_DIR_ENV: self.data_dir})
        self._patch.start()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        """
        Restore the environment and delete the directory.

        :param exc_info: Ignored; exceptions propagate.
        """
        self._patch.stop()
        self._directory.cleanup()
