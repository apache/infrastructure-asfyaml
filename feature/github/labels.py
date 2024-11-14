#!/usr/bin/env python3
"""GitHub labels feature"""
import re
from . import directive, ASFGitHubFeature


@directive
def set_labels(self: ASFGitHubFeature):
    # Labels for repo
    labels = self.yaml.get("labels")
    if labels:
        if len(labels) > 20:
            raise Exception("Too many GitHub labels/topics - must be <= 20 items!")
        for label in labels:
            if not re.match(r"^[-a-z0-9]{1,35}$", label):
                raise Exception(
                    f".asf.yaml: Invalid GitHub label '{label}' - must be lowercase alphanumerical and <= 35 characters!"
                )
        # Apply changes, unless we are in no-op (test) mode.
        if not self.noop("labels"):
            self.ghrepo.replace_topics(labels)
