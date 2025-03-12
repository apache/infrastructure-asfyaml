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

"""GitHub general features: wiki, issues, projects, discussions"""
from . import directive, ASFGitHubFeature


@directive
def config_features(self: ASFGitHubFeature):
    # Generic features: issues, wiki, projects, discussions
    features = self.yaml.get("features")
    if features:
        if features.get("discussions", False):
            notifs = self.instance.features.notifications
            if (not notifs) or "discussions" not in notifs.valid_targets:
                raise Exception("GitHub discussions can only be enabled if a mailing list target exists for it.")

        # Apply the changes to GitHub, unless we are in no-op (test) mode.
        if not self.noop("features"):
            self.ghrepo.edit(
                has_issues=features.get("issues", False),
                has_wiki=features.get("wiki", False),
                has_projects=features.get("projects", False),
                has_discussions=features.get("discussions", False),
            )
