#!/usr/bin/env python3
"""GitHub merge buttons"""
from . import directive, ASFGitHubFeature


@directive
def enabled_merge_buttons(self: ASFGitHubFeature):
    # Merge buttons
    merges = self.yaml.get("enabled_merge_buttons")
    if merges:
        if not self.noop("enabled_merge_buttons"):
            self.ghrepo.edit(
                allow_squash_merge=merges.get("squash", False),
                allow_merge_commit=merges.get("merge", False),
                allow_rebase_merge=merges.get("rebase", False),
            )
