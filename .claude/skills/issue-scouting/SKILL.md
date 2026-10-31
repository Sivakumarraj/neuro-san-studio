---
name: issue-scouting
description: "How to find and rank open issues in cognizant-ai-lab/neuro-san-studio, neuro-san and nsflow that an outside contributor can fix and get merged: where to read them, how to tell whether someone is already on one, the ranking rubric, and the target brief to hand over. Use when asked what to contribute next, to find an issue, or to check whether an issue is still free."
---

# Issue scouting

The aim is the issue most likely to be reviewed and merged soon, not the most interesting one. A
maintainer-filed, unclaimed, fresh, small issue gets a review; a large feature from an outsider
usually waits.

## Read the issues

- Open issues, newest first, from the logged-out page of each repository
  (github.com/cognizant-ai-lab/<repo>/issues?q=is:issue+is:open+sort:created-desc) through a
  web-fetch tool, or from the REST API (api.github.com/repos/cognizant-ai-lab/<repo>/issues?state=open&per_page=50,
  60 unauthenticated requests an hour). In the API, an entry with a `pull_request` key is a pull
  request: skip it. `assignees` and `user.login` say who holds it and who filed it.
- Upstream leaves most issues unlabelled, so never filter by label.

## Is it still free?

Upstream assigns almost every issue to whoever filed it (on Oct 31 2026 only a canary test was unassigned in
neuro-san-studio), so assignment is not the test. An issue is a candidate when:

1. No open pull request mentions it (github.com/cognizant-ai-lab/<repo>/pulls?q=is:pr+<NNNN>) and no
   branch for it shows under the issue's Development section.
2. It is not already fixed: `git log upstream/main --oneline --grep "#<NNNN>"` (upstream's commits start
   with the issue number).
3. It has waited a week or more. A brand-new issue is usually in its filer's hands, and outside fixes that
   raced the owner were closed when the owner's own fix landed (#1511).
4. The first step is a comment asking the assignee whether they would take an outside pull request, and no
   code is written before they say yes.

GitHub's `author_association` is not a reliable maintainer signal: staff with private organization
membership show as CONTRIBUTOR to a logged-out reader. Use the owner's maintainer list (the desk profile's
`maintainers`) instead.

## Rank

Score the way the Opportunity Desk's `FitAssessor` scores contributions, so the two agree:

| Signal | Points |
|--------|--------|
| The change is in familiar ground: coded tools, HOCON networks, the `ns` CLI, tests, docs | up to 40 |
| Nobody assigned / assigned to its filer / assigned to someone else | 25 / 15 / 5 |
| A maintainer filed it | 20 |
| Open 7 to 60 days / longer / under a week | 15 / 5 / 0 |

Among close scores, prefer the smaller change, the clearer definition of done, and the fix a unit
test can prove. Avoid the Agent Network Designer refactors maintainers are partway through, anything
that needs secrets or paid APIs to test, and features without a maintainer's go-ahead.

## Target brief

Write `logs/agents_workspace/1_scout_target.md` with a first choice and a runner-up. For each: the
issue link and title; why it ranks there (signals and points); the scope (files, rough size); the
test that will prove the fix; and the risks (overlap with in-flight work, unclear acceptance).
