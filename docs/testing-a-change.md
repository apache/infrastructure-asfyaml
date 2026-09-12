# Testing a parser change against the sandbox repo

This page is for people **changing or reviewing the `.asf.yaml` parser itself**.
If you are a project looking to try out a preview feature in your own repository,
see [testing.md](testing.md) instead.

Unit tests prove that a feature parses its YAML and calls the API it means to
call. They do not prove that GitHub accepts the call, or that the result is the
one the contributor had in mind. For that, the parser has to run against a real
repository — which is what
[`apache/infrastructure-asfyaml-sandbox`](https://github.com/apache/infrastructure-asfyaml-sandbox)
is for. It is a throwaway repo: its settings, branch protections, labels and
rulesets exist to be mangled and reset.

The `Test a change against the sandbox repo` workflow
([`.github/workflows/sandbox-test.yaml`](../.github/workflows/sandbox-test.yaml))
takes any version of the parser — including a pull request opened from a fork —
and applies a `.asf.yaml` of your choosing to a sandbox repo.

## Two places this runs

| | In `apache/infrastructure-asfyaml` | In your own fork |
|---|---|---|
| Who dispatches it | a committer, reviewing a PR | you, the author, before asking for review |
| Which sandbox | `apache/infrastructure-asfyaml-sandbox` | `<your account>/infrastructure-asfyaml-sandbox` |
| Whose token | the one infra put on the Apache repo | one you make yourself |
| Which ref | the `pr` input, PR number in the Apache repo | the `ref` input, a branch on your fork |
| Setup needed | none, it's already there | [a few minutes, once](#setting-it-up-in-your-own-fork) |

The sandbox target is not hardcoded: it defaults to the sandbox repo of **whoever
owns the repository the workflow is running in**. So the same workflow file, run
from your fork, acts on your sandbox with your token, and a fork cannot reach the
Apache sandbox through it. Everything below applies to both; the differences are
called out where they matter.

Testing in your own fork first is the polite thing to do — it turns "does this
work?" into "here is what it did", and it spends your GitHub minutes and your
sandbox instead of the project's.

## Before you press the button

> [!WARNING]
> Dispatching this workflow **executes code from the ref you name**, with a token
> that has admin rights on the sandbox repo. For a PR from a fork, that is code
> written by someone outside the project. GitHub restricts `workflow_dispatch` to
> people with write access, and **that person is the security control**: read the
> diff before you run it, and check that the commit SHA recorded in the run
> summary is the one you read. A push to the PR between your review and your
> dispatch changes the code that runs.

Nothing outside the sandbox repo is in the token's reach, but the token is in the
reach of whatever the PR's code does with it. Treat "I ran the sandbox test" as a
statement about a specific commit, not about a PR.

None of this applies to a run in your own fork: the code, the sandbox and the
token are all yours, and there is nobody else's trust to spend. That is the
other reason to self-test first.

## Testing a change, step by step

### 1. Read the diff

Look at the PR as you normally would, and note the head SHA (`Commits` tab, or
`gh pr view <NNN> --json headRefOid`). You will confirm it in step 3.

Self-testing your own branch in your own fork? There is nothing to vouch for —
start at step 2.

### 2. Put the `.asf.yaml` under test on a sandbox branch

The parser reads its configuration from a branch of the sandbox repo, so write
the configuration that exercises the change and push it there. Use the Apache
sandbox if you are a committer reviewing a PR, or your own if you are the author
self-testing:

```bash
git clone https://github.com/apache/infrastructure-asfyaml-sandbox.git   # or <your account>/...
cd infrastructure-asfyaml-sandbox
git switch -c test/pr-42          # convention: test/pr-<PR number>
$EDITOR .asf.yaml                 # the configuration you want to try
git commit -am "Test config for PR #42"
git push origin test/pr-42
```

Keep the configuration minimal — just the feature under test, plus whatever it
depends on. A large `.asf.yaml` makes it harder to attribute a surprising result
to the change.

### 3. Dry run

Go to
[Actions → Test a change against the sandbox repo](../../actions/workflows/sandbox-test.yaml)
→ `Run workflow` and fill in:

| Field | Value |
|---|---|
| Use workflow from | **`main`** — see [Why the dropdown stays on main](#why-the-dropdown-stays-on-main) |
| `pr` | the PR number, e.g. `42`. **In your fork, leave this empty** — see below |
| `ref` | leave as `main` when using `pr`; **in your fork, your branch name** |
| `sandbox_branch` | `test/pr-42` |
| `sandbox_repo` | leave empty — it defaults to your own sandbox |
| `noop` | **`true`** |

`pr` means "a PR in the repository this workflow is running in". In
`apache/infrastructure-asfyaml` that is the PR under review, and it resolves to
`refs/pull/<n>/head`, a ref that exists on the Apache repo even when the PR came
from a fork — which is why a fork PR needs no mirror branch. In your own fork
there are normally no PRs, so name your branch in `ref` instead.

The run summary records the ref, the **commit SHA**, the PR author, the sandbox
branch, and the `.asf.yaml` that was read. **Check the SHA against step 1.**

With `noop` on, the parser reads from the GitHub API and reports what each
feature would do without changing anything. Most mistakes — a bad schema, a
malformed API payload, a feature that never fires — show up here.

### 4. Apply it for real

Dispatch again with the same inputs and `noop` set to `false`.

### 5. Verify on the sandbox repo

Check the thing the change was supposed to affect:

| Feature | Where to look |
|---|---|
| `description`, `homepage`, `labels`, `features` | the sandbox repo's front page and `Settings` |
| `protected_branches`, `protected_tags` | `Settings → Branches`, `Settings → Tags` |
| `rulesets` | `Settings → Rules` |
| `del_branch_on_merge`, `enabled_merge_buttons`, `pull_requests` | `Settings → General` |
| `dependabot_alerts`, `dependabot_updates` | `Settings → Advanced Security` |
| `environments` | `Settings → Environments` |
| `copilot_code_review` | `Settings → Rules`, and a PR in the sandbox |
| `ghp_branch`, `ghp_path` | `Settings → Pages` |
| `collaborators` | `Settings → Collaborators` (invitations are pending until accepted) |
| `autolink_jira` | `Settings → Autolink references` |

### 6. Reset the sandbox

Leaving the sandbox in a mangled state makes the *next* reviewer's result
ambiguous, so put it back:

1. Dispatch the workflow once more with `ref` = `main`, `pr` empty,
   `sandbox_branch` = `main`, `noop` = `false`. This re-applies the baseline
   `.asf.yaml` from the sandbox's main branch. (Resetting your own sandbox
   matters less than resetting the shared one, but stale settings will confuse
   your next run too.)
2. Delete your test branch: `git push origin --delete test/pr-42`.
3. Anything the baseline cannot undo — a created ruleset, a pending collaborator
   invitation, an environment — remove by hand.

### 7. Say so in the PR

Post what you ran, so the next person does not repeat it:

> Sandbox-tested at `abc1234` against `test/pr-42` — `protected_branches` applied
> as expected, `required_signatures` showed up in Settings → Branches.
> Run: <link to the workflow run>

## Setting it up in your own fork

Four things, once, and then every later branch is just a dispatch:

1. **Enable Actions on your fork.** GitHub disables workflows on new forks. Open
   the fork's `Actions` tab and confirm the prompt; the workflow then shows up
   with its `Run workflow` button.
2. **Make yourself a sandbox repo.** Create
   `<your account>/infrastructure-asfyaml-sandbox` — the default name, so you
   never have to fill in `sandbox_repo`. Any repo you own with admin rights will
   do; pass its `owner/name` in `sandbox_repo` if you call it something else.
   Give it a small baseline `.asf.yaml` on `main` so you have something to reset
   to. Keep it public, or the checkout step cannot read it.
3. **Create a `sandbox` environment** in your fork
   (`Settings → Environments → New environment`, named exactly `sandbox`).
4. **Add an `ASFYAML_SANDBOX_TOKEN` secret to that environment**: a fine-grained
   personal access token whose repository access is **only** your sandbox repo,
   with `Administration: read and write` (plus `Contents`, `Pages` or
   `Environments` if you are testing those features). Scope it to that one repo —
   a token with `Administration` on all your repositories is a bad thing to hand
   to a CI job.

Then follow the same steps as above, with `ref` set to your branch instead of
`pr`, and push your test `.asf.yaml` to a branch of *your* sandbox. When you open
the PR, say what you saw — a reviewer who can read "I ran this against my own
sandbox and `required_signatures` appeared in Settings → Branches" has a much
easier job than one starting from scratch.

> [!TIP]
> A run in your fork is not a substitute for the reviewer's run against the
> Apache sandbox — your token, your sandbox settings and your repo's existing
> state all differ. It is there to catch the obvious breakage before anyone else
> spends time on it.

## Testing locally instead

The workflow is a wrapper around one command, and you can run it yourself with a
token of your own:

```bash
git clone https://github.com/apache/infrastructure-asfyaml-sandbox.git
cd infrastructure-asfyaml-sandbox && git switch test/pr-42 && cd ..

git clone https://github.com/apache/infrastructure-asfyaml.git parser
cd parser && gh pr checkout 42 && poetry install

poetry run asfyaml-run \
  --repo ../infrastructure-asfyaml-sandbox \
  --org apache \
  --branch test/pr-42 \
  --noop \
  --token "$GH_TOKEN"
```

Drop `--noop` (or pass `--no-noop`) to apply the changes. `--org` is the owner of
the sandbox you are acting on, so it is your own account when you run this against
your own sandbox.

> [!IMPORTANT]
> **The checkout directory name is the GitHub repo name.** The parser derives the
> repository it acts on from the directory it is given, so
> `--repo /somewhere/infrastructure-asfyaml-sandbox` acts on
> `apache/infrastructure-asfyaml-sandbox`. Renaming the directory points the run
> at a different repo — including, if you get it wrong, a real project's.

To check only that a configuration is valid, without contacting GitHub at all:

```bash
poetry run asfyaml-validate --repo ../infrastructure-asfyaml-sandbox --branch test/pr-42
```

## Things that surprise people

### Why the dropdown stays on main

`workflow_dispatch` runs the *workflow definition* from the branch chosen in the
`Use workflow from` dropdown. Leaving it on `main` means the steps that handle
the token come from reviewed code, while the parser under test is checked out as
data. Selecting a PR branch there would let that PR rewrite the runner itself.

### Branch-scoped and repo-scoped settings behave differently

`sandbox_branch` decides which branch's `.asf.yaml` is *read*, and which branch
the parser believes it is processing. Features keyed on the branch — website
staging and publishing, `whoami`, Pelican and Jekyll builds — only fire when the
branch matches. Repository metadata under `github:` is not branch-scoped: it
applies to the whole repo no matter which branch it was read from. So a
`description:` change takes effect even when read from `test/pr-42`, while a
`publish:` block may do nothing at all.

### `noop` is not offline

A dry run still authenticates and reads from the GitHub API — that is how it can
report what *would* change. It only suppresses the writes.

## One-time setup for the Apache repo (infra)

The workflow needs these to exist in `apache/infrastructure-asfyaml`. They are
outside this repository:

1. **The sandbox repo**, `apache/infrastructure-asfyaml-sandbox`, public, with a
   baseline `.asf.yaml` on `main` that represents "settings at rest". Keep the
   baseline small and boring; step 6 above resets to it.
2. **A `sandbox` environment** on `apache/infrastructure-asfyaml`
   (`Settings → Environments`). Required reviewers can be added here if
   committer-only dispatch is judged too weak a gate.
3. **A secret `ASFYAML_SANDBOX_TOKEN`** on that environment: a fine-grained
   personal access token, or a GitHub App installation token, whose repository
   access is **only** `apache/infrastructure-asfyaml-sandbox`. Grant the
   permissions the features under test need — `Administration: read and write`
   covers most repository settings, with `Contents`, `Pages` and `Environments`
   for the features that use them. Do not use a token with access to other
   repositories in the org.

The workflow fails with a clear message when the secret is missing, so a
half-finished setup is not silently a no-op.
