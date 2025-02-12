#!/usr/bin/env python3
"""GitHub merge commit settings feature"""
from . import directive, ASFGitHubFeature


@directive
def merge_commit_settings(self: ASFGitHubFeature):
    merge_commit_title = self.yaml.get("merge_commit_title")
    merge_commit_message = self.yaml.get("merge_commit_message")

    # if neither a title nor message is specified, just return
    if not merge_commit_title and not merge_commit_message:
        return

    # if only one of the 2 properties is set,
    # retrieve the other one from the current live setting
    if merge_commit_title and not merge_commit_message:
        merge_commit_message = self.ghrepo.merge_commit_message

    if merge_commit_message and not merge_commit_title:
        merge_commit_title = self.ghrepo.merge_commit_title

    # check if we have a valid combination
    if (merge_commit_title, merge_commit_message) not in [
        ("PR_TITLE", "PR_BODY"),
        ("PR_TITLE", "BLANK"),
        ("MERGE_MESSAGE", "PR_TITLE"),
    ]:
        raise Exception(
            f".asf.yaml: Invalid merge_commit title / message settings: - must be a combination of "
            "('PR_TITLE', 'PR_BODY') | ('PR_TITLE', 'BLANK') | ('MERGE_MESSAGE', 'PR_TITLE')."
        )

    if not self.noop("merge_commit_title") and not self.noop("merge_commit_message"):
        self.ghrepo.edit(merge_commit_title=merge_commit_title, merge_commit_message=merge_commit_message)
