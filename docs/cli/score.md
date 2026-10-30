# score

Runs a network's fixtures several times and reports how often it passes and what each answer costs. With a second
network it runs both on the same fixtures and tests whether the difference in pass rate is larger than run-to-run
noise. It only reads networks and fixtures; it never changes them. To repair a failing network, use
[`consultant`](./consultant.md).

## Usage

The HOCON path is relative to `registries/`. Fixtures come from `tests/fixtures/<network>/`, the same folder
`consultant` uses.

```bash
ns score --hocon-file industry/intranet_agents.hocon --repeats 5
```

Compare a second network on the first network's fixtures, and keep the full report:

```bash
ns score \
  --hocon-file industry/intranet_agents.hocon \
  --compare-hocon-file generated/intranet_agents_v2.hocon \
  --repeats 5 \
  --output intranet_score.json
```

Run a subset with `--only-fixtures`, as in `consultant`:

```bash
ns score \
  --hocon-file industry/intranet_agents.hocon \
  --only-fixtures employee_policy.hocon employee_benefits.hocon
```

Every attempt makes real LLM calls, so the cost of a run is about the reported mean cost per question times the
number of fixtures, times `--repeats`, times two when comparing.

## Options

| Option | Description |
|---|---|
| `--hocon-file` | The network whose fixtures are run. Required. |
| `--compare-hocon-file` | A second network to run on the same fixtures and compare against the first. |
| `--repeats` | Attempts per fixture. Defaults to `3`. Every attempt runs; there is no early stop. |
| `--only-fixtures` | Run a space-separated list of exact fixture filenames, including `.hocon`. |
| `--output` | Write the full report as JSON to this file. |

## What it reports

For each network:

- **Pass rate over all attempts.** A fixture's `success_ratio` stops its test once enough attempts pass, which
  hides later failures. `score` runs every attempt and counts each one. The fixture files are not changed.
- **Mean cost per question** and **cost per correct answer** (total spend divided by passing attempts), from the
  token accounting Neuro SAN reports at the end of each interaction. Attempts that report none, such as timeouts,
  are left out of the cost figures, and the report says how many attempts had a cost.
- One line per fixture with its passes, attempts and mean cost.

When comparing, attempt *i* of each fixture on the first network is paired with attempt *i* on the second. Only
pairs where exactly one network passed carry information. The report gives both counts and an exact two-sided sign
test on them: the chance of a split at least that lopsided if the two networks were equally good. A small p-value,
such as below 0.05, means the difference is unlikely to be noise. A large one means these runs cannot tell the two
apart; it does not mean they are equal.

## Notes

- To collect token accounting, interactions without their own `chat_filter` run with `MAXIMAL`. Grading reads only
  the final answer, so this does not change a verdict. A fixture that sets its own `chat_filter` keeps it, and its
  attempts may report no cost.
- Cost is only as complete as Neuro SAN's token counting. LLM calls that the counter does not see, for example inside
  some coded tools, are not included.
- Like `consultant`, `score` runs in a child process with the project's direct-test environment, from the project
  root.
