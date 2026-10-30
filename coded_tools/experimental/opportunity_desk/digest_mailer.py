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

import os
import smtplib
from email.message import EmailMessage

# The recipient comes only from the environment, never from an agent's arguments,
# so no prompt can make the desk email anyone but its owner.
SMTP_ENV: dict[str, str] = {
    "host": "OPPORTUNITY_DESK_SMTP_HOST",
    "port": "OPPORTUNITY_DESK_SMTP_PORT",
    "user": "OPPORTUNITY_DESK_SMTP_USER",
    "password": "OPPORTUNITY_DESK_SMTP_PASSWORD",
    "to": "OPPORTUNITY_DESK_DIGEST_TO",
}
DEFAULT_SMTP_PORT: int = 587
SMTP_TIMEOUT_SECONDS: int = 30


class DigestMailer:
    """
    Emails the digest to the owner over SMTP with STARTTLS (a Gmail app password works).

    Optional: when the variables in SMTP_ENV are not all set, is_configured() is False
    and SendDigest returns the digest as text instead of sending it.
    """

    @staticmethod
    def is_configured() -> bool:
        """
        :return: True when host, user, password and recipient are all set.
        """
        return all(os.getenv(SMTP_ENV.get(key)) for key in ("host", "user", "password", "to"))

    @staticmethod
    def send(subject: str, body: str) -> None:
        """
        Blocking; call through asyncio.to_thread.

        :param subject: The email subject.
        :param body: Plain-text body.
        :raises smtplib.SMTPException: When the server refuses the login or the message.
        :raises OSError: When the server cannot be reached.
        """
        message: EmailMessage = EmailMessage()
        message["From"] = os.getenv(SMTP_ENV.get("user"))
        message["To"] = os.getenv(SMTP_ENV.get("to"))
        message["Subject"] = subject
        message.set_content(body)
        port: int = int(os.getenv(SMTP_ENV.get("port")) or DEFAULT_SMTP_PORT)
        with smtplib.SMTP(os.getenv(SMTP_ENV.get("host")), port, timeout=SMTP_TIMEOUT_SECONDS) as server:
            server.starttls()
            server.login(os.getenv(SMTP_ENV.get("user")), os.getenv(SMTP_ENV.get("password")))
            server.send_message(message)
