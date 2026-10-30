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

import html
import re
from datetime import datetime
from datetime import timezone
from typing import Any
from urllib.parse import quote

from bs4 import BeautifulSoup

from coded_tools.experimental.opportunity_desk.posting import Posting

# Board slugs and repository names go into URLs, so they are checked before use.
SLUG_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
REPO_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9._-]{1,100}/[A-Za-z0-9._-]{1,100}$")
# Long enough for the requirements section of a posting; keeps the store small.
MAX_DESCRIPTION_CHARS: int = 8000

# Each provider's public, unauthenticated job-board endpoint. These are the
# endpoints the providers document for embedding a careers page, so reading them
# is permitted; sites that forbid automated access (LinkedIn, Naukri) are not here.
BOARD_URLS: dict[str, str] = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}
GITHUB_ISSUES_URL: str = "https://api.github.com/repos/{repo}/issues?state=open&per_page=50&labels={label}"


class BoardParser:
    """
    Builds board URLs and turns each provider's JSON into Postings. No network access.

    The field names follow each provider's public job-board API: Greenhouse's
    "jobs" list with HTML-escaped "content", Lever's top-level list whose
    requirements sit in "lists" rather than the description, Ashby's "jobs" list,
    and GitHub's issues list, where pull requests also appear and are skipped.
    """

    @staticmethod
    def board_url(board: dict[str, Any]) -> str:
        """
        :param board: A profile entry with "provider" and "slug".
        :return: The provider's public listing URL for that board.
        :raises ValueError: For an unsupported provider or a malformed slug.
        """
        provider: str = str(board.get("provider", "")).lower()
        slug: str = str(board.get("slug", ""))
        if provider not in BOARD_URLS:
            raise ValueError(f"unsupported provider '{provider}'; use one of {', '.join(BOARD_URLS)}")
        if not SLUG_PATTERN.match(slug):
            raise ValueError(f"malformed {provider} board slug '{slug}'")
        return BOARD_URLS.get(provider).format(slug=slug)

    @staticmethod
    def issue_urls(spec: dict[str, Any]) -> list[str]:
        """
        :param spec: A profile entry with "repo" ("owner/name") and optional "labels".
        :return: One open-issues URL per label, or one unfiltered URL when no labels are given.
        :raises ValueError: For a malformed repository name.
        """
        repo: str = str(spec.get("repo", ""))
        if not REPO_PATTERN.match(repo):
            raise ValueError(f"malformed repository name '{repo}'; expected owner/name")
        labels: list[str] = list(spec.get("labels") or [""])
        return [GITHUB_ISSUES_URL.format(repo=repo, label=quote(label)) for label in labels]

    @staticmethod
    def parse_board(board: dict[str, Any], document: Any) -> list[Posting]:
        """
        :param board: The profile entry the document was fetched for.
        :param document: The decoded JSON response.
        :return: The postings it lists.
        :raises ValueError: When the document does not have the provider's shape.
        """
        provider: str = str(board.get("provider", "")).lower()
        slug: str = str(board.get("slug", ""))
        company: str = str(board.get("company") or slug)
        if provider == "greenhouse":
            return [BoardParser._greenhouse(job, slug, company) for job in BoardParser._jobs(document, provider)]
        if provider == "lever":
            if not isinstance(document, list):
                raise ValueError(f"lever board '{slug}' did not return a list of postings")
            return [BoardParser._lever(job, slug, company) for job in document if isinstance(job, dict)]
        if provider == "ashby":
            jobs: list[dict[str, Any]] = BoardParser._jobs(document, provider)
            return [BoardParser._ashby(job, slug, company) for job in jobs if job.get("isListed", True)]
        raise ValueError(f"unsupported provider '{provider}'")

    @staticmethod
    def parse_issues(repo: str, document: Any) -> list[Posting]:
        """
        :param repo: The "owner/name" the issues came from.
        :param document: The decoded JSON list from the GitHub issues endpoint.
        :return: One contribution posting per open issue, pull requests skipped.
        :raises ValueError: When the document is not a list.
        """
        if not isinstance(document, list):
            raise ValueError(f"GitHub did not return an issue list for {repo}")
        postings: list[Posting] = []
        for issue in document:
            if not isinstance(issue, dict) or "pull_request" in issue:
                continue
            labels: list[str] = [
                label.get("name", "") for label in issue.get("labels") or [] if isinstance(label, dict)
            ]
            postings.append(
                Posting(
                    posting_id=f"github:{repo}:{issue.get('number')}",
                    kind="contribution",
                    source="github",
                    title=str(issue.get("title", "")),
                    company=repo,
                    location="open source",
                    url=str(issue.get("html_url", "")),
                    description=BoardParser._clip(f"Labels: {', '.join(labels)}\n{issue.get('body') or ''}"),
                    posted_at=str(issue.get("created_at") or ""),
                )
            )
        return postings

    @staticmethod
    def _jobs(document: Any, provider: str) -> list[dict[str, Any]]:
        """
        :param document: A decoded response expected to hold a "jobs" list.
        :param provider: For the error message.
        :return: The job objects.
        :raises ValueError: When there is no "jobs" list.
        """
        jobs: Any = document.get("jobs") if isinstance(document, dict) else None
        if not isinstance(jobs, list):
            raise ValueError(f"{provider} response has no 'jobs' list")
        return [job for job in jobs if isinstance(job, dict)]

    @staticmethod
    def _greenhouse(job: dict[str, Any], slug: str, company: str) -> Posting:
        """
        :param job: One Greenhouse job object.
        :param slug: The board slug.
        :param company: Display name for the employer.
        :return: The normalized posting.
        """
        location: Any = job.get("location") or {}
        return Posting(
            posting_id=f"greenhouse:{slug}:{job.get('id')}",
            kind="role",
            source="greenhouse",
            title=str(job.get("title", "")),
            company=str(job.get("company_name") or company),
            location=str(location.get("name", "") if isinstance(location, dict) else location),
            url=str(job.get("absolute_url", "")),
            description=BoardParser._plain(str(job.get("content") or "")),
            posted_at=str(job.get("first_published") or job.get("updated_at") or ""),
        )

    @staticmethod
    def _lever(job: dict[str, Any], slug: str, company: str) -> Posting:
        """
        :param job: One Lever posting object.
        :param slug: The board slug.
        :param company: Display name for the employer.
        :return: The normalized posting; its description includes the "lists" sections,
            which is where Lever postings state years of experience.
        """
        categories: dict[str, Any] = job.get("categories") or {}
        places: list[str] = list(categories.get("allLocations") or [])
        location: str = ", ".join(places) or str(categories.get("location") or "")
        if str(job.get("workplaceType", "")).lower() == "remote":
            location = f"{location} (remote)".strip()
        sections: list[str] = [f"{item.get('text', '')}\n{item.get('content', '')}" for item in job.get("lists") or []]
        description: str = "\n".join(
            [str(job.get("descriptionPlain") or ""), *sections, str(job.get("additionalPlain") or "")]
        )
        created: Any = job.get("createdAt")
        posted_at: str = ""
        if isinstance(created, int | float):
            posted_at = datetime.fromtimestamp(created / 1000, tz=timezone.utc).isoformat(timespec="seconds")
        return Posting(
            posting_id=f"lever:{slug}:{job.get('id')}",
            kind="role",
            source="lever",
            title=str(job.get("text", "")),
            company=company,
            location=location,
            url=str(job.get("hostedUrl", "")),
            description=BoardParser._plain(description),
            posted_at=posted_at,
        )

    @staticmethod
    def _ashby(job: dict[str, Any], slug: str, company: str) -> Posting:
        """
        :param job: One Ashby job object.
        :param slug: The board slug.
        :param company: Display name for the employer.
        :return: The normalized posting.
        """
        places: list[str] = [str(job.get("location") or "")]
        places += [
            str(extra.get("location", "")) for extra in job.get("secondaryLocations") or [] if isinstance(extra, dict)
        ]
        if job.get("isRemote"):
            places.append("Remote")
        return Posting(
            posting_id=f"ashby:{slug}:{job.get('id')}",
            kind="role",
            source="ashby",
            title=str(job.get("title", "")),
            company=company,
            location=", ".join(place for place in places if place),
            url=str(job.get("jobUrl", "")),
            description=BoardParser._plain(str(job.get("descriptionPlain") or job.get("descriptionHtml") or "")),
            posted_at=str(job.get("publishedAt") or ""),
        )

    @staticmethod
    def _plain(text: str) -> str:
        """
        :param text: Text that may be HTML, possibly entity-escaped as Greenhouse sends it.
        :return: Plain text, clipped to MAX_DESCRIPTION_CHARS.
        """
        unescaped: str = html.unescape(text)
        if "<" in unescaped:
            unescaped = BeautifulSoup(unescaped, "html.parser").get_text(separator="\n", strip=True)
        return BoardParser._clip(unescaped)

    @staticmethod
    def _clip(text: str) -> str:
        """
        :param text: Any text.
        :return: The text, no longer than MAX_DESCRIPTION_CHARS.
        """
        return text[:MAX_DESCRIPTION_CHARS]
