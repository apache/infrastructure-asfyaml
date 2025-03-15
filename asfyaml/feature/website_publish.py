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


class ASFWebsitePublishingFeature(ASFYamlFeature, name="publish", priority=9):
    """.asf.yaml website publishing feature class."""

    schema = strictyaml.Map(
        {
            strictyaml.Optional("whoami", default="main"): strictyaml.Str(),
            strictyaml.Optional("subdir", default=None): strictyaml.Str(),
            strictyaml.Optional("type", default="website"): strictyaml.Str(),
            strictyaml.Optional("hostname", default=None): strictyaml.Str(),
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

        # Get optional target hostname:
        hostname = self.yaml.hostname if "hostname" in self.yaml else None
        if hostname and "apache.org" in hostname:
            if mappings.WS_HOSTNAME_OVERRIDES.get(self.repository.name, "") != hostname:
                raise Exception(
                    f".asf.yaml: Invalid hostname '{hostname}' - you cannot specify *.apache.org hostnames, they must be inferred!"
                )
        elif not hostname:  # Infer hostname if not supplied.
            hostname = f"{self.repository.hostname}.apache.org"

        # If whoami specified, ignore this payload if branch does not match
        whoami = self.yaml.get("whoami")
        if whoami and whoami != self.instance.branch:
            return

        subdir = self.yaml.get("subdir")
        if subdir:
            validate_subdir(subdir)

        # Determine deployment type (website or blog?)
        deploy_type = self.yaml.get("type", "website")
        if deploy_type not in ("website", "blog"):
            raise Exception(f".asf.yaml: Invalid deployment type '{deploy_type}' - must be either 'website' or 'blog'!")

        print(f"Publishing contents at https://{self.repository.hostname}.apache.org/ ...")

        # If in NO-OP mode, we shouldn't actually try to stage anything.
        if not self.noop("publish"):
            # Try sending publish payload to pubsub
            try:
                payload = {
                    "publish": {
                        "project": self.repository.project,
                        "subdir": subdir,
                        "source": "https://gitbox.apache.org/repos/asf/%s.git" % self.repository.name,
                        "branch": self.instance.branch,
                        "pusher": self.committer.username,
                        "target": hostname,
                        "type": deploy_type,
                    }
                }

                # Send to pubsub.a.o
                requests.post(f"https://pubsub.apache.org:2070/publish/{self.repository.project}", json=payload)
            except Exception as e:
                print(e)
