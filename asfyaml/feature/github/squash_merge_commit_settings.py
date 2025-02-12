#!/usr/bin/env python3
"""GitHub squash merge commit settings feature"""
from . import directive, ASFGitHubFeature


@directive
def squash_merge_commit_settings(self: ASFGitHubFeature):
    squash_merge_commit_title = self.yaml.get("squash_merge_commit_title")
    squash_merge_commit_message = self.yaml.get("squash_merge_commit_message")

    # if neither a title nor message is specified, just return
    if not squash_merge_commit_title and not squash_merge_commit_message:
        return

    # if only one of the 2 properties is set,
    # retrieve the other one from the current live setting
    if squash_merge_commit_title and not squash_merge_commit_message:
        squash_merge_commit_message = self.ghrepo.squash_merge_commit_message

    if squash_merge_commit_message and not squash_merge_commit_title:
        squash_merge_commit_title = self.ghrepo.squash_merge_commit_title

    # check if we have a valid combination
    if (squash_merge_commit_title, squash_merge_commit_message) not in [
        ("PR_TITLE", "PR_BODY"),
        ("PR_TITLE", "BLANK"),
        ("PR_TITLE", "COMMIT_MESSAGES"),
        ("COMMIT_OR_PR_TITLE", "COMMIT_MESSAGES"),
    ]:
        raise Exception(
            f".asf.yaml: Invalid squash_merge_commit title / message settings: - must be a combination of "
            "('PR_TITLE', 'PR_BODY') | ('PR_TITLE', 'BLANK') | ('PR_TITLE', 'COMMIT_MESSAGES') | "
            "('COMMIT_OR_PR_TITLE', 'COMMIT_MESSAGES')."
        )

    if not self.noop("squash_merge_commit_title") and not self.noop("squash_merge_commit_message"):
        self.ghrepo.edit(
            squash_merge_commit_title=squash_merge_commit_title,
            squash_merge_commit_message=squash_merge_commit_message,
        )
