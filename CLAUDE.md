@AGENTS.md

## Harness: upstream contributions and the Opportunity Desk (this fork only)

**Goal:** small, merge-ready contributions to cognizant-ai-lab's neuro-san repositories, and upkeep of the
Opportunity Desk network that exists only in this fork.

**Issue tracking:** GitHub Issues on cognizant-ai-lab/neuro-san-studio, neuro-san and nsflow. The orchestrator
reads ready work from open, unassigned issues; every write upstream (an issue, a comment, a pull request) is
human-gated: the owner posts it.

**Entry point — applies to every prompt in this repo:** You MUST invoke the `contrib-orchestrator` skill *before*
responding to any request — new work, a follow-up, a re-run, a question, or a change to a previous result. It is
the single entry point; do not craft a response outside it. The orchestrator decides what happens next: it answers
trivial or out-of-domain requests directly and runs the agents only when the work warrants it.

This section and `.claude/` exist only in the owner's fork. Upstream branches are cut from `upstream/main`, so they
never carry either.

**Change history:**

| Date | Change | Target | Reason |
|------|--------|--------|--------|
| 2026-10-31 | Initial setup | All | No harness existed; a stale fork and fixture URLs broke CI |
| 2026-10-31 | Assignment means ask first | scout agent and skills, rules | Upstream self-assigns issues |
