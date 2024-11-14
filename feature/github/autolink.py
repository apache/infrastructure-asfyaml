#!/usr/bin/env python3
"""GitHub autolink feature"""
from . import directive, ASFGitHubFeature


@directive
def autolink(self: ASFGitHubFeature):
    # Jira autolinking
    autolink = self.yaml.get("autolink_jira")
    if autolink:
        # If not a list, assume a string and listify it (we'll validate shortly...)
        if not isinstance(autolink, list):
            autolink = [autolink]
        # Validate all jira names listed first
        for jiraname in autolink:
            # Must be string, uppercase alpha only.
            if not isinstance(jiraname, str) and re.match(r"^([A-Z][A-Z]+)$", jiraname):
                raise Exception(
                    ".asf.yaml: Invalid Jira project for GitHub autolink '%r' - must be a string of uppercase alphabetical characters only!"
                    % jiraname
                )
        # Grab any existing autolinks (to ensure we don't recreate them over and over)
        if not self.instance.no_cache:
            existing_autolinks = [x for x in repo.get_autolinks()]  # Paginated (Iter) result -> list
        else:
            existing_autolinks = []
        # Now add the autolink if not already there
        for jiraname in autolink:
            jira_url = f"https://issues.apache.org/jira/browse/{jiraname}-<num>"
            # Check whether the url_template matches an existing autolink. If not, create the autolink entry.
            if not any(jira_url == al.url_template for al in existing_autolinks):
                print(f"Setting up new auto-link for {jiraname}-<num> -> {jira_url}")
                if not self.noop("autolink_jira"):
                    repo.create_autolink(key_prefix=f"{jiraname}-", url_template=jira_url)
