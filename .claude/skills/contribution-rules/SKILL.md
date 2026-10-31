---
name: contribution-rules
description: "The rules every change in this fork follows before it can reach cognizant-ai-lab: AGENTS.md first, branch and commit naming, the owner's commit identity, the PR template, issue-first for features, what never goes upstream, and the owner's standing rules (technical content only, no job or AI-tool language in PRs, commits or issues). Use when writing a commit message, naming a branch, drafting a PR or an issue, or deciding whether a change belongs upstream at all."
---

# Contribution rules

These rules exist because every upstream pull request carries the owner's name to the people who
review his work. A careless one costs more than a missing one.

## Upstream's rules come first

`AGENTS.md` at the repository root is the maintainers' own rulebook for coding agents. Read it in
full before any change; this skill only adds what it does not say. The points that most often sink
a pull request:

- every network sets `max_steps` and `max_execution_seconds`;
- `.get()` for dictionaries, specific exceptions, type hints, docstrings, one class per file,
  `async_invoke` in coded tools, lazy `%` logging;
- 119-character lines in `.py` and `.md`, US spelling;
- documentation ships in the same PR, and every link in a touched document is verified;
- a curated example needs `metadata`, a docs page, a line and TOC entry in `docs/examples.md`, and
  a registered fixture.

## Branches and commits

- Cut every upstream branch from `upstream/main`, named `fix/<NNNN>-<short-name>`, `docs/...` or
  `feature/...` (AGENTS.md section 5). A branch cut from the fork's own main would carry fork-only
  files.
- One-line commit messages in upstream's form: `#<NNNN>: Imperative summary`, for example
  `#1544: Split the Agent Network Designer toolbox into local and multi-user files`.
- Author every commit as the owner. The environment's default git identity is not his:
  `git -c user.name="Siva Kumar Raju" -c user.email="rajusivakumar453@gmail.com" commit -m "..."`.
- No `Co-Authored-By` trailer, no session link and no tool name in commit messages: the owner's
  standing rule for his repositories.

## Pull requests and issues

- Fill `.github/PULL_REQUEST_TEMPLATE.md` heading by heading. A free-form description is one
  reason an earlier pull request was closed.
- Before writing code for any issue, comment on it asking its assignee (usually its filer) whether
  they would take an outside pull request, and wait for a yes. Outside fixes that raced an issue's
  owner were closed when the owner's own fix landed.
- A bug or chore can then go to a pull request with "Fixes #NNNN". A feature needs an issue first,
  and no pull request until a maintainer has answered it.
- Technical content only. Never mention jobs, hiring, referrals, internships or graduating in an
  issue, pull request, comment or commit. Mention at most one maintainer, and nudge at most once.
- The owner posts every issue, comment and pull request himself. Prepare the text, show it, stop.
- The owner must be able to explain every changed line without help; reviewers ask, and an
  answer he cannot give costs more than the change gained.

## What never goes upstream

Branching from `upstream/main` keeps all of these out; the preflight gate checks it anyway.

- `.claude/` and the harness section at the end of `CLAUDE.md`.
- The Opportunity Desk: `registries/experimental/opportunity_desk.hocon`,
  `registries/manifest_opportunity_desk.hocon`, `coded_tools/experimental/opportunity_desk/`,
  `tests/coded_tools/experimental/opportunity_desk/`, `tests/fixtures/experimental/opportunity_desk/`,
  `docs/examples/experimental/opportunity_desk.md`, `deploy/opportunity_desk/`, `render.yaml`, and
  the desk's lines in `docs/examples.md`, `registries/experimental/manifest.hocon`,
  `tests/integration/test_integration_test_hocons.py` and `.lycheeignore`.
- Anything from the owner's private profile: contacts, history, notes.

## The record these rules come from

- Whole applications submitted as code were closed (#1133, #1145); one-line Community Projects
  entries in the README were merged (#1134, #1297). A separate project belongs in Community
  Projects, not in the repository.
- The IT service desk was refused five times (#1133, its README entry removed on Jun 10 2026,
  #1138, #1145, #1179). Never resubmit it in any form.
- A merged code fix weighs more than another documentation line, and the people who merge them
  are the lab's own engineers.
- Open #1530 ("Feature/decision prescriptor", opened about Oct 24 2026) submits a new network as code
  with an empty "Fixes #" line and many merge commits from main: the pattern that gets closed. Finish its template
  and link an issue a maintainer has answered, or close it and list the network under Community
  Projects from its own repository.
