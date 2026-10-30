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

"""Neuro SAN's data-driven test driver, extended to keep each attempt's token accounting."""

from leaf_common.parsers.dictionary_extractor import DictionaryExtractor
from leaf_common.time.timeout import Timeout
from neuro_san.message.processors.basic_message_processor import BasicMessageProcessor
from neuro_san.test.driver.data_driven_tests_driver import DataDrivenTestsDriver
from neuro_san.test.interfaces.assert_forwarder import AssertForwarder

from neuro_san_studio.network_score.token_timed_assert_capture import TokenTimedAssertCapture


class ScoringTestsDriver(DataDrivenTestsDriver):
    """
    Run fixture attempts exactly as DataDrivenTestsDriver does, and record what each one spent.

    The base driver already streams every message through a BasicMessageProcessor, which keeps the final token
    accounting, but it never reads it. Two overrides fix that without copying the base class's interact():
    get_new_capture() makes each attempt's capture a TokenTimedAssertCapture, and test_response_keys(), which the
    base class calls once per interaction with that processor, copies the accounting into the capture.
    """

    def get_new_capture(self, test_index: int | None = None) -> TokenTimedAssertCapture:
        """
        Override of DataDrivenTestsDriver.get_new_capture() that returns a token-keeping capture.

        :param test_index: Optional index of the attempt for logging and reporting.
        :return: A new TokenTimedAssertCapture for one attempt.
        """
        return TokenTimedAssertCapture(self.asserts_basis, test_index=test_index)

    def test_response_keys(
        self,
        processor: BasicMessageProcessor,
        response_extractor: DictionaryExtractor,
        keys: list[str],
        asserts: AssertForwarder,
        timeouts: list[Timeout],
    ) -> None:
        """
        Override of DataDrivenTestsDriver.test_response_keys() that records token accounting before grading.

        Recording first keeps the spend even when grading raises. `asserts` is always the capture made by
        get_new_capture() above, because the base driver passes each attempt's own capture down to here.
        The base method calls itself again for nested response keys such as `text.keywords`; only the first
        call, from interact() with TEST_KEYS, records, so each interaction is counted once.

        :param processor: The processor that consumed this interaction's messages.
        :param response_extractor: The fixture's expected-response block.
        :param keys: The response keys to grade.
        :param asserts: This attempt's capture.
        :param timeouts: The timeouts to check while grading.
        """
        if keys == self.TEST_KEYS:
            asserts.add_token_accounting(processor.get_token_accounting())
        super().test_response_keys(processor, response_extractor, keys, asserts, timeouts)
