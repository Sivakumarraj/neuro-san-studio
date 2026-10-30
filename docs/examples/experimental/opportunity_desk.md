# Opportunity Desk

The **Opportunity Desk** is a personal desk of small specialist agents. It researches questions and checks
every quoted claim against its source, finds openings and open-source issues that fit its owner and tracks
them, and drafts outreach that must pass the owner's own rules before anyone sees it. It never sends
anything: the owner does.

---

## File

[opportunity_desk.hocon](../../../registries/experimental/opportunity_desk.hocon)

---

## Description

Four rules shape the network:

* **Small specialists on a cheap model.** Each agent does one job on `gpt-5.4-nano`. Only the senior analyst
  runs a stronger model, and only after an evidence check fails.
* **Decisions in code.** Fit scores, eligibility, evidence verdicts, outreach cadence and the digest
  recipient are decided in Python. The agents explain those decisions and never make them.
* **Stop instead of guessing.** A claim whose quote cannot be found at its source is reported as
  unverified. A blocked draft is not rewritten to get around the block.
* **Nothing leaves without the owner.** Drafts come back ready to copy. The only email the desk sends is the
  digest, to the address in the environment, which no prompt can change.

| Agent | Kind | What it does |
|---|---|---|
| `desk_lead` | LLM, front man | Routes each request with AAOSA claims and composes the answer |
| `research_analyst` | LLM | Searches, reads pages, writes claims with verbatim quotes, runs the evidence check |
| `senior_analyst` | LLM, stronger model | Re-researches a question whose evidence check returned `ESCALATE` |
| `opportunity_scout` | LLM | Scans boards, shows and updates the pipeline, sends the digest |
| `outreach_writer` | LLM | Drafts messages and records what the owner sent or received |
| `board_scanner` | Coded tool | Reads boards and repositories, scores postings, stores the new ones |
| `pipeline_tracker` | Coded tool | Lists, updates and audits the pipeline; status values are checked in code |
| `digest_sender` | Coded tool | Emails the owner the matches found since the last delivered digest |
| `evidence_checker` | Coded tool | Fetches each cited page and checks the quote is on it; returns the verdict |
| `outreach_gate` | Coded tool | Checks a draft against the contact's status, the cadence and the wording rules |
| `outreach_recorder` | Coded tool | Records a message the owner sent or received |

Web search (`ddgs_search`, no key needed), arXiv search and page reading come from the
[toolbox](../../toolbox.md). Every page the desk fetches goes through the studio's SSRF-hardened `SafeFetch`.

### Evidence check and escalation

The researcher has to back every claim with a quote of at least six words copied from a page it read.
`evidence_checker` fetches each page and looks for the quote after normalizing case, punctuation and
markup. A dropped word still matches; a paraphrase does not. When the share of verified claims falls below
the profile's `evidence_threshold` (default 0.7), the verdict is `ESCALATE` and the question goes to the
senior analyst. This is the red-flag idea from the MAKER paper
([Meyerson et al., 2025](https://arxiv.org/abs/2511.09030)) applied to sources rather than steps: a cheap
model's answer is accepted only when a check written in code says it holds.

The check proves the quoted text is on the cited page. It does not prove the claim follows from that text.

### Fit scoring

`FitAssessor` scores a posting out of 100 from skills named as whole words, a target title, an accepted
location and an entry-level signal, with a reason for every point. Hard requirements make a posting
ineligible whatever its score: more years of experience than the owner's limit, a graduation batch that
excludes the owner, a senior title, or a term the owner excluded. Open issues in tracked repositories are
scored on skills alone.

The scoring is keyword-based on purpose: every point is traceable. It will miss a posting that describes a
skill in other words.

### Outreach rules

Every contact has a status in the profile:

| Status | Meaning |
|---|---|
| `open` | Normal rules apply |
| `technical_only` | No hiring language at all (job, referral, opening, resume and similar) |
| `reply_only` | Write only after they have written to you |
| `do_not_contact` | Nothing is drafted |

For every status, at most `max_unanswered` messages may go out in a row without a reply (default 1: send
one, then wait), and a permitted follow-up still waits `cooldown_days`. Drafts over `max_words`, with
markdown (which email and LinkedIn show literally) or with a banned phrase are refused. The gate reads the
history listed in the profile plus everything recorded since, so tell the desk when you send or receive a
message.

---

## Data sources

Only sources that permit automated reading are used:

* **Careers boards** on Greenhouse, Lever and Ashby, through the public job-board endpoints those providers
  document for embedding a careers page. List the employers you want under `boards`.
* **Open issues** in the repositories under `contribution_repos`, through the GitHub REST API (60
  unauthenticated requests an hour).

LinkedIn and Naukri forbid automated access in their terms and are deliberately not supported. Their own
job-alert emails are the lawful way to follow them.

---

## The profile

The owner's profile is a private JSON file named by `OPPORTUNITY_DESK_PROFILE`. It holds real names and
addresses, so it never goes in the repository. Without it, the fictional
[example_profile.json](../../../coded_tools/experimental/opportunity_desk/example_profile.json) is used and
the desk says so in every scan.

```json
{
    "owner": {"graduation_year": 2025, "max_experience_years": 1},
    "skills": ["python", "fastapi", "rag", "llm"],
    "target_titles": ["ai engineer", "ml engineer"],
    "locations": ["bengaluru", "remote"],
    "boards": [{"provider": "greenhouse", "slug": "<board slug>", "company": "<name>"}],
    "contribution_repos": [{"repo": "cognizant-ai-lab/neuro-san-studio", "labels": ["good first issue"]}],
    "outreach": {"max_unanswered": 1, "cooldown_days": 7, "max_words": 180, "banned_phrases": []},
    "contacts": {
        "<contact id>": {
            "name": "<name>",
            "email": "<address>",
            "status": "open",
            "history": [{"direction": "sent", "happened_on": "2026-10-01"}]
        }
    }
}
```

A board slug is the last part of the employer's careers URL: `boards.greenhouse.io/<slug>`,
`jobs.lever.co/<slug>` or `jobs.ashbyhq.com/<slug>`.

---

## Running it locally

Set `OPENAI_API_KEY`, point `OPPORTUNITY_DESK_PROFILE` at your profile, and serve the desk alone:

```bash
export AGENT_MANIFEST_FILE=registries/manifest_opportunity_desk.hocon
python -m neuro_san_studio run
```

The tracker is a SQLite file under `logs/opportunity_desk/` (set `OPPORTUNITY_DESK_DATA_DIR` to move it).
The network is off in the shared manifest because it needs a profile to be useful.

To use other models, set `OPPORTUNITY_DESK_MODEL` and `OPPORTUNITY_DESK_SENIOR_MODEL` to any model name
neuro-san knows, with the matching provider key.

---

## Running it in the cloud

[deploy/opportunity_desk/](../../../deploy/opportunity_desk/) builds one container with the neuro-san
server and the nsflow client on localhost, and Caddy in front of them on `$PORT`. Neither nsflow nor the
neuro-san server authenticates requests, so Caddy asks for a password on everything except `/healthz`.
`start.sh` refuses to start when `DESK_PASSWORD` is shorter than 16 characters, hashes it for Caddy, and
removes it from the environment before the agents start. It starts as root only to hand the mounted disk
to an unprivileged user.

The manifest [manifest_opportunity_desk.hocon](../../../registries/manifest_opportunity_desk.hocon) serves
only this network and uses neuro-san's `periodic` scheduler to send `Daily scan` every day at 03:01 UTC.
The scan and the digest are coded tools, so a scheduled run costs only the agents' routing.

On Render, [render.yaml](../../../render.yaml) describes the service:

1. In the Render dashboard, choose **New > Blueprint**, pick this repository and the branch to deploy.
2. Enter the values Render asks for: `DESK_PASSWORD`, `OPENAI_API_KEY`, and the SMTP settings if you want
   the digest emailed (with Gmail, an app password).
3. Under the service's **Environment** tab, add a **Secret File** named `profile.json` with your profile.
4. Open the service URL and sign in as `owner` with your password.

The starter instance has 512 MB of memory; the desk used about 265 MB at idle when measured. The disk keeps
the tracker across deploys.

The neuro-san server listens on port 8080 on every interface. Render routes public traffic only to
`$PORT`, but other services in the same Render workspace can reach port 8080 over the private network, so
keep untrusted services out of that workspace.

---

## Example conversations

* "Scan my boards and show me the best new matches."
* "Move greenhouse:acme:4011 to applied."
* "What does the MAKER paper propose, with sources?"
* "I received a reply from example-recruiter today; record it, then draft an answer about the evidence
  checker."

---

## Tests

Unit tests for every coded tool are in
[tests/coded_tools/experimental/opportunity_desk/](../../../tests/coded_tools/experimental/opportunity_desk/),
with recorded board responses in place of the network. The integration fixture
[outreach_blocked.hocon](../../../tests/fixtures/experimental/opportunity_desk/outreach_blocked.hocon) checks
that a draft to a `do_not_contact` contact comes back refused, with no draft.
