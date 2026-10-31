---
name: preflight-gate
description: "The checks upstream CI's quality gate runs — ruff format and lint, pylint, pymarkdown, unit tests, HOCON validation with the class check, the lychee link check — plus commit and diff hygiene, all runnable locally before a push. Use before any push, when CI is red, or when asked to check, preflight or QA a branch."
---

# Preflight gate

CI rejects a push for things that are cheap to catch first: in October 2026 a stale fork turned 105
tests red, and fixture URLs failed the link check. Run these from the repository root with the venv
active (`. venv/bin/activate`). They mirror `.github/workflows/tests.yml` and the Makefile; run the
narrow form while working and the full form before an upstream pull request.

## 1. Format and lint (the Makefile's `lint-check`)

```bash
ruff format --check --diff <changed paths>
ruff check <changed paths>
pylint <changed paths under apps, coded_tools, middleware or neuro_san_studio>
pylint <changed paths under tests>
pymarkdown --config ./.pymarkdownlint.yaml scan ./docs ./README.md
```

Scan any other changed `.md` file explicitly (AGENTS.md section 4). Lines stay within 119
characters, table rows included: `awk 'length > 119 {print FILENAME": "FNR}' <changed .md files>`.

## 2. Tests and validation

```bash
python -m pytest -q -m "not integration and not smoke" --ignore=tests/integration
python -m neuro_san_studio validate <each changed network .hocon>
```

`validate` also loads every coded tool class the network names. Two failures are known to come from
a root sandbox rather than the code: the permission tests in
`tests/neuro_san_studio/coded_tools/file_management/test_write_file.py`, and tests that call hosts a
sandbox proxy blocks. Confirm a suspect failure on a clean checkout of `upstream/main` before
blaming the branch.

## 3. Links

CI runs lychee 0.24.1 over `**/*.py`, `**/*.md`, `**/*.hocon`, `**/*.yml`, `**/*.json` and more,
code blocks included. List what it will request:

```bash
python .claude/skills/preflight-gate/scripts/link_check.py <changed files>
```

Every URL it prints must be a real, reachable page. Put fixture URLs on `*.example.com`. When code
builds an API URL from a template, add its non-browsable base to `.lycheeignore` under "URLs whose
base path is not browsable". The script cannot tell whether a page resolves; CI is the check of
record.

## 4. Dockerfiles

CI runs hadolint, which is not available locally. Keep Dockerfiles to pinned base images, a
`SHELL` with `pipefail`, `--no-cache-dir`, and a JSON-form `CMD`, and read CI's result.

## 5. Hygiene

```bash
# Authors must all be: Siva Kumar Raju <rajusivakumar453@gmail.com>
git log upstream/main..HEAD --format='%an <%ae>' | sort -u
WORDS="co-authored-by|claude|anthropic|\bjob\b|hiring|referral|resume|internship"
git log upstream/main..HEAD --format=%B | grep -i -n -E "$WORDS"
git diff --name-only upstream/main...HEAD | grep -E "^\.claude/|^CLAUDE\.md$|^render\.yaml$|opportunity_desk"
```

The last two must print nothing for an upstream branch. The pull-request body must carry every
heading of `.github/PULL_REQUEST_TEMPLATE.md` and "Fixes #NNNN".

## Report

One row per check: pass, fail, or not run locally; the command; and the failing output.
