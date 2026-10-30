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

"""Tests for the token-keeping data-driven test driver."""

from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch

from leaf_common.parsers.dictionary_extractor import DictionaryExtractor
from neuro_san.test.driver.data_driven_tests_driver import DataDrivenTestsDriver

from neuro_san_studio.network_score.scoring_tests_driver import ScoringTestsDriver
from neuro_san_studio.network_score.token_timed_assert_capture import TokenTimedAssertCapture


class TestScoringTestsDriver(TestCase):
    """Verify the two overrides that keep each attempt's token accounting."""

    def test_new_captures_keep_tokens(self) -> None:
        """Every attempt gets a token-keeping capture with its index."""
        driver = ScoringTestsDriver(MagicMock(), test_name="fixture.hocon")

        capture = driver.get_new_capture(test_index=2)

        self.assertIsInstance(capture, TokenTimedAssertCapture)
        self.assertEqual(2, capture.get_test_index())

    def test_accounting_is_recorded_before_grading(self) -> None:
        """The processor's accounting reaches the capture, and grading still runs with the same arguments."""
        driver = ScoringTestsDriver(MagicMock(), test_name="fixture.hocon")
        capture = driver.get_new_capture(test_index=0)
        processor = MagicMock()
        processor.get_token_accounting.return_value = {"total_tokens": 42, "total_cost": 0.01}
        extractor = MagicMock()

        with patch.object(DataDrivenTestsDriver, "test_response_keys") as base_grading:
            driver.test_response_keys(processor, extractor, ScoringTestsDriver.TEST_KEYS, capture, [])

        self.assertEqual(42, capture.get_total_tokens())
        base_grading.assert_called_once_with(processor, extractor, ScoringTestsDriver.TEST_KEYS, capture, [])

    def test_accounting_is_kept_when_grading_raises(self) -> None:
        """A grading error does not lose what the interaction spent."""
        driver = ScoringTestsDriver(MagicMock(), test_name="fixture.hocon")
        capture = driver.get_new_capture(test_index=0)
        processor = MagicMock()
        processor.get_token_accounting.return_value = {"total_tokens": 7, "total_cost": 0.0}

        with patch.object(DataDrivenTestsDriver, "test_response_keys", side_effect=TimeoutError("late")):
            with self.assertRaises(TimeoutError):
                driver.test_response_keys(processor, MagicMock(), ScoringTestsDriver.TEST_KEYS, capture, [])

        self.assertEqual(7, capture.get_total_tokens())

    def test_nested_keys_are_not_counted_again(self) -> None:
        """A real nested response spec makes the base method recurse; the interaction is still counted once."""
        driver = ScoringTestsDriver(MagicMock(), test_name="fixture.hocon")
        capture = driver.get_new_capture(test_index=0)
        processor = MagicMock()
        processor.get_token_accounting.return_value = {"total_tokens": 30, "total_cost": 0.0}
        # An unknown evaluator name is skipped by the base driver, so no LLM grading runs.
        extractor = DictionaryExtractor({"text": {"no_such_evaluator": "x"}, "structure": {"inner": {"deep": 1}}})

        driver.test_response_keys(processor, extractor, ScoringTestsDriver.TEST_KEYS, capture, [])

        self.assertEqual(30, capture.get_total_tokens())
