# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""Tests for the input resolution in the sandbox test workflow.

The workflow hands what this step resolves to `actions/checkout` and to shell
arguments, so the validation here is what keeps a dispatch from turning into
arbitrary code or ref injection. It also decides which repository the run is
allowed to modify, which is what keeps a fork's run inside the fork's own
sandbox. These tests run the step's script the way the runner would.
"""

import subprocess

import pytest
import yaml

WORKFLOW = "../.github/workflows/sandbox-test.yaml"


def resolve_script(base_path):
    """Extracts the 'run' script of the workflow's input resolution step."""
    workflow = yaml.safe_load(base_path.joinpath(WORKFLOW).read_text())
    steps = workflow["jobs"]["sandbox-test"]["steps"]
    step = next(s for s in steps if s.get("id") == "resolve")
    return step["run"]


def run_resolve(
    base_path,
    tmp_path,
    pr="",
    ref="main",
    sandbox_branch="main",
    sandbox_repo="",
    owner="apache",
):
    """Runs the resolution script, returning (exit code, resolved outputs)."""
    output_file = tmp_path / "github_output"
    output_file.touch()
    result = subprocess.run(
        ["bash", "-c", resolve_script(base_path)],
        env={
            "PATH": "/usr/bin:/bin",
            "PR": pr,
            "REF": ref,
            "SANDBOX_BRANCH": sandbox_branch,
            "SANDBOX_REPO": sandbox_repo,
            "REPO_OWNER": owner,
            "GITHUB_OUTPUT": str(output_file),
        },
        capture_output=True,
        text=True,
    )
    outputs = {}
    for line in output_file.read_text().splitlines():
        key, _, value = line.partition("=")
        outputs[key] = value
    return result.returncode, outputs


def test_pr_number_resolves_to_the_pull_request_head(base_path, tmp_path):
    code, outputs = run_resolve(base_path, tmp_path, pr="42")
    assert (code, outputs["ref"]) == (0, "refs/pull/42/head")


def test_ref_is_used_when_no_pr_is_given(base_path, tmp_path):
    code, outputs = run_resolve(base_path, tmp_path, ref="feat/my-branch")
    assert (code, outputs["ref"]) == (0, "feat/my-branch")


def test_sandbox_branch_may_contain_slashes(base_path, tmp_path):
    assert run_resolve(base_path, tmp_path, pr="42", sandbox_branch="test/pr-42")[0] == 0


@pytest.mark.parametrize(
    "pr",
    ["abc", "42; whoami", "42/head", "-1", "4 2", "$(whoami)"],
)
def test_a_pr_that_is_not_a_plain_number_is_rejected(base_path, tmp_path, pr):
    assert run_resolve(base_path, tmp_path, pr=pr)[0] != 0


@pytest.mark.parametrize(
    "ref",
    ["main; whoami", "$(whoami)", "main\nref=refs/pull/1/head", "main branch", "`whoami`"],
)
def test_a_ref_with_shell_or_newline_characters_is_rejected(base_path, tmp_path, ref):
    assert run_resolve(base_path, tmp_path, ref=ref)[0] != 0


@pytest.mark.parametrize(
    "sandbox_branch",
    ["main; whoami", "$(whoami)", "main\nref=refs/pull/1/head", ""],
)
def test_an_invalid_sandbox_branch_is_rejected(base_path, tmp_path, sandbox_branch):
    assert run_resolve(base_path, tmp_path, pr="42", sandbox_branch=sandbox_branch)[0] != 0


def test_setting_both_pr_and_a_non_default_ref_is_rejected(base_path, tmp_path):
    assert run_resolve(base_path, tmp_path, pr="42", ref="some-branch")[0] != 0


# The sandbox target follows the repo the workflow runs in, so that a fork's run
# acts on the fork owner's sandbox rather than on the Apache one.


def test_sandbox_defaults_to_the_sandbox_of_the_owner_running_the_workflow(base_path, tmp_path):
    code, outputs = run_resolve(base_path, tmp_path, owner="apache")
    assert code == 0
    assert outputs["sandbox_repo"] == "apache/infrastructure-asfyaml-sandbox"
    assert outputs["sandbox_owner"] == "apache"
    assert outputs["sandbox_dir"] == "infrastructure-asfyaml-sandbox"


def test_a_fork_defaults_to_the_fork_owners_sandbox(base_path, tmp_path):
    code, outputs = run_resolve(base_path, tmp_path, owner="somecontributor")
    assert code == 0
    assert outputs["sandbox_repo"] == "somecontributor/infrastructure-asfyaml-sandbox"
    assert outputs["sandbox_owner"] == "somecontributor"


def test_an_explicit_sandbox_repo_overrides_the_default(base_path, tmp_path):
    code, outputs = run_resolve(
        base_path, tmp_path, owner="somecontributor", sandbox_repo="somecontributor/my-test-repo"
    )
    assert code == 0
    assert outputs["sandbox_repo"] == "somecontributor/my-test-repo"
    assert outputs["sandbox_owner"] == "somecontributor"
    assert outputs["sandbox_dir"] == "my-test-repo"


@pytest.mark.parametrize(
    "sandbox_repo",
    [
        "noslash",
        "too/many/slashes",
        "owner name/repo",
        "$(whoami)/repo",
        "owner/repo; whoami",
        "owner/repo\nref=refs/pull/1/head",
        "/repo",
        "owner/",
    ],
)
def test_a_malformed_sandbox_repo_is_rejected(base_path, tmp_path, sandbox_repo):
    assert run_resolve(base_path, tmp_path, sandbox_repo=sandbox_repo)[0] != 0
