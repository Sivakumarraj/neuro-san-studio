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

from coded_tools.experimental.opportunity_desk.board_parser import BoardParser

# Trimmed from a real response of https://api.lever.co/v0/postings/leverdemo?mode=json (Oct 2026).
# The "3+ years" requirement sits in "lists", not in the description.
LEVER_RESPONSE: list = [
    {
        "categories": {
            "commitment": "Regular Full Time (Salary)",
            "location": "Atlanta, Georgia",
            "allLocations": ["Atlanta, Georgia"],
        },
        "createdAt": 1788199939703,
        "descriptionPlain": "Join a scaling, tight-knit team.",
        "id": "ad208490-4052-4f91-a57e-433f2d1e484b",
        "lists": [{"text": "Skill Set:", "content": "<li>3+ years of customer relationship experience</li>"}],
        "text": "Customer Success Manager",
        "workplaceType": "hybrid",
        "hostedUrl": "https://jobs.lever.co/leverdemo/ad208490-4052-4f91-a57e-433f2d1e484b",
    }
]
# Shape of https://boards-api.greenhouse.io/v1/boards/<slug>/jobs?content=true; content is entity-escaped HTML.
GREENHOUSE_RESPONSE: dict = {
    "jobs": [
        {
            "id": 4011,
            "title": "AI Engineer",
            "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/4011",
            "location": {"name": "Bengaluru, India"},
            "updated_at": "2026-10-20T10:00:00-04:00",
            "first_published": "2026-10-18T09:00:00-04:00",
            "company_name": "Acme AI",
            "content": "&lt;p&gt;Build &lt;strong&gt;RAG&lt;/strong&gt; agents in Python.&lt;/p&gt;",
        }
    ],
    "meta": {"total": 1},
}
# Shape of https://api.ashbyhq.com/posting-api/job-board/<slug>.
ASHBY_RESPONSE: dict = {
    "jobs": [
        {
            "id": "b1",
            "title": "Applied AI Engineer",
            "location": "Bengaluru",
            "secondaryLocations": [{"location": "Hyderabad"}],
            "isRemote": True,
            "isListed": True,
            "jobUrl": "https://jobs.ashbyhq.com/acme/b1",
            "descriptionPlain": "LLM evaluation work.",
            "publishedAt": "2026-10-21T00:00:00.000+00:00",
        },
        {"id": "b2", "title": "Hidden", "isListed": False},
    ]
}
GITHUB_ISSUES: list = [
    {
        "number": 12,
        "title": "Add retries to the search tool",
        "html_url": "https://github.com/org/repo/issues/12",
        "labels": [{"name": "good first issue"}],
        "body": "Python change.",
        "created_at": "2026-10-01T00:00:00Z",
    },
    {"number": 13, "title": "A pull request", "pull_request": {"url": "x"}},
]


class TestBoardParser(TestCase):
    """
    Each provider's JSON must come out as the same Posting shape, and nothing unsafe may reach a URL.
    """

    def test_lever_includes_lists_in_the_description(self):
        """Lever keeps requirements in 'lists'; dropping them would hide the years asked for."""
        posting = BoardParser.parse_board(
            {"provider": "lever", "slug": "leverdemo", "company": "Lever"}, LEVER_RESPONSE
        )[0]
        self.assertEqual(posting.posting_id, "lever:leverdemo:ad208490-4052-4f91-a57e-433f2d1e484b")
        self.assertEqual(posting.title, "Customer Success Manager")
        self.assertEqual(posting.location, "Atlanta, Georgia")
        self.assertIn("3+ years", posting.description)
        self.assertNotIn("<li>", posting.description)
        self.assertTrue(posting.posted_at.startswith("2026-"))

    def test_greenhouse_unescapes_and_strips_content(self):
        """Greenhouse sends HTML as entities; the description must be plain text."""
        posting = BoardParser.parse_board({"provider": "greenhouse", "slug": "acme"}, GREENHOUSE_RESPONSE)[0]
        self.assertEqual(posting.company, "Acme AI")
        self.assertEqual(posting.location, "Bengaluru, India")
        self.assertIn("RAG", posting.description)
        self.assertNotIn("<", posting.description)
        self.assertEqual(posting.posted_at, "2026-10-18T09:00:00-04:00")

    def test_ashby_merges_locations_and_skips_unlisted(self):
        """Secondary locations and remote both count; unlisted jobs are not openings."""
        postings = BoardParser.parse_board({"provider": "ashby", "slug": "acme", "company": "Acme"}, ASHBY_RESPONSE)
        self.assertEqual(len(postings), 1)
        self.assertEqual(postings[0].location, "Bengaluru, Hyderabad, Remote")

    def test_github_issues_skip_pull_requests(self):
        """The issues endpoint lists pull requests too; they are not open work."""
        postings = BoardParser.parse_issues("org/repo", GITHUB_ISSUES)
        self.assertEqual([posting.posting_id for posting in postings], ["github:org/repo:12"])
        self.assertEqual(postings[0].kind, "contribution")
        self.assertIn("good first issue", postings[0].description)

    def test_urls_are_built_only_from_safe_names(self):
        """A slug or repository that could rewrite the URL is refused."""
        self.assertEqual(
            BoardParser.board_url({"provider": "lever", "slug": "acme"}),
            "https://api.lever.co/v0/postings/acme?mode=json",
        )
        with self.assertRaises(ValueError):
            BoardParser.board_url({"provider": "lever", "slug": "acme/../../admin"})
        with self.assertRaises(ValueError):
            BoardParser.board_url({"provider": "linkedin", "slug": "acme"})
        with self.assertRaises(ValueError):
            BoardParser.issue_urls({"repo": "org/repo?x=1"})
        self.assertIn(
            "labels=good%20first%20issue", BoardParser.issue_urls({"repo": "o/r", "labels": ["good first issue"]})[0]
        )

    def test_wrong_shape_is_an_error_not_an_empty_board(self):
        """A changed API must fail loudly, never look like a board with no openings."""
        with self.assertRaises(ValueError):
            BoardParser.parse_board({"provider": "greenhouse", "slug": "acme"}, {"error": "not found"})
        with self.assertRaises(ValueError):
            BoardParser.parse_board({"provider": "lever", "slug": "acme"}, {"ok": False})
