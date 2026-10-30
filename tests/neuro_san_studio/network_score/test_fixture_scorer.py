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

"""Tests for scoring every repeat of one fixture."""

from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch

from neuro_san_studio.network_score.fixture_scorer import FixtureScorer
from neuro_san_studio.network_score.token_timed_assert_capture import TokenTimedAssertCapture


class TestFixtureScorer(TestCase):
    """Verify attempt setup, the no-early-stop call and result conversion, with no LLM calls."""

    TEST_CASE = {
        "agent": "basic/old",
        "success_ratio": "2/3",
        "interactions": [
            {"text": "first question"},
            {"text": "second question", "chat_filter": "MINIMAL"},
        ],
    }

    def test_attempts_are_independent_and_set_up_for_scoring(self) -> None:
        """Each attempt is a copy with the agent override and the token-keeping chat filter."""
        test_cases = FixtureScorer("tests/fixtures/basic/old/q.hocon", 3, agent="basic/new").attempt_test_cases(
            self.TEST_CASE
        )

        self.assertEqual(3, len(test_cases))
        self.assertIsNot(test_cases[0], test_cases[1])
        self.assertEqual("basic/new", test_cases[0].get("agent"))
        interactions = test_cases[0].get("interactions")
        self.assertEqual(FixtureScorer.SCORING_CHAT_FILTER, interactions[0].get("chat_filter"))
        # A fixture's own chat filter is kept.
        self.assertEqual("MINIMAL", interactions[1].get("chat_filter"))
        # The parsed fixture itself is not changed.
        self.assertIsNone(self.TEST_CASE.get("interactions")[0].get("chat_filter"))

    def test_without_override_the_fixture_agent_is_kept(self) -> None:
        """Scoring a single network leaves the fixture's agent alone."""
        test_cases = FixtureScorer("q.hocon", 1).attempt_test_cases(self.TEST_CASE)

        self.assertEqual("basic/old", test_cases[0].get("agent"))

    def test_repeats_are_at_least_one(self) -> None:
        """A zero repeat count still runs one attempt."""
        self.assertEqual(1, len(FixtureScorer("q.hocon", 0).attempt_test_cases(self.TEST_CASE)))

    def test_score_asks_the_driver_to_finish_every_attempt(self) -> None:
        """The success threshold equals the attempt count, so the driver cannot stop early."""
        passing = TokenTimedAssertCapture(MagicMock(), test_index=1)
        passing.add_token_accounting({"total_tokens": 5, "total_cost": 0.01})
        failing = TokenTimedAssertCapture(MagicMock(), test_index=0)
        failing.add_assert(AssertionError("wrong answer"))
        with (
            patch("neuro_san_studio.network_score.fixture_scorer.TestsUtil.parse_hocon_test_case") as parse,
            patch("neuro_san_studio.network_score.fixture_scorer.ScoringTestsDriver.run_tests") as run_tests,
        ):
            parse.return_value = dict(self.TEST_CASE)
            run_tests.return_value = [passing, failing]

            results = FixtureScorer("tests/fixtures/basic/old/q.hocon", 2).score()

        test_cases, threshold = run_tests.call_args.args
        self.assertEqual(len(test_cases), threshold)
        self.assertEqual([0, 1], [result.attempt for result in results])
        self.assertFalse(results[0].passed)
        self.assertIsNone(results[0].total_cost)
        self.assertTrue(results[1].passed)
        self.assertEqual(5, results[1].total_tokens)
        self.assertEqual("q.hocon", results[1].fixture)

    def test_single_attempt_without_index_is_attempt_zero(self) -> None:
        """The driver gives a lone attempt no index; it is reported as attempt 0."""
        capture = TokenTimedAssertCapture(MagicMock(), test_index=None)

        results = FixtureScorer("q.hocon", 1).attempt_results([capture])

        self.assertEqual(0, results[0].attempt)
        self.assertTrue(results[0].passed)
