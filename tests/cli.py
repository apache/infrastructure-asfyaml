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

"""Tests for the command line entry points."""

import argparse

import pytest

from asfyaml import cli


def test_plain_branch_name_becomes_a_full_ref():
    assert cli.branch_ref("main") == "refs/heads/main"


def test_branch_name_with_slashes_becomes_a_full_ref():
    assert cli.branch_ref("test/pr-42-rulesets") == "refs/heads/test/pr-42-rulesets"


def test_full_branch_ref_is_passed_through_unchanged():
    assert cli.branch_ref("refs/heads/main") == "refs/heads/main"


def test_tag_ref_is_rejected():
    with pytest.raises(argparse.ArgumentTypeError, match="not a branch"):
        cli.branch_ref("refs/tags/v1.0.0")


def test_empty_branch_is_rejected():
    with pytest.raises(argparse.ArgumentTypeError, match="must not be empty"):
        cli.branch_ref("")


def test_run_parser_defaults_to_the_main_branch():
    args = cli.run_parser().parse_args(["--repo", "."])
    assert args.branch == "refs/heads/main"


def test_run_parser_normalises_the_branch_argument():
    args = cli.run_parser().parse_args(["--repo", ".", "--branch", "test/pr-42"])
    assert args.branch == "refs/heads/test/pr-42"


def test_validate_parser_normalises_the_branch_argument():
    args = cli.validate_parser().parse_args(["--repo", ".", "--branch", "refs/heads/staging"])
    assert args.branch == "refs/heads/staging"


def _git_repo_with_a_commit(tmp_path):
    import os
    import subprocess

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@x",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@x",
    }
    repo_path = tmp_path / "sandbox-repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo_path, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"], cwd=repo_path, check=True, env=env)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, check=True, capture_output=True, text=True, env=env)
    return repo_path, head.stdout.strip()


def test_run_parser_accepts_an_old_sha():
    args = cli.run_parser().parse_args(["--repo", ".", "--old-sha", "0123abc"])
    assert args.old_sha == "0123abc"


def test_run_parser_old_sha_defaults_to_none():
    assert cli.run_parser().parse_args(["--repo", "."]).old_sha is None


@pytest.mark.parametrize("old_sha", ["", "not-hex", "abc; whoami", "g" * 40])
def test_run_parser_rejects_a_malformed_old_sha(old_sha):
    with pytest.raises(SystemExit):
        cli.run_parser().parse_args(["--repo", ".", "--old-sha", old_sha])


def test_old_sha_builds_a_reflog_for_the_branch(tmp_path):
    # The feature code only ever sees a Repository, so --old-sha has to turn into the same
    # one-line reflog the gitbox hook would supply: old tip, HEAD, the full ref.
    repo_path, head = _git_repo_with_a_commit(tmp_path)
    repo = cli.build_repository(repo_path, "apache", "refs/heads/main", old_sha="a" * 40)
    changesets = list(repo.changesets)
    assert len(changesets) == 1
    assert (changesets[0].oldsha, changesets[0].newsha, changesets[0].name) == ("a" * 40, head, "refs/heads/main")
    assert repo.org_id == "apache"


def test_without_old_sha_the_reflog_is_empty(tmp_path):
    repo_path, _head = _git_repo_with_a_commit(tmp_path)
    repo = cli.build_repository(repo_path, "apache", "refs/heads/main", old_sha=None)
    assert list(repo.changesets) == []
