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

"""Tests for the token-keeping assert capture."""

from unittest import TestCase
from unittest.mock import MagicMock

from neuro_san_studio.network_score.token_timed_assert_capture import TokenTimedAssertCapture


class TestTokenTimedAssertCapture(TestCase):
    """Verify that token accounting is summed per attempt and never guessed."""

    def test_no_accounting_reports_unknown(self) -> None:
        """An attempt that saw no accounting reports `None`, not zero."""
        capture = TokenTimedAssertCapture(MagicMock(), test_index=0)

        self.assertIsNone(capture.get_total_tokens())
        self.assertIsNone(capture.get_total_cost())

    def test_interactions_are_summed(self) -> None:
        """Each interaction's accounting adds to the attempt totals."""
        capture = TokenTimedAssertCapture(MagicMock(), test_index=1)

        capture.add_token_accounting({"total_tokens": 100, "total_cost": 0.002})
        capture.add_token_accounting({"total_tokens": 50, "total_cost": 0.001})

        self.assertEqual(150, capture.get_total_tokens())
        self.assertAlmostEqual(0.003, capture.get_total_cost())
        self.assertEqual(1, capture.get_test_index())

    def test_missing_accounting_is_skipped(self) -> None:
        """An interaction with no accounting leaves earlier totals unchanged."""
        capture = TokenTimedAssertCapture(MagicMock())

        capture.add_token_accounting({"total_tokens": 10, "total_cost": 0.5})
        capture.add_token_accounting(None)
        capture.add_token_accounting({})

        self.assertEqual(10, capture.get_total_tokens())
        self.assertAlmostEqual(0.5, capture.get_total_cost())
