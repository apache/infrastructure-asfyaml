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
