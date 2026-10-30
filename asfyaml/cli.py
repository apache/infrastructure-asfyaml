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

import os
import argparse
import re
from pathlib import Path

from asfyaml import dataobjects
from asfyaml.asfyaml import ASFYamlInstance, ASFYAMLException


def dir_path(path):
    if os.path.isdir(path):
        return path
    else:
        raise argparse.ArgumentTypeError(f"readable_dir:{path} is not a valid path")


def branch_ref(branch):
    """Normalises a branch argument into a full ``refs/heads/`` ref."""
    branch = branch.strip()
    if not branch:
        raise argparse.ArgumentTypeError("branch must not be empty")
    if branch.startswith("refs/heads/"):
        return branch
    if branch.startswith("refs/"):
        raise argparse.ArgumentTypeError(f"'{branch}' is not a branch, .asf.yaml is only processed on branches")
    return f"refs/heads/{branch}"


def commit_sha(sha):
    """Accepts a (possibly abbreviated) hex commit SHA and nothing else."""
    sha = sha.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{4,40}", sha):
        raise argparse.ArgumentTypeError(f"'{sha}' is not a commit SHA")
    return sha


def run_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=dir_path, help="path to the repo to process", required=True)
    parser.add_argument("--org", type=str, default="apache", help="the organization this repo belongs to")
    parser.add_argument("--token", type=str, help="token to access the repo via the GH API")
    parser.add_argument("--noop", action=argparse.BooleanOptionalAction, default=False, help="do not perform changes")
    parser.add_argument(
        "--branch",
        type=branch_ref,
        default=dataobjects.DEFAULT_BRANCH,
        help="the branch the .asf.yaml is being processed for, e.g. 'main' or 'refs/heads/main'",
    )
    parser.add_argument(
        "--old-sha",
        type=commit_sha,
        default=None,
        help="the commit the branch was at before this push; with it, the run is treated as the push from "
        "that commit to HEAD, as the gitbox hook would see it (needed to exercise the trusted publishing check)",
    )
    return parser


def build_repository(repo_path: Path, org: str, branch: str, old_sha: str | None) -> dataobjects.Repository:
    """The Repository for a run, with the one-line reflog the gitbox hook would have supplied.

    Features that care about the push (rather than just the file) read it from the reflog, so
    with --old-sha we fabricate the entry "old HEAD ref" and they need not know which entry
    point they are under. Without it the reflog stays empty, as it always has.
    """
    reflog = ""
    if old_sha is not None:
        head = dataobjects.gitcmd("-C", str(repo_path), "rev-parse", "HEAD").strip()
        if not head:
            raise Exception(f"--old-sha given but git rev-parse HEAD failed in {repo_path}")
        reflog = f"{old_sha} {head} {branch}\n"
    return dataobjects.Repository(str(repo_path), reflog=reflog, org_id=org)


def cli():
    args = run_parser().parse_args()

    repo_path = Path(os.path.abspath(args.repo))
    repo = build_repository(repo_path, args.org, args.branch, args.old_sha)

    yml_file = os.path.join(repo_path, ".asf.yaml")
    if not os.path.exists(yml_file):
        raise Exception(f".asf.yaml does not exist at location '{yml_file}'")

    with open(yml_file) as f:
        yml_content = f.read()

    os.environ["PATH_INFO"] = repo_path.name
    os.environ["GIT_PROJECT_ROOT"] = str(repo_path.parent)

    if args.token is not None:
        os.environ["GH_TOKEN"] = args.token

    if os.environ.get("GH_TOKEN") is None:
        raise Exception(
            "no GitHub token has been provided, either add a '--token' argument or set a 'GH_TOKEN' env variable."
        )

    a = ASFYamlInstance(repo, "anonymous", yml_content, args.branch)

    if args.noop:
        a.environments_enabled.add("noop")
    else:
        a.environments_enabled.add("production")

    a.run_parts()


def validate_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=dir_path, help="path to the repo to process", required=True)
    parser.add_argument("--org", type=str, default="apache", help="the organization this repo belongs to")
    parser.add_argument(
        "--branch",
        type=branch_ref,
        default=dataobjects.DEFAULT_BRANCH,
        help="the branch the .asf.yaml is being processed for, e.g. 'main' or 'refs/heads/main'",
    )
    return parser


def validate():
    """Validates a .asf.yaml file according to the current schema."""
    args = validate_parser().parse_args()

    repo_path = Path(os.path.abspath(args.repo))
    repo = dataobjects.Repository(str(repo_path), org_id=args.org)

    yml_file = os.path.join(repo_path, ".asf.yaml")
    if not os.path.exists(yml_file):
        raise Exception(f".asf.yaml does not exist at location '{yml_file}'")

    with open(yml_file, mode="r") as f:
        yml_content = f.read()

    os.environ["PATH_INFO"] = repo_path.name
    os.environ["GIT_PROJECT_ROOT"] = str(repo_path.parent)

    a = ASFYamlInstance(repo, "anonymous", yml_content, args.branch)

    a.environments_enabled.add("production")

    try:
        a.run_parts(validate_only=True)
        print(f"{yml_file} is a valid .asf.yaml file.")
    except ASFYAMLException as err:
        print(err.error_message)


if __name__ == "__main__":
    cli()
