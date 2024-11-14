#!/usr/bin/env python3
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
