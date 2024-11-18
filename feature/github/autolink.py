#!/usr/bin/env python3
"""GitHub autolink feature"""
from . import directive, ASFGitHubFeature


@directive
def autolink(self: ASFGitHubFeature):
    # Jira autolinking
    autolink_jira = self.yaml.get("autolink_jira")
    if autolink_jira:
        # If not a list, assume a string and listify it (we'll validate shortly...)
        if not isinstance(autolink_jira, list):
            autolink_jira = [autolink_jira]
        # Grab any existing autolinks (to ensure we don't recreate them over and over)
        if not self.instance.no_cache:
            existing_autolinks = [x for x in self.ghrepo.get_autolinks()]  # Paginated (Iter) result -> list
        else:
            existing_autolinks = []
        # Now add the autolink if not already there
        for jiraname in autolink_jira:
            jira_url = f"https://issues.apache.org/jira/browse/{jiraname}-<num>"
            # Check whether the url_template matches an existing autolink. If not, create the autolink entry.
            if not any(jira_url == al.url_template for al in existing_autolinks):
                print(f"Setting up new auto-link for {jiraname}-<num> -> {jira_url}")
                if not self.noop("autolink_jira"):
                    self.ghrepo.create_autolink(key_prefix=f"{jiraname}-", url_template=jira_url)
