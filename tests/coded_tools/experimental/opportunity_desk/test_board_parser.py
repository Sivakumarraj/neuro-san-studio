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

# Trimmed from a real response of https://api.lever.co/v0/postings/leverdemo?mode=json (Oct 2026),
# with the posting URL moved to an example host so the repository's link check never depends on it.
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
        "hostedUrl": "https://jobs.example.com/leverdemo/ad208490-4052-4f91-a57e-433f2d1e484b",
    }
]
# Shape of https://boards-api.greenhouse.io/v1/boards/<slug>/jobs?content=true; content is entity-escaped HTML.
GREENHOUSE_RESPONSE: dict = {
    "jobs": [
        {
            "id": 4011,
            "title": "AI Engineer",
            "absolute_url": "https://boards.example.com/acme/jobs/4011",
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
            "jobUrl": "https://jobs.example.com/acme/b1",
            "descriptionPlain": "LLM evaluation work.",
            "publishedAt": "2026-10-21T00:00:00.000+00:00",
        },
        {"id": "b2", "title": "Hidden", "isListed": False},
    ]
}
# Shape of a GitHub issue-search response: pull requests carry a "pull_request" object.
GITHUB_SEARCH: dict = {
    "total_count": 2,
    "items": [
        {
            "number": 1297,
            "title": "docs: add Legacy Business-Rule Extractor to Community Projects",
            "state": "closed",
            "comments": 1,
            "html_url": "https://github.com/cognizant-ai-lab/neuro-san-studio/pull/1297",
            "repository_url": "https://api.github.com/repos/cognizant-ai-lab/neuro-san-studio",
            "pull_request": {"merged_at": "2026-08-11T00:09:00Z"},
            "created_at": "2026-08-04T13:46:44Z",
            "updated_at": "2026-08-11T00:09:00Z",
            "closed_at": "2026-08-11T00:09:00Z",
        },
        {
            "number": 1550,
            "title": "Score networks over every repeat",
            "state": "open",
            "comments": 0,
            "html_url": "https://github.example.com/cognizant-ai-lab/neuro-san-studio/issues/1550",
            "repository_url": "https://api.github.com/repos/cognizant-ai-lab/neuro-san-studio",
            "created_at": "2026-10-31T09:00:00Z",
            "updated_at": "2026-10-31T09:00:00Z",
            "closed_at": None,
        },
    ],
}
GITHUB_ISSUES: list = [
    {
        "number": 12,
        "title": "Add retries to the search tool",
        "html_url": "https://github.example.com/org/repo/issues/12",
        "labels": [{"name": "good first issue"}],
        "body": "Python change.",
        "created_at": "2026-10-01T00:00:00Z",
        "user": {"login": "Noravee"},
        "author_association": "MEMBER",
        "assignees": [],
        "comments": 0,
    },
    {
        "number": 14,
        "title": "Taken already",
        "html_url": "https://github.example.com/org/repo/issues/14",
        "body": "Python change.",
        "created_at": "2026-10-02T00:00:00Z",
        "author_association": "NONE",
        "assignees": [{"login": "someone"}],
        "comments": 3,
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

    def test_github_issues_skip_pull_requests_and_record_claims(self):
        """The issues endpoint lists pull requests too; they are not open work. Claims are kept."""
        postings = BoardParser.parse_issues("org/repo", GITHUB_ISSUES)
        self.assertEqual([posting.posting_id for posting in postings], ["github:org/repo:12", "github:org/repo:14"])
        self.assertEqual(postings[0].kind, "contribution")
        self.assertIn("good first issue", postings[0].description)
        self.assertTrue(postings[0].filed_by_maintainer)
        self.assertEqual(postings[0].filed_by, "Noravee")
        self.assertEqual(postings[0].claimed_by, "")
        self.assertEqual(postings[1].claimed_by, "someone")
        self.assertEqual(postings[1].comments, 3)

    def test_unlabelled_repositories_read_every_open_issue(self):
        """Upstream labels nothing, so no labels must mean no label filter, not an empty one."""
        self.assertEqual(
            BoardParser.issue_urls({"repo": "cognizant-ai-lab/neuro-san-studio", "labels": []}),
            ["https://api.github.com/repos/cognizant-ai-lab/neuro-san-studio/issues?state=open&per_page=50"],
        )

    def test_contributions_search_and_parse(self):
        """One search covers every repository; merged pull requests are told apart from closed ones."""
        url = BoardParser.contributions_url(
            "Sivakumarraj", ["cognizant-ai-lab/neuro-san-studio", "cognizant-ai-lab/nsflow"]
        )
        self.assertIn(
            "q=author:Sivakumarraj%20repo:cognizant-ai-lab/neuro-san-studio%20repo:cognizant-ai-lab/nsflow", url
        )
        with self.assertRaises(ValueError):
            BoardParser.contributions_url("bad user", ["o/r"])
        with self.assertRaises(ValueError):
            BoardParser.contributions_url("user", [])
        records = BoardParser.parse_contributions(GITHUB_SEARCH)
        self.assertEqual(records[0].get("item_key"), "cognizant-ai-lab/neuro-san-studio#1297")
        self.assertEqual(records[0].get("kind"), "pull_request")
        self.assertTrue(records[0].get("merged"))
        self.assertEqual(records[1].get("kind"), "issue")
        self.assertFalse(records[1].get("merged"))
        with self.assertRaises(ValueError):
            BoardParser.parse_contributions({"message": "API rate limit exceeded"})

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
