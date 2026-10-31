# Tools registry

Agents and skills reference a tool by its **role**, never by a hard tool name. When the preferred
tool is unavailable, fall back to the alternative. Reviewed on the dates below.

| Role | Preferred tool | Alternative (if unavailable) | Status | Last reviewed |
|------|----------------|------------------------------|--------|---------------|
| upstream-reader | `git fetch upstream main` for code and history; logged-out github.com issue and PR pages through a web-fetch tool | the GitHub REST API (api.github.com/repos/cognizant-ai-lab/...) through a web-fetch tool; in cloud sessions the GitHub connector reaches only the owner's forks | active | 2026-10-31 |
| fork-github | GitHub connector for Sivakumarraj/neuro-san-studio (Actions runs and logs, branches) | `git push` / `git fetch` against `origin` | active | 2026-10-31 |
| python-env | `venv` with `pip install -r requirements.txt -r requirements-build.txt` | none — without the pinned versions, results do not match CI | active | 2026-10-31 |
| link-checker | CI's lychee 0.24.1 (`.github/workflows/tests.yml`) | `preflight-gate/scripts/link_check.py`, which applies `.lycheeignore` and the example-domain rule offline; downloading lychee locally was refused by a session permission policy | active | 2026-10-31 |
| dockerfile-linter | CI's hadolint (quality gate) | none locally — keep Dockerfiles minimal and read CI's result | active | 2026-10-31 |
| deploy-host | Render dashboard Blueprint from `render.yaml` | the Render connector: creates web services and sets variables, but cannot attach a disk or a secret file | active | 2026-10-31 |
