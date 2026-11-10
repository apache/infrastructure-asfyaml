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

JIRA_BROWSE_URL = "https://issues.apache.org/jira/browse/"


def jira_autolink_url(jira_space: str) -> str:
    return f"{JIRA_BROWSE_URL}{jira_space}-<num>"


def listify(value) -> list:
    # If not a list, assume a string and listify it (we'll validate shortly...)
    if not value:
        return []
    return value if isinstance(value, list) else [value]


@directive
def autolink(self: ASFGitHubFeature):
    # Jira auto-linking. Once autolink_jira has been configured, it is the authoritative list of
    # Jira auto-links for the repository: any ASF Jira auto-link not in the list is removed, no
    # matter how it was created. If it has never been configured, nothing is added or removed.
    previous_yaml = self.previous_yaml if isinstance(self.previous_yaml, dict) else {}
    if "autolink_jira" not in self.yaml and "autolink_jira" not in previous_yaml:
        return

    desired_spaces = listify(self.yaml.get("autolink_jira"))
    desired_urls = {jira_autolink_url(jira_space) for jira_space in desired_spaces}

    # Grab any existing auto-links (to ensure we don't recreate them over and over)
    if not self.instance.no_cache:
        existing_autolinks = [x for x in self.ghrepo.get_autolinks()]  # Paginated (Iter) result -> list
    else:
        existing_autolinks = []

    # Remove ASF Jira auto-links that are not (or no longer) in the config. Auto-links pointing
    # anywhere else than the ASF Jira are left untouched. An auto-link matching a configured Jira
    # space but with is_alphanumeric set is also removed, to be recreated correctly below.
    matched_urls = set()
    for existing in existing_autolinks:
        if not existing.url_template.startswith(JIRA_BROWSE_URL):
            continue
        if existing.url_template in desired_urls and not existing.is_alphanumeric:
            matched_urls.add(existing.url_template)
        else:
            print(f"Removing auto-link for {existing.key_prefix}<num> -> {existing.url_template}")
            if not self.noop("autolink_jira"):
                self.ghrepo.remove_autolink(existing)

    # Now add the autolink if not already there. is_alphanumeric=False ensures the auto-link only
    # matches numeric ticket ids, e.g. SOLR-123 but not SOLR-FOO.
    for jira_space in desired_spaces:
        jira_url = jira_autolink_url(jira_space)
        if jira_url not in matched_urls:
            print(f"Setting up new auto-link for {jira_space}-<num> -> {jira_url}")
            if not self.noop("autolink_jira"):
                self.ghrepo.create_autolink(key_prefix=f"{jira_space}-", url_template=jira_url, is_alphanumeric=False)
