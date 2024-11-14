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
import asfyaml
from asfyaml import ASFYamlFeature
import re
import strictyaml
import os
import yaml
import string

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
        }
    )

    def run(self):
        """GitHub features"""
        # Test if we need to process this (only works on the default branch)
        if self.instance.branch != self.repository.default_branch:
            print(f"Saw GitHub meta-data in .asf.yaml, but not in default branch of repository, not updating...")
            print(self.instance.branch, self.repository.default_branch)
            return

        # Check if cached yaml exists, compare if changed
        ymlfile = "/x1/asfyaml/ghsettings.%s.yml" % self.repository.name
        if not self.instance.no_cache:
            try:
                if os.path.exists(ymlfile):
                    old_yaml = yaml.safe_load(open(ymlfile).read())
                    if old_yaml == self.yaml:
                        if asfyaml.DEBUG:
                            print("[github] Saw no changes to GitHub settings, skipping this run.")
                        return
            except yaml.YAMLError as _e:  # Failed to parse old yaml? bah.
                print("Failed to parse previous GitHub settings, please notify users@infra.apache.org")

        # Update items
        print("GitHub meta-data changed, updating...")

        self.ghrepo = None  # TODO: Init this!

        for _feat in _features:
            _feat(self)

        # Generic features: issues, wiki, projects, discussions
        features = self.yaml.get("features")
        if features:
            if features.get("discussions", False):
                notifs = self.instance.features.notifications
                if (not notifs) or "discussions" not in notifs.valid_targets:
                    raise Exception("GitHub discussions can only be enabled if a mailing list target exists for it.")

            # If in NO-OP mode, we shouldn't actually try to stage anything.
            if not self.noop("features"):
                repo.edit(
                    has_issues=features.get("issues", False),
                    has_wiki=features.get("wiki", False),
                    has_projects=features.get("projects", False),
                    has_discussions=features.get("discussions", False),
                )

        # Merge buttons
        merges = self.yaml.get("enabled_merge_buttons")
        if merges:
            if not self.noop("enabled_merge_buttons"):
                repo.edit(
                    allow_squash_merge=merges.get("squash", False),
                    allow_merge_commit=merges.get("merge", False),
                    allow_rebase_merge=merges.get("rebase", False),
                )

# Import our sub-directives
from . import labels, autolink