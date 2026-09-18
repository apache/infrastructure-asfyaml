---
name: sandbox-test
description: >
  Test a change to the .asf.yaml parser against a real GitHub repository, using the
  "Test a change against the sandbox repo" workflow. Covers one pull request, a local
  branch, or a batch of open PRs. Builds a set/update/unset test matrix, runs it noop
  then live, verifies every claim by reading the GitHub API back, resets the sandbox,
  and then proposes a review comment and a disposition for the human to approve.
  Invoke when asked to "sandbox-test this", "test PR NNN against the sandbox", "does
  this actually work on GitHub", "test the open PRs", or before approving or merging
  any PR that touches asfyaml/feature/.
---

# Testing a parser change against a sandbox repo

Unit tests prove a feature parses its YAML and calls the API it meant to call. They do
not prove GitHub accepts the call, or that the result is the one the contributor had in
mind. Three of the bugs this skill exists to catch passed their unit tests and exited 0
while changing nothing on GitHub.

[docs/testing-a-change.md](../../../docs/testing-a-change.md) is the reference for the
workflow itself. This skill is the procedure to run around it.

## The rule that matters most

**A green run is not a result. Reading the setting back from the GitHub API is the
result.** The parser can print "Setting X to Y", exit 0, and have changed nothing —
that is exactly what a broken state check looks like. Every claim you make must trace
to an API response you read after the run, not to a log line and not to an exit code.

## Safety

- **Never point `asfyaml-run` at a directory named after a real project.** The parser
  derives the target repository from the directory name, so `--repo /tmp/airflow` acts
  on `apache/airflow`. The sandbox directory must be named after the sandbox repo.
- **Read the diff before you dispatch.** Dispatching executes the PR's code with a
  token holding admin rights on the sandbox. For a PR from a fork that is code from
  outside the project, and the person dispatching is the security control. Read it,
  and check the commit SHA in the run summary matches what you read.
- **Never dispatch someone else's PR against the Apache sandbox to "see what happens".**
  Self-test in your own fork first; it spends your minutes and your sandbox.

## 1. Pick a sandbox

| | Your own fork | `apache/infrastructure-asfyaml` |
|---|---|---|
| Who runs it | any contributor | committer or infra admin |
| Sandbox | `<you>/infrastructure-asfyaml-sandbox` | `apache/infrastructure-asfyaml-sandbox` |
| Token | one you make | the one infra installed |
| Ref input | `ref` = your branch | `pr` = the PR number |
| Setup | below, once | already done |

The sandbox defaults to the sandbox repo of whoever owns the repo the workflow runs in,
so a fork run cannot reach the Apache sandbox.

**Prefer your own fork.** Use the Apache sandbox only when the feature cannot work
anywhere else — some settings are org-only. Merge queue rules, for example, are rejected
outright on a user-owned repository, and no amount of parser fixing changes that.

### One-time setup in your own fork

1. Enable Actions on the fork (GitHub disables them on new forks).
2. Create `<you>/infrastructure-asfyaml-sandbox`, public, with a small baseline
   `.asf.yaml` on `main`. Keep a `baseline` branch pointing at that commit — resetting
   is then one push.
3. Create an environment named exactly `sandbox` in the fork.
4. Add secret `ASFYAML_SANDBOX_TOKEN` to that environment: a fine-grained PAT whose
   **repository access is only the sandbox repo**.

Token permissions, by what you are testing:

| Feature under test | Permission |
|---|---|
| most repository settings, rulesets, autolinks, interaction limits, branch protection | `Administration: Read and write` |
| deployment environments | `Environments: Read and write` |
| Pages | `Pages: Read and write` |
| pushing test branches to the sandbox | `Contents: Read and write` |

A 403 saying `Resource not accessible by personal access token` almost always means the
token's *repository access list* is wrong, not its permission level — check which repo it
was granted before re-reading the permission checkboxes.

## 2. Preflight the branch

Do all of this before dispatching anything.

1. **Check the branch can run at all.** The workflow calls `asfyaml-run --branch ...`,
   and that flag arrived with the sandbox workflow itself. Any branch cut before then
   dies with `unrecognized arguments: --branch`:

   ```bash
   git show <ref>:asfyaml/cli.py | grep -q -- '--branch' || echo "needs rebase onto main"
   ```

2. **Rebase onto current `main` if needed.** For someone else's PR, push the rebase to a
   branch in *your* fork (`sandbox-test/pr-<NNN>`) — never to the contributor's branch.
3. **Run the suite and the hooks** on the rebased tree: `poetry run pytest` and
   `poetry run pre-commit run --all-files`. Report what you ran, not what you assume.
4. **Read the diff of the directive**, both for the security reason above and because
   you cannot design a test matrix for code you have not read.

## 3. Build the test matrix

A single "does it turn on" run is not a test of a directive. Most `.asf.yaml` directives
are declarative, so the interesting behaviour is at the edges. Cover every row that
applies:

| Case | Config | What it proves |
|---|---|---|
| **Set** | key present, feature off beforehand | the enable path works |
| **Update** | key present with a *different* value | the change path works, not just create |
| **Idempotent re-apply** | same config twice | no redundant write on the second run |
| **Unset (explicit)** | `enabled: false`, feature **on** beforehand | the disable path works |
| **Unset (removal)** | key deleted, feature **on** beforehand | removal disables what the file used to manage |
| **Unmanaged** | key never present, feature **on** beforehand | the directive leaves alone what it does not manage |
| **No match / negative** | something the config should *not* touch | scoping is right |

Rules for building it:

- **Choose values that cannot be confused with the starting state.** If the setting is
  already `5`, test with `7`. A test whose pass state equals its start state proves
  nothing.
- **Seed the "before" state deliberately.** For the unset and unmanaged rows the feature
  must be *on* before the run, otherwise a no-op looks like a success. Set it by hand
  through the API first.
- **Seed things the directive must not touch.** An unrelated autolink, a branch that
  matches no pattern, a ruleset the config does not mention.

### The two traps that make an edge case silently untestable

**`github:` directives only run on the default branch.** `feature/github/__init__.py`
returns early unless the branch being processed equals the repository's default branch,
and in a workflow checkout that resolves to `main`. So `sandbox_branch: test/pr-42` makes
every `github:` directive a no-op and the run still goes green. **Put the test config on
the sandbox's `main`** and reset afterwards. The workflow warns when `sandbox_branch` is
anything else; treat that warning as "this run proved nothing", not as a style note.

**`previous_yaml` is empty in every sandbox and CI run.** It is read from a cache at
`/x1/asfyaml`, which exists only in production. Any directive branch guarded by "was this
key in the previous `.asf.yaml`" cannot be exercised here — say so rather than claiming
coverage.

That second trap is also a recurring *bug* source, so check for this shape while reading
the diff:

```python
if not enabled and not was_previously_configured:
    return
```

It means an explicit `false` cannot turn off a setting that is currently on, whenever the
cache is cold or the setting was enabled outside `.asf.yaml`. It has been found in more
than one directive. Test the **unset (explicit)** row specifically to catch it.

## 4. Run it

1. Record the before state from the API, in full, for everything the run should and
   should not touch.
2. Dispatch with `noop: true`. Read the whole apply step — `grep` with a tight `tail`
   will truncate the interesting lines. Check it names every change you expect.
3. Dispatch with `noop: false`.
4. **Read the state back from the API.** Compare against the before state field by field.
5. Repeat per matrix row, resetting in between when a row needs a different start state.

Some settings take time to settle — CodeQL default setup reports `languages: []` until
its setup workflow finishes. If a field looks wrong immediately after a write, wait for
any triggered run in the sandbox to complete and read again before calling it a bug.

### When a run fails, find out whose fault it is

Before attributing a failure to the PR, **send the same request to GitHub yourself**,
by hand, bypassing the parser:

```bash
gh api -X POST repos/<you>/infrastructure-asfyaml-sandbox/<endpoint> --input payload.json
```

If a hand-written payload fails identically, the parser is not the problem — the feature
is unavailable in this environment, and the PR needs an org-owned sandbox. If it
succeeds, the parser's payload is wrong and you have the diff to prove it. Also probe the
endpoint's *read* semantics: several GitHub endpoints return `200` with a body field
rather than the `404`-means-off behaviour a directive might assume.

## 5. Reset the sandbox

Leaving state behind makes the next run's result ambiguous. Undo everything:

- push `baseline` over `main` (`git push origin baseline:main --force`)
- delete created rulesets, autolinks, environments, branch protections and test branches
- turn off anything the baseline cannot turn off — the parser may be unable to disable
  what it enabled, which is precisely one of the bugs being hunted
- confirm the reset by reading the API, the same way you confirmed the change

## 6. Propose a comment

Draft it, show it, **wait for explicit approval, then post**. Never post unprompted.

A good comment contains:

- what was tested, at which **commit SHA**, against which sandbox, with **run links**
- a before/after table of actual API values, not prose
- whether the branch needed a rebase to run at all
- which matrix rows could **not** be covered, and why (the cache, org-only features)
- findings, each with the evidence that supports it and a concrete suggested fix

State plainly when a failure is not the PR's fault. "GitHub rejects this identically for
a hand-written payload" saves the author a day.

## 7. Propose a disposition

Recommend one, with the reasoning, and let the human decide:

| Disposition | When |
|---|---|
| **Approve** | matrix passes, docs updated, tests present |
| **Approve with follow-up** | works, but a non-blocking gap worth an issue |
| **Request changes** | a matrix row fails, or a finding needs a code change |
| **Needs committer run** | blocked only by a limitation of a personal sandbox |
| **Needs author input** | the premise did not reproduce; ask before judging |

Remember a schema change is a documentation change: a directive not described in
`README.md` is not finished.

### Merging

Merge only when **all** of these hold:

1. the human explicitly approved the merge in this session,
2. they have merge permission on `apache/infrastructure-asfyaml`,
3. the sandbox result was verified by reading the API, not by a green run,
4. CI is green on the head commit you tested, and that commit is still the PR head.

Check the last one immediately before merging — a push between the test and the merge
invalidates the result. If any condition fails, say which and stop.
