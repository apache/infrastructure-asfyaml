#!/usr/bin/env python3
#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""This is the GitHub feature for .asf.yaml."""
from asfyaml.asfyaml import ASFYamlFeature, ASFYamlInstance, DEBUG
import strictyaml
import os
import sys
import yaml
import string
import github as pygithub
import github.Auth as pygithubAuth

GH_TOKEN_FILE = "/x1/gitbox/tokens/asfyaml.txt"  # Path to .asf.yaml github token
_features = []


def directive(func):
    _features.append(func)
    return func


class JiraSpaceString(strictyaml.Str):
    """YAML validator for Jira spaces, must be uppercase alpha only."""
    def validate_scalar(self, chunk):
        if not all(char in string.ascii_uppercase for char in chunk.contents):
            raise strictyaml.YAMLValidationError(None, "String must be uppercase only, e.g. INFRA or AIRFLOW.", chunk)
        return chunk.contents


class ASFGitHubFeature(ASFYamlFeature, name="github"):
    """.asf.yaml GitHub feature class."""

    schema = strictyaml.Map(
        {
            # repository description, e.g. "Apache Airflow"
            strictyaml.Optional("description"): strictyaml.Str(),
            # repository website, e.g. "https://airflow.apache.org/"
            strictyaml.Optional("homepage"): strictyaml.Str(),
            # labels: a list of labels/tags to describe the repository.
            strictyaml.Optional("labels"): strictyaml.Seq(strictyaml.Str()),
            # features: enable/disable specific GitHub features. dict of bools.
            strictyaml.Optional("features"): strictyaml.Map(
                {
                    strictyaml.Optional("wiki"): strictyaml.Bool(),
                    strictyaml.Optional("issues"): strictyaml.Bool(),
                    strictyaml.Optional("projects"): strictyaml.Bool(),
                    strictyaml.Optional("discussions"): strictyaml.Bool(),
                }
            ),
            # enabled_merge_buttons
            strictyaml.Optional("enabled_merge_buttons"): strictyaml.Map(
                {
                    strictyaml.Optional("squash"): strictyaml.Bool(),
                    strictyaml.Optional("merge"): strictyaml.Bool(),
                    strictyaml.Optional("rebase"): strictyaml.Bool(),
                }
            ),
            # Auto-linking for JIRA. Can be a list of Jira projects or a single string value
            strictyaml.Optional("autolink_jira"): strictyaml.OrValidator(
                JiraSpaceString(),
                strictyaml.Seq(JiraSpaceString()),
            ),

            strictyaml.Optional("merge_commit_message"): strictyaml.Str(),
            strictyaml.Optional("merge_commit_title"): strictyaml.Str(),
            strictyaml.Optional("squash_merge_commit_message"): strictyaml.Str(),
            strictyaml.Optional("squash_merge_commit_title"): strictyaml.Str(),

            # GitHub Pages: branch (can be default or gh-pages) and path (can be /docs or /)
            strictyaml.Optional("ghp_branch"): strictyaml.Str(),
            strictyaml.Optional("ghp_path", default="/docs"): strictyaml.Str(),
        }
    )

    def __init__(self, parent: ASFYamlInstance, yaml: strictyaml.YAML, **kwargs):
        self.ghrepo = None
        super().__init__(parent, yaml)

    def run(self):
        """GitHub features"""
        # Test if we need to process this (only works on the default branch)
        if self.instance.branch != self.repository.default_branch:
            print(f"Saw GitHub meta-data in .asf.yaml, but not in default branch of repository, not updating...")
            return

        # Check if cached yaml exists, compare if changed
        self.previous_yaml = {}
        yaml_filepath = f"/x1/asfyaml/ghsettings.{self.repository.name}.yml"
        if "pytest" in sys.modules:  # Pytest mode, no /x1!
            yaml_filepath = f"/tmp/ghsettings.{self.repository.name}.yml"
        if not self.instance.no_cache:
            try:
                if os.path.exists(yaml_filepath):
                    self.previous_yaml = yaml.safe_load(open(yaml_filepath).read())
                    if self.previous_yaml == self.yaml:
                        if DEBUG:
                            print("[github] Saw no changes to GitHub settings, skipping this run.")
                        return
            except yaml.YAMLError as _e:  # Failed to parse old yaml? bah.
                print("Failed to parse previous GitHub settings, please notify users@infra.apache.org")

        # Update items
        print("GitHub meta-data changed, updating...")
        if not self.noop("github"):
            pgh = pygithub.Github(auth=pygithubAuth.Token(open(GH_TOKEN_FILE).read().strip()))
            self.ghrepo = pgh.get_repo(f"apache/{self.repository.name}")

        # For each sub-feature we see (with the @directive decorator on it), run it
        for _feat in _features:
            _feat(self)

        # Save cached version of this YAML for next time.
        with open(yaml_filepath, "w") as f:
            f.write(yaml.dump(self.yaml_raw, default_flow_style=False))

# Import our sub-directives (...after we have declared the feature class, to avoid circular imports)
from . import metadata, autolink, features, merge_buttons, pages, merge_commit_settings, squash_merge_commit_settings
