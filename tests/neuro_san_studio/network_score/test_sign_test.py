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

"""Tests for the exact two-sided sign test."""

from unittest import TestCase

from neuro_san_studio.network_score.sign_test import SignTest


class TestSignTest(TestCase):
    """Verify sign-test p-values against hand-computed binomial tails."""

    def test_lopsided_split_matches_the_binomial_tail(self) -> None:
        """17 against 2 is 2 * (1 + 19 + 171) / 2**19."""
        self.assertAlmostEqual(382 / 2**19, SignTest.two_sided_p_value(17, 2))

    def test_order_of_the_counts_does_not_matter(self) -> None:
        """The test is two-sided, so swapping the networks gives the same p-value."""
        self.assertEqual(SignTest.two_sided_p_value(9, 3), SignTest.two_sided_p_value(3, 9))

    def test_even_split_is_capped_at_one(self) -> None:
        """An even split doubles a tail above one half, so the result is capped."""
        self.assertEqual(1.0, SignTest.two_sided_p_value(5, 5))

    def test_no_discordant_pairs_gives_no_evidence(self) -> None:
        """With no pair where only one network passed, the p-value is 1."""
        self.assertEqual(1.0, SignTest.two_sided_p_value(0, 0))

    def test_negative_count_is_rejected(self) -> None:
        """A negative pair count is a caller bug and is reported."""
        with self.assertRaises(ValueError):
            SignTest.two_sided_p_value(-1, 2)
