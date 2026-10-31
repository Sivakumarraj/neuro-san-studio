---
name: contrib-orchestrator
description: "Entry point for all work in this fork of neuro-san-studio — invoke before responding to any request here. Turns a request into a small, merge-ready contribution to cognizant-ai-lab/neuro-san-studio, neuro-san or nsflow (find an issue, fix it, pass the same gate CI runs, package the pull request for the owner to post), or into a tested change to the Opportunity Desk network. Use for: find an issue, next contribution, fix #1528, prepare a PR, sync the fork, why is CI red, change the desk, deploy the desk. Follow-ups: re-run, update the PR, address review comments, fix the previous result, supplement, improve."
model: inherit
---

# Contribution orchestrator

Coordinates the issue-scout, contribution-builder and preflight-qa agents so that every change
leaving this fork is small, correct, and passes upstream's checks before anyone sees it.

## Execution mode: subagent

The agents work in sequence and only the combined result matters, so each is spawned with the
`Agent` tool (`subagent_type: general-purpose`) and returns a file in the workspace. There is no
agent team.

## Agents

| Agent | Role | Skills | Output |
|-------|------|--------|--------|
| issue-scout | Finds and ranks the next mergeable upstream issue | issue-scouting, contribution-rules | `logs/agents_workspace/1_scout_target.md` |
| contribution-builder | Implements the change and packages it | contribution-rules, preflight-gate, opportunity-desk-ops | `logs/agents_workspace/2_build_summary.md` |
| preflight-qa | Runs CI's gate and the hygiene checks across boundaries | preflight-gate, contribution-rules | `logs/agents_workspace/3_qa_report.md` |

The workspace lives under `logs/`, which git already ignores, so nothing in it is ever committed.

## Workflow

### Phase 0: intake and triage (always first — this skill is the repo's entry point)

1. **Triage.** A greeting, a question about the code, or anything outside contributions and the
   desk: answer directly and stop. A status question ("how are my pull requests doing?"): answer
   from upstream's pages or the desk's contribution tracker and stop.
2. **Classify** in-domain work: (a) an upstream contribution, (b) a desk change, (c) a CI failure.
3. **Context check.** If `logs/agents_workspace/` exists and the request refers to it (re-run,
   update the PR, address review comments), this is a follow-up: reuse the files and re-run only
   the phase that changes. Otherwise move the old workspace to `logs/agents_workspace_<date>/`.
4. **Tracker: GitHub Issues upstream.** Read ready work from the open, unassigned issues (the
   `upstream-reader` role in `references/tools.md`). Every write to upstream — an issue, a comment,
   a pull request — is human-gated: prepare the text, show it, and stop. The owner posts it. Carry
   the issue number (`#NNNN`) through the run; never copy issue text into the workspace.

### Phase 1: prepare

- Sync before anything else, because a stale fork is what turned 105 tests red in October 2026:
  `git fetch upstream main`, adding `https://github.com/cognizant-ai-lab/neuro-san-studio` as the
  `upstream` remote if it is missing. Install the pinned requirements into the venv when they changed.
- Upstream work: branch from `upstream/main` as `fix/<NNNN>-<short-name>` (or `docs/...`,
  `feature/...`). A branch cut from `upstream/main` cannot carry fork-only files such as `.claude/`
  or the desk.
- Desk work: stay on the branch that carries the desk.

### Phase 2: scout (upstream work without a named issue)

Spawn issue-scout. Show the owner its first choice and runner-up, and wait for their pick: their
name goes on the pull request, so they choose the work.

### Phase 3: build

Spawn contribution-builder with the chosen issue (or the desk request) and the target brief.

### Phase 4: preflight QA

Spawn preflight-qa on the branch. On any failure, send the report back to contribution-builder and
re-run QA; after two failed rounds, stop and report what still fails, with the output.

### Phase 5: finish

- Upstream work: give the owner the branch, the compare link
  (github.com/cognizant-ai-lab/neuro-san-studio/compare/main...Sivakumarraj:<branch>), the
  pull-request body filled from `.github/PULL_REQUEST_TEMPLATE.md` with "Fixes #NNNN", and the
  builder's owner briefing. Push the branch only after the owner says to; the owner opens the PR.
- Desk work: commit and push to the desk branch after QA passes, then report CI's result.
- Keep `logs/agents_workspace/`; summarize in a few lines.

## Error handling

- An agent fails: retry once; on a second failure, continue without its result and say what is
  missing.
- Conflicting results (QA says a check fails that the builder says passed): keep both reports with
  their sources and trust the command output, not the claim.
- Upstream unreachable: use the alternative for that role in `references/tools.md`; if none works,
  stop before building rather than working from a stale picture.

## Test scenarios

1. "Find me something to contribute" → scout ranks; the owner picks; build; QA; package. No push.
2. "Fix #1528" → no scouting; branch `fix/1528-...` from `upstream/main`; QA passes; package.
3. "CI is red on my branch" → read the failing job's log first; if the fork is behind upstream,
   sync; otherwise route the failure to the builder with the log.
4. "Add a board to the desk" → desk path; the private profile is not in the repository, so the
   change is to code, docs or the example profile only.
5. "What is AAOSA?" → answered directly in phase 0; no agents.
