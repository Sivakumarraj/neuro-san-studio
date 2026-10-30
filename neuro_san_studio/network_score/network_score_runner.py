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

"""Worker process for `ns score`: run the fixtures, print the report and write the JSON."""

import glob
import json
import logging
import os
import sys
from typing import Any

from neuro_san_studio.network_score.attempt_result import AttemptResult
from neuro_san_studio.network_score.fixture_scorer import FixtureScorer
from neuro_san_studio.network_score.network_scorecard import NetworkScorecard
from neuro_san_studio.network_score.paired_comparison import PairedComparison
from neuro_san_studio.network_score.score_options import ScoreOptions
from neuro_san_studio.network_score.score_report_formatter import ScoreReportFormatter

logger = logging.getLogger(__name__)


class NetworkScoreRunner:
    """
    Score one network, or compare two, on the first network's fixtures.

    `ns score` starts this in a child process with the project's direct-test environment, the same way
    `ns consultant` starts its worker (see NeuroSanStudioCli._run_consultant), so the caller's environment is
    left alone. Fixtures run one after another; each fixture's attempts run in parallel inside Neuro SAN's driver.
    """

    EXIT_OK = 0
    EXIT_ERROR = 1
    DEFAULT_FIXTURE_ROOT = os.path.join("tests", "fixtures")
    REGISTRY_ROOT = "registries"

    def __init__(self, options: ScoreOptions, fixture_root: str | None = None) -> None:
        """
        Initialize the runner.

        :param options: The parsed `ns score` options.
        :param fixture_root: The directory holding one fixture folder per network.
        """
        self._options = options
        self._fixture_root = fixture_root or self.DEFAULT_FIXTURE_ROOT

    @staticmethod
    def network_name(hocon_file: str) -> str:
        """
        Return the runtime network name for a registries-relative HOCON file.

        :param hocon_file: A path such as `industry/intranet_agents.hocon`.
        :return: The name used by `ns chat` and fixtures, such as `industry/intranet_agents`.
        """
        return os.path.splitext(hocon_file)[0]

    def run(self) -> int:
        """
        Run the scoring, print the report and write the JSON when asked.

        :return: EXIT_OK on success, EXIT_ERROR when an input is missing or the output cannot be written.
        """
        baseline_name = self.network_name(self._options.hocon_file)
        networks = [self._options.hocon_file]
        if self._options.compare_hocon_file:
            networks.append(self._options.compare_hocon_file)
        for hocon_file in networks:
            if not os.path.isfile(os.path.join(self.REGISTRY_ROOT, hocon_file)):
                logger.error("Network file not found: %s", os.path.join(self.REGISTRY_ROOT, hocon_file))
                return self.EXIT_ERROR
        fixture_paths = self.fixture_paths(baseline_name)
        if not fixture_paths:
            logger.error("No fixtures to run for %s under %s", baseline_name, self._fixture_root)
            return self.EXIT_ERROR

        scorecards = [self.score_network(baseline_name, fixture_paths)]
        if self._options.compare_hocon_file:
            scorecards.append(self.score_network(self.network_name(self._options.compare_hocon_file), fixture_paths))
        report = self.report(scorecards)
        return self.write_output(report)

    def fixture_paths(self, network_name: str) -> list[str]:
        """
        Return the network's fixtures, narrowed to `--only-fixtures` when given.

        :param network_name: The runtime network name.
        :return: Sorted fixture paths; empty when a requested fixture is missing, after logging which.
        """
        paths = sorted(glob.glob(os.path.join(self._fixture_root, network_name, "*.hocon")))
        only_fixtures = self._options.only_fixtures
        if not only_fixtures:
            return paths
        by_name = {os.path.basename(path): path for path in paths}
        missing = [name for name in only_fixtures if by_name.get(name) is None]
        if missing:
            logger.error("Fixtures not found under %s: %s", os.path.join(self._fixture_root, network_name), missing)
            return []
        return [by_name.get(name) for name in only_fixtures]

    def score_network(self, network_name: str, fixture_paths: list[str]) -> NetworkScorecard:
        """
        Run every fixture against one network.

        :param network_name: The network to run the fixtures against.
        :param fixture_paths: The fixtures to run.
        :return: The network's scorecard.
        """
        attempts: list[AttemptResult] = []
        for fixture_path in fixture_paths:
            attempts.extend(FixtureScorer(fixture_path, self._options.repeats, agent=network_name).score())
        return NetworkScorecard(network_name, attempts)

    def report(self, scorecards: list[NetworkScorecard]) -> dict[str, Any]:
        """
        Print the text report and return the JSON report.

        :param scorecards: The baseline scorecard, then the candidate when comparing.
        :return: The JSON-ready report.
        """
        report: dict[str, Any] = {
            "repeats": self._options.repeats,
            "scorecards": [scorecard.to_dict() for scorecard in scorecards],
        }
        # The report is the command's output, not a log message, so it goes to stdout.
        for scorecard in scorecards:
            print(ScoreReportFormatter.scorecard_text(scorecard))
        if len(scorecards) == 2:
            comparison = PairedComparison(scorecards[0], scorecards[1])
            report.update({"comparison": comparison.to_dict()})
            print(ScoreReportFormatter.comparison_text(comparison))
        return report

    def write_output(self, report: dict[str, Any]) -> int:
        """
        Write the JSON report when `--output` was given.

        :param report: The JSON-ready report.
        :return: EXIT_OK, or EXIT_ERROR when the file cannot be written.
        """
        output = self._options.output
        if not output:
            return self.EXIT_OK
        try:
            with open(output, "w", encoding="utf-8") as output_file:
                json.dump(report, output_file, indent=2)
        except OSError as exc:
            logger.error("Could not write the score report to %s: %s", output, exc)
            return self.EXIT_ERROR
        logger.info("Wrote the score report to %s", output)
        return self.EXIT_OK

    @staticmethod
    def main() -> None:
        """Run from the JSON options that `ns score` passes as the only argument."""
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
        options = ScoreOptions(**json.loads(sys.argv[1]))
        sys.exit(NetworkScoreRunner(options).run())


if __name__ == "__main__":
    NetworkScoreRunner.main()
