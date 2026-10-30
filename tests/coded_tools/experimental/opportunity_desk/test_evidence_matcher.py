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

from unittest import TestCase

from coded_tools.experimental.opportunity_desk.evidence_matcher import EvidenceMatcher

PAGE: str = """
<p>MAKER solves a task with over one million LLM steps with zero errors,
using “extreme decomposition” and voting.</p>
"""


class TestEvidenceMatcher(TestCase):
    """
    The matcher must accept a real quote through formatting noise and reject a paraphrase.
    """

    def test_verbatim_quote_through_markup_line_breaks_and_curly_quotes(self):
        """Normalization makes formatting irrelevant."""
        quote = 'solves a task with over one million LLM steps with zero errors, using "extreme decomposition"'
        self.assertEqual(EvidenceMatcher.coverage(PAGE, quote), 1.0)

    def test_one_dropped_word_still_matches(self):
        """Most shingles survive a small slip."""
        quote = "MAKER solves a task with over one million LLM steps with zero errors using decomposition and voting"
        self.assertTrue(EvidenceMatcher.is_supported(PAGE, quote))

    def test_paraphrase_is_rejected(self):
        """The same meaning in other words is exactly what this check refuses."""
        quote = "The system completes more than a million model calls without a single mistake"
        self.assertFalse(EvidenceMatcher.is_supported(PAGE, quote))

    def test_short_quote_proves_nothing(self):
        """Fewer than six words scores zero even when present."""
        self.assertEqual(EvidenceMatcher.coverage(PAGE, "with zero errors"), 0.0)
