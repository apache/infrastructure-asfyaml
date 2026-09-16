# Working in this repository

Instructions for coding agents (and a useful summary for humans). This repo holds
the parser that applies `.asf.yaml` files across the Apache Software Foundation's
GitHub repositories, plus the documentation projects read to write those files.

`CLAUDE.md` and `GEMINI.md` are symlinks to this file — one set of instructions,
whichever name a tool looks for. Edit `AGENTS.md`; never replace a symlink with a
copy, or the three will drift apart.

## The one thing not to get wrong

The parser changes real repository settings. `asfyaml-run` decides which GitHub
repository to act on from **the name of the directory it is pointed at**, so
`--repo /somewhere/airflow` acts on `apache/airflow`.

- Never run `asfyaml-run` against a directory named after a real project.
- Test against a sandbox repository you own, as described in
  [docs/testing-a-change.md](docs/testing-a-change.md).
- Prefer `--noop` (a dry run) until you have a reason not to.
- `asfyaml-validate` only checks the schema and never contacts GitHub. When
  validation is all you need, use it.

## Getting set up

```bash
poetry install
poetry run pytest                          # the test suite
poetry run pre-commit run --all-files      # ruff, ruff-format, mypy, license headers
```

Python 3.10 is the floor; CI runs 3.10 through 3.13.

## Layout

| Path | What lives there |
|---|---|
| `asfyaml/asfyaml.py` | the instance and the `ASFYamlFeature` base class |
| `asfyaml/feature/` | one module per `.asf.yaml` feature |
| `asfyaml/feature/github/` | the `github:` feature, one module per directive group |
| `asfyaml/cli.py` | the `asfyaml-run` and `asfyaml-validate` entry points |
| `tests/` | pytest suite |
| `README.md` | **the user-facing `.asf.yaml` documentation** |
| `docs/ASFYamlFeature.md` | how to write a feature |
| `docs/testing.md` | preview environments, for projects trying out new features |
| `docs/testing-a-change.md` | how to test a change to the parser itself |

## Conventions

- **Tests are not named `test_*.py`.** `pytest` is configured with
  `python_files = "*.py"`, so a test module is named after what it covers —
  `tests/github_rulesets.py`, `tests/cli.py`. A file added as `test_foo.py` will
  run, but it will not match anything else in the directory.
- **New features must be registered.** A subclass of `ASFYamlFeature` is only
  picked up if its module is imported in `asfyaml/feature/__init__.py`.
- **A schema change is a documentation change.** `README.md` is what projects
  actually read; a new or altered directive that is not described there does not
  really exist. Update it in the same PR.
- Python files carry the ASF license header — the `insert-license` pre-commit hook
  adds it.
- Line length is 120 (`ruff`). `ruff format` decides formatting; do not hand-format
  around it.
- `mypy` runs over `asfyaml/` only; `tests/` is excluded.

## Testing a change

Unit tests show that a feature parses its YAML and calls the API it meant to call.
They do not show that GitHub accepts the call, or that the result is the one the
contributor had in mind. For anything that touches the GitHub API, run it against
a sandbox repository as well.

**[docs/testing-a-change.md](docs/testing-a-change.md) is the full process.** In
short, to test your own branch in your own fork:

1. Enable Actions on your fork (GitHub disables them on new forks).
2. Create `<your account>/infrastructure-asfyaml-sandbox` — a throwaway repo you
   own, with a small baseline `.asf.yaml` on `main`.
3. Create a `sandbox` environment in your fork, with a secret
   `ASFYAML_SANDBOX_TOKEN`: a fine-grained token whose repository access is **only**
   that sandbox repo.
4. Push a branch to the sandbox carrying the `.asf.yaml` that exercises your change,
   then run the `Test a change against the sandbox repo` workflow from your fork's
   Actions tab with `ref` set to your branch and `noop` left on. Repeat with
   `noop` off, check the result, and reset the sandbox afterwards.

The sandbox target follows whoever owns the repo the workflow runs in, so a run
from your fork acts on your sandbox with your token. You do not need any access to
the Apache sandbox, and cannot reach it from your fork.

Report what you saw in the pull request. A reviewer who reads "I ran this against
my own sandbox and `required_signatures` appeared under Settings → Branches" has a
far easier job than one starting from nothing.

## Opening a pull request

1. **Work on a branch in your own fork**, not on `main`.
2. **One logical change per PR.** Unrelated cleanups belong in their own PR.
3. **Run the checks before pushing** — `poetry run pytest` and
   `poetry run pre-commit run --all-files`. CI runs the same ones.
4. **Write the commit message for someone who will read it in a year.** A short
   subject line, then prose explaining what problem the change solves and why it
   was solved this way. What the diff does is visible in the diff; why it does it
   is not.
5. **In the PR description**, say what changed, what you tested and how, and
   anything a reviewer needs that isn't in the diff — a setting that has to exist,
   a follow-up you deliberately left out. If you tested against a sandbox, say so
   and link the run.
6. **Open it against `apache/infrastructure-asfyaml`, base `main`**:

   ```bash
   gh pr create --repo apache/infrastructure-asfyaml --base main \
     --head <your account>:<your branch> \
     --title "..." --body-file <file>
   ```

7. Report issues and suggestions as **GitHub issues in this repository**. Do not
   open Jira tickets for this repo.

### If you are an agent

- Do not commit, push, or open a pull request unless you were asked to. Say what
  you would do and let the human decide.
- Show the human the commit message and the PR description before they are used.
  Both are published under their name.
- Do not claim a change was tested unless you ran something and read the output.
  "The tests pass" means you ran them in this session.
