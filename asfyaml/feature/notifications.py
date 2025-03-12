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

"""This is the notifications feature for .asf.yaml. It validates and sets up mailing list targets for repository events."""

import asfyaml.mappings as mappings
from asfyaml.asfyaml import ASFYamlFeature
import re
import fnmatch
import json
import os
import yaml
import asfpy

# Notification settings are stored locally in repo-dir.git/notifications.yaml
NOTIFICATION_SETTINGS_FILE = "notifications.yaml"
# This JSON file contains all valid mailing lists we manage.
VALID_LISTS_FILE = "/x1/gitbox/mailinglists.json"
# These are the schemes we can set.
VALID_NOTIFICATION_SCHEMES = [
    "commits",
    "issues",
    "pullrequests",
    "issues_status",
    "issues_comment",
    "pullrequests_status",
    "pullrequests_comment",
    "jira_options",
    "jobs",
    "commits_by_path",
    "discussions",
    # The rules below are for INFRA-23186
    "pullrequests_bot_*",
    "pullrequests_status_bot_*",
    "pullrequests_comment_bot_*",
    "issues_bot_*",
    "issues_status_bot_*",
    "issues_comment_bot_*",
]

# These are the only valid targets for private repo events
VALID_PRIVATE_TARGETS = [
    "private@*",
    "security@*",
    "commits@infra.apache.org",
]

# regex for valid ASF mailing list
RE_VALID_MAILING_LIST = re.compile(r"[-a-z0-9]+@[-a-z0-9]+(\.incubator)?\.apache\.org$")


class ASFNotificationsFeature(ASFYamlFeature, name="notifications", priority=0):
    """.asf.yaml notifications feature class. Runs before anything else."""
    valid_targets = {}  # Placeholder for self.valid_targets. Will be re-initialized on run.

    def run(self):
        # Test if we need to process this (only works on the default branch)
        if self.instance.branch != self.repository.default_branch:
            print(f"Saw notifications meta-data in .asf.yaml, but not in default branch of repository, not updating...")
            return
        self.valid_targets = {}  # Set to a brand-new instance-local dict for valid scheme entries.
        # Read the list of valid mailing list targets from disk
        valid_lists = json.load(open(VALID_LISTS_FILE))
        # For each setting in our YAML, validate and then set.
        for key, value in self.yaml.items():
            # commits_by_path is handled elsewhere and is a dict, so we disregard that here.
            # jira_options isn't super necessary to verify yet, so ignore as well.
            if key == "commits_by_path" or key == "jira_options":
                continue
            # if there is a '.incubator' bit in the mailing list target, crop it out. We're done with those!
            value = value.replace(".incubator.apache.org", ".apache.org")
            if not isinstance(value, str):
                raise Exception(
                    f"[ERROR] Found bad value set for notifications::{key}. Notification targets must be string values."
                )
            # Ensure we allow this scheme to be configured
            if not any(fnmatch.fnmatch(key, pattern) for pattern in VALID_NOTIFICATION_SCHEMES):
                raise Exception(f"[ERROR] Found unknown notification scheme, notifications::{key}")
            # Ensure this is a valid (existing) list target
            if not RE_VALID_MAILING_LIST.match(value) or value not in valid_lists:
                raise Exception(
                    f"[ERROR] The mailing list target, {value}, set in notifications::{key}, is not an existing ASF mailing list."
                )
            if self.repository.is_private:
                if not any(fnmatch.fnmatch(value, pattern) for pattern in VALID_PRIVATE_TARGETS):
                    raise Exception(
                        f"[ERROR] The mailing list target for notifications::{key} MUST be a private mailing list."
                    )

            # Ensure the right project is contacted, but allow for overrides
            mapped_override = mappings.ML_OVERRIDES.get(self.repository.name)
            if mapped_override and value == mapped_override:
                pass
            elif not value.endswith(f"@{self.repository.hostname}.apache.org"):
                raise Exception(
                    f"[ERROR] Target for notifications::{key} is set to {value}, but must be a valid @{self.repository.hostname}.apache.org mailing list!"
                )

            # All is well??
            self.valid_targets[key] = value

        # Check for commits_by_path and validate if found
        if "commits_by_path" in self.yaml:
            if not isinstance(self.yaml.commits_by_path, dict):
                raise Exception(
                    f"[ERROR] notifications::commits_by_path must be a dictionary, but was a {self.yaml.commits_by_path.__class__.__name__}"
                )
            for pattern, target in self.yaml.commits_by_path.items():
                # All mail targets must be strings. Either a single target or a list of targets.
                email_targets = isinstance(target, list) and target or [target]
                if not all(isinstance(x, str) for x in email_targets):
                    raise Exception(
                        f"[ERROR] Notification target for notifications::commits_by_path::{pattern} must be either a single email address or a list of email addresses."
                    )
                for email_address in email_targets:
                    if not fnmatch.fnmatch(email_address, "*@*.*"):  # Super simple email address validation
                        raise Exception(
                            f"[ERROR] Notification target for notifications::commits_by_path::{pattern} must be valid email addresses, but found target: {email_address}"
                        )

        # Update the notifications file on disk
        scheme_path = os.path.join(self.repository.path, NOTIFICATION_SETTINGS_FILE)
        old_yml = {}
        if os.path.exists(scheme_path):
            old_yml = yaml.safe_load(open(scheme_path))
        if old_yml == self.yaml:  # No changes, just return straight away.
            return
        else:  # Changes made, save to disk
            with open(scheme_path, "w") as fp:
                yaml.dump(self.yaml_raw, fp, default_flow_style=False)
                print("Dumped yaml")

        print(f"Updating notification schemes for repository {self.repository.name}: ")
        changes = ""
        # Figure out what changed since last
        all_schemes = set(list(self.yaml.keys()) + list(old_yml.keys()))  # Every scheme in old + new set.
        for key in all_schemes:
            if key == "commits_by_path":
                continue  # We don't handle these just yet
            if key not in old_yml and key in self.yaml:
                changes += "- adding new scheme (%s): %r\n" % (key, self.yaml[key])
            elif key in old_yml and key not in self.yaml:
                changes += "- removing old scheme (%s) - was %r\n" % (key, old_yml[key])
            elif key in old_yml and key in self.yaml and old_yml[key] != self.yaml[key]:
                changes += "- updating scheme %s: %r -> %r\n" % (key, old_yml[key], self.yaml[key])
        # Print the changes to the git client
        print(changes)

        changesets = ""
        for push in self.repository.changesets:
            for commit in push.commits:
                if ".asf.yaml" in commit.files:
                    perp = commit.committer_email
                    if commit.committer_email != commit.author_email:
                        perp = f"{commit.committer_email}/{commit.author_email}"
                    changesets += f"{commit.sha}: [{perp}] {commit.subject}\n"
        # If in test mode, bail!
        if "quietmode" in self.instance.environments_enabled:
            return

        # Tell project what happened, on private@
        msg = f"""The following notification schemes have been changed on {self.repository.name} by {self.committer.email}:
{changes}

These changes were caused by the following commits to the {self.instance.branch} branch:

{changesets}

With regards,
ASF Infra.
"""
        asfpy.messaging.mail(
            sender="GitBox <gitbox@apache.org>",
            recipients=[f"private@{self.repository.hostname}.apache.org"],
            subject=f"Notification schemes for {self.repository.name}.git updated",
            message=msg,
        )
