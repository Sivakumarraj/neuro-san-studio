---
name: opportunity-desk-ops
description: "How to change, test, run and deploy the Opportunity Desk network that lives only in this fork: where its parts are, the invariants it must keep, the private profile that never enters git, the local container check, the Render Blueprint, and how to verify a live deploy. Use for any desk change, desk bug, desk deploy, digest or contribution-tracker question."
---

# Opportunity Desk operations

The desk is a personal network: research with checked sources, openings and upstream issues scored
in code, the owner's own pull requests tracked against an escalation ladder, and outreach drafts
gated by contact rules. It is never part of an upstream pull request.

## Where it lives

| Part | Path |
|------|------|
| Network | `registries/experimental/opportunity_desk.hocon` (off in the shared manifest) |
| Deploy manifest | `registries/manifest_opportunity_desk.hocon` — serves only the desk; `Daily scan` at 03:01 UTC |
| Coded tools | `coded_tools/experimental/opportunity_desk/` — one class per file |
| Tests | `tests/coded_tools/experimental/opportunity_desk/` — `FakePageSource`, `DeskTestEnvironment` |
| Fixture | `tests/fixtures/experimental/opportunity_desk/outreach_blocked.hocon` |
| Docs | `docs/examples/experimental/opportunity_desk.md` |
| Deploy | `deploy/opportunity_desk/` (Dockerfile, `start.sh`, Caddyfile) and `render.yaml` |

## Invariants — keep these when changing anything

- Decisions live in code: fit scores, eligibility, evidence verdicts, outreach cadence, the
  contribution ladder and the digest recipient. The agents explain those results; they never decide.
- The owner's profile names real people. It stays outside git (`OPPORTUNITY_DESK_PROFILE`); the
  committed `example_profile.json` is fictional, and a test checks its addresses are example.com.
- The desk sends nothing to anyone; the digest goes only to `OPPORTUNITY_DESK_DIGEST_TO`.
- `start.sh` refuses to start without a `DESK_PASSWORD` of at least 16 characters, and Caddy is the
  only published port: neither nsflow nor the neuro-san server authenticates requests.
- Every fetch goes through `SafeFetch` (via `SafePageSource`).

## Test

```bash
python -m pytest tests/coded_tools/experimental/opportunity_desk -q
python -m neuro_san_studio validate registries/experimental/opportunity_desk.hocon
```

For a change under `deploy/`, run the container flow locally: copy `neuro_san_studio`, `registries`,
`coded_tools`, `middleware`, `skills`, `config`, `logging.hocon` and `deploy/opportunity_desk` into a
folder an unprivileged `desk` user owns; run `start.sh` as root with `PORT`, `DESK_PASSWORD`,
`AGENT_MANIFEST_FILE`, `OPPORTUNITY_DESK_DATA_DIR` and `OPPORTUNITY_DESK_PROFILE` set; then expect
`/healthz` → 200, `/` → 401 without the password and 200 with it, and `/api/v1/list` naming
`experimental/opportunity_desk`. A short password must make it exit with a refusal.

## Deploy on Render

The owner deploys from the dashboard: New > Blueprint, this repository and the desk's branch. Render
asks for `DESK_PASSWORD`, `OPENAI_API_KEY` and the optional SMTP values; then a Secret File named
`profile.json` holds the profile. Keys go into Render, never into a chat. The Render connector can
create a service and set variables, but it cannot attach the disk or the secret file, which is why
the Blueprint is the path.

## Verify a live deploy

With the Render connector: the service's latest deploy is `live`; its logs show
`Found 1 periodic agent` and no `Traceback`; `<service>.onrender.com/healthz` returns 200 and
the root returns 401 without the password. After 03:01 UTC, the audit log (ask the desk for "the audit
log") shows a `scan` and a `contributions_checked` entry.

## Costs

The starter instance and a 1 GB disk are about $7 to $8 a month. Model calls on gpt-5.4-nano are
cents; OpenAI web search is the main variable cost, billed per search call. gpt-5.4-nano and
gpt-5.4-mini retire on 2027-04-01 and the search model's default, gpt-4o, on 2027-01-14 (neuro-san's
model table); move `OPPORTUNITY_DESK_MODEL`, `OPPORTUNITY_DESK_SENIOR_MODEL` and
`OPPORTUNITY_DESK_SEARCH_MODEL` before then.
