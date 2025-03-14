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

from asfyaml.asfyaml import ASFYamlFeature
import asfyaml.validators
import re
import fnmatch
import requests
import strictyaml

def validate_subdir(subdir):
    """Validates a sub-directory for projects with multiple website repos."""
    if not re.match(r"^[-._a-zA-Z0-9/]+$", subdir):
        raise Exception(".asf.yaml: Invalid subdir '%s' - Should be [.-_a-zA-Z0-9/]+ only!" % subdir)
    if re.match(r".*\.\./.*", subdir):
        raise Exception(".asf.yaml: Invalid subdir '%s' - Usage of '../'!" % subdir)
    if subdir.startswith("/"):
        raise Exception(".asf.yaml: Invalid subdir '%s' - cannot start with a forward slash (/)!" % subdir)


class ASFWebsiteStagingFeature(ASFYamlFeature, name="staging", priority=9):
    """.asf.yaml website publishing feature class."""

    schema = strictyaml.Map(
        {
            strictyaml.Optional("whoami", default="main"): strictyaml.Str(),
            strictyaml.Optional("subdir", default=None): strictyaml.Str(),
            strictyaml.Optional("type", default="website"): strictyaml.Str(),
            strictyaml.Optional("hostname", default=None): strictyaml.Str(),
            strictyaml.Optional("profile", default=None): asfyaml.validators.EmptyValue() | strictyaml.Str(),
            strictyaml.Optional("autostage", default=None): strictyaml.Str(),
        })

    def run(self):
        """Publishing for websites. Sample entry .asf.yaml entry:
        publish:
          whoami: asf-site
          # would publish current branch (if asf-site) at https://$project.apache.org/
          subdir: optional subdirectory to publish from
          type: website|blog (default website)
          hostname: optional override; must be events.apache.org or a non-ASF host
        """

        hostname = f"{self.repository.hostname}.apache.org"  # Infer hostname if not supplied.

        autostage = self.yaml.get("autostage")
        if autostage:
            assert isinstance(autostage, str), "autostage parameter must be a string!"
            assert autostage.endswith("/*"), "autostage parameter must be $foo/*, e.g. site/* or feature/*"
        do_autostage = (
            autostage and fnmatch.fnmatch(self.instance.branch, autostage) and self.instance.branch.endswith("-staging")
        )  # site/foo-staging, matching site/*

        # If whoami specified, ignore this payload if branch does not match autostage
        whoami = self.yaml.get("whoami")
        if whoami and whoami != self.instance.branch and not do_autostage:
            return

        subdir = self.yaml.get("subdir")
        if subdir:
            validate_subdir(subdir)

        # Get profile from .asf.yaml, if present, or autostage derivation
        profile = self.yaml.get("profile", "")
        if do_autostage:
            profile = self.instance.branch.replace(autostage[:-1], "", 1)[
                :-8
            ]  # site/foo-staging -> foo -> $project-foo.staged.a.o
        # The profile value is used in the staging host name, so must only contain valid DNS characters
        if profile and not re.match(r"^[-.a-zA-Z0-9/]*$", profile):
            raise Exception(
                f".asf.yaml: Invalid staging profile, '{profile}'. Must only contain permitted DNS characters (see RFC1035, §2.3.1)"
            )

        wsname = f"https://{self.repository.hostname}.staged.apache.org"
        if profile:
            wsname = f"https://{self.repository.hostname}-{profile}.staged.apache.org"
        print(f"Staging contents at {wsname} ...")


        # Try sending publish payload to pubsub
        if not self.noop("staging"):
            try:
                payload = {
                    "staging": {
                        "project": self.repository.project,
                        "subdir": subdir,
                        "source": "https://gitbox.apache.org/repos/asf/%s.git" % self.repository.name,
                        "branch": self.instance.branch,
                        "pusher": self.committer.username,
                        "target": hostname,
                        "profile": profile,
                    }
                }

                # Send to pubsub.a.o
                requests.post(f"https://pubsub.apache.org:2070/staging/{self.repository.project}", json=payload)

            except Exception as e:
                print(e)
