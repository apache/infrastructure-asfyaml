#!/usr/bin/env python3
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

        # If in NO-OP mode, we shouldn't actually try to stage anything.
        if not self.noop("features"):
            self.ghrepo.edit(
                has_issues=features.get("issues", False),
                has_wiki=features.get("wiki", False),
                has_projects=features.get("projects", False),
                has_discussions=features.get("discussions", False),
            )
