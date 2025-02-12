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

"""GitHub auto-link feature"""
from . import directive, ASFGitHubFeature


@directive
def autolink(self: ASFGitHubFeature):
    # Jira auto-linking
    autolink_jira = self.yaml.get("autolink_jira")
    if autolink_jira:
        # If not a list, assume a string and listify it (we'll validate shortly...)
        if not isinstance(autolink_jira, list):
            autolink_jira = [autolink_jira]
        # Grab any existing auto-links (to ensure we don't recreate them over and over)
        if not self.instance.no_cache:
            existing_autolinks = [x for x in self.ghrepo.get_autolinks()]  # Paginated (Iter) result -> list
        else:
            existing_autolinks = []
        # Now add the autolink if not already there
        for jira_space in autolink_jira:
            jira_url = f"https://issues.apache.org/jira/browse/{jira_space}-<num>"
            # Check whether the url_template matches an existing auto-link. If not, create the auto-link entry.
            if not any(jira_url == al.url_template for al in existing_autolinks):
                print(f"Setting up new auto-link for {jira_space}-<num> -> {jira_url}")
                if not self.noop("autolink_jira"):
                    self.ghrepo.create_autolink(key_prefix=f"{jira_space}-", url_template=jira_url)
