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

"""Tests for the `ns score` worker."""

import json
import os
import tempfile
from unittest import TestCase
from unittest.mock import patch

from neuro_san_studio.network_score.attempt_result import AttemptResult
from neuro_san_studio.network_score.network_score_runner import NetworkScoreRunner
from neuro_san_studio.network_score.score_options import ScoreOptions


class TestNetworkScoreRunner(TestCase):
    """Verify input checks, fixture selection, the comparison path and the JSON output, with no LLM calls."""

    def setUp(self) -> None:
        """Create a project folder with two networks and two fixtures, and work inside it."""
        self._original_directory = os.getcwd()
        self._project = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        os.chdir(self._project.name)
        os.makedirs(os.path.join("registries", "basic"))
        for network in ("old", "new"):
            with open(os.path.join("registries", "basic", f"{network}.hocon"), "w", encoding="utf-8") as hocon:
                hocon.write("{}")
        os.makedirs(os.path.join("tests", "fixtures", "basic", "old"))
        for fixture in ("b.hocon", "a.hocon"):
            with open(os.path.join("tests", "fixtures", "basic", "old", fixture), "w", encoding="utf-8") as hocon:
                hocon.write("{}")

    def tearDown(self) -> None:
        """Return to the original folder and remove the project folder."""
        os.chdir(self._original_directory)
        self._project.cleanup()

    def test_network_name_drops_the_extension(self) -> None:
        """The runtime name is the registries-relative path without `.hocon`."""
        self.assertEqual("industry/intranet_agents", NetworkScoreRunner.network_name("industry/intranet_agents.hocon"))

    def test_fixtures_are_sorted_or_selected(self) -> None:
        """All fixtures run in name order, or only the requested ones in the requested order."""
        all_paths = NetworkScoreRunner(ScoreOptions(hocon_file="basic/old.hocon")).fixture_paths("basic/old")
        selected = NetworkScoreRunner(
            ScoreOptions(hocon_file="basic/old.hocon", only_fixtures=["b.hocon"])
        ).fixture_paths("basic/old")

        self.assertEqual(["a.hocon", "b.hocon"], [os.path.basename(path) for path in all_paths])
        self.assertEqual(["b.hocon"], [os.path.basename(path) for path in selected])

    def test_missing_requested_fixture_is_an_error(self) -> None:
        """A requested fixture that does not exist stops the run with a logged error."""
        runner = NetworkScoreRunner(ScoreOptions(hocon_file="basic/old.hocon", only_fixtures=["missing.hocon"]))

        with self.assertLogs("neuro_san_studio.network_score.network_score_runner", level="ERROR"):
            self.assertEqual(NetworkScoreRunner.EXIT_ERROR, runner.run())

    def test_missing_network_file_is_an_error(self) -> None:
        """A compare network that is not in registries/ stops the run before any fixture runs."""
        runner = NetworkScoreRunner(ScoreOptions(hocon_file="basic/old.hocon", compare_hocon_file="basic/gone.hocon"))

        with self.assertLogs("neuro_san_studio.network_score.network_score_runner", level="ERROR"):
            self.assertEqual(NetworkScoreRunner.EXIT_ERROR, runner.run())

    def test_compare_runs_both_networks_on_the_first_networks_fixtures(self) -> None:
        """Both networks run the same fixtures, and the JSON report carries both scorecards and the comparison."""
        output = os.path.join(self._project.name, "score.json")
        runner = NetworkScoreRunner(
            ScoreOptions(hocon_file="basic/old.hocon", compare_hocon_file="basic/new.hocon", repeats=1, output=output)
        )
        with (
            patch("neuro_san_studio.network_score.network_score_runner.FixtureScorer") as scorer_class,
            patch("builtins.print"),
        ):
            scorer_class.return_value.score.return_value = [
                AttemptResult(fixture="a.hocon", attempt=0, passed=True, total_tokens=10, total_cost=0.001)
            ]

            exit_code = runner.run()

        self.assertEqual(NetworkScoreRunner.EXIT_OK, exit_code)
        agents = [call.kwargs.get("agent") for call in scorer_class.call_args_list]
        self.assertEqual(["basic/old", "basic/old", "basic/new", "basic/new"], agents)
        with open(output, encoding="utf-8") as report_file:
            report = json.load(report_file)
        self.assertEqual(2, len(report.get("scorecards")))
        self.assertEqual(1.0, report.get("comparison").get("sign_test_p_value"))
