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
from pathlib import Path

from asfyaml import dataobjects
from asfyaml.asfyaml import ASFYamlInstance

def dir_path(path):
    if os.path.isdir(path):
        return path
    else:
        raise argparse.ArgumentTypeError(f"readable_dir:{path} is not a valid path")


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=dir_path, help="path to the repo to process")
    parser.add_argument("--org", type=str, default="apache", help="the organization this repo belongs to")
    parser.add_argument("--token", type=str, required=True, help="token to access the repo via the GH API")
    parser.add_argument("--noop", action=argparse.BooleanOptionalAction, default=False, help="do not perform changes")
    args = parser.parse_args()

    repo_path = Path(os.path.abspath(args.repo))
    repo = dataobjects.Repository(str(repo_path))

    yml_file = os.path.join(repo_path, ".asf.yaml")
    if not os.path.exists(yml_file):
        raise Exception(f".asf.yaml does not exist at location '{yml_file}'")

    with open(yml_file, mode="r") as f:
        yml_content = f.read()

    os.environ["PATH_INFO"] = repo_path.name
    os.environ["GIT_PROJECT_ROOT"] = str(repo_path.parent)
    os.environ["GH_TOKEN"] = args.token
    os.environ["ORG_ID"] = args.org

    a = ASFYamlInstance(repo, "anonymous", yml_content)

    if args.noop:
        a.environments_enabled.add("noop")
    else:
        a.environments_enabled.add("production")

    a.run_parts()


if __name__ == "__main__":
    cli()
