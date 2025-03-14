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

import strictyaml
from asfyaml.asfyaml import ASFYamlFeature
import requests
import fnmatch

# Pelican website builds via CI2


class ASFJekyllFeature(ASFYamlFeature, name="pelican", env="production", priority=4):

    schema = strictyaml.Map(
        {
            strictyaml.Optional("whoami"): strictyaml.Str(),
            strictyaml.Optional("target"): strictyaml.Str(),
            strictyaml.Optional("theme"): strictyaml.Str(),
            strictyaml.Optional("notify"): strictyaml.Str(),
            strictyaml.Optional("autobuild"): strictyaml.Str(),
            # INFRA-26629: This isn't used by us, but by the asf pelican builder, so keep it as a thing
            strictyaml.Optional("minimum_page_count"): strictyaml.Int(),
        }
    )

    def run(self):
        """
        Pelican auto-build example:
          pelican:
            whoami: applicable branch (optional; 'asf-site' not allowed)
            autobuild: folder/* (optional)
            target: branch (optional)
            theme: name (optional, default: 'theme')
            notify: recipients (optional)
        """
        # Don't build from asf-site, like...ever
        ref = self.instance.branch
        if ref == "asf-site":
            print("Not auto-building from asf-site, ever...")
            return

        autobuild = self.yaml.get("autobuild")
        if autobuild:
            assert autobuild.endswith("/*"), "autobuild parameter must be $foo/*, e.g. site/* or feature/*"
        do_autobuild = (
            autobuild and fnmatch.fnmatch(ref, autobuild) and not ref.endswith("-staging")
        )  # don't autobuild the autobuilt

        # If whoami specified, ignore this payload if branch does not match
        whoami = self.yaml.get("whoami")
        if whoami and whoami != ref and not do_autobuild:
            return

        # Get target branch, if any, default to same branch
        target = self.yaml.get("target", ref)
        if do_autobuild:
            ref_bare = ref.replace(autobuild[:-1], "", 1)  # site/foo -> foo
            target = "%s/%s-staging" % (autobuild[:-2], ref_bare)  # site/foo -> site/foo-staging

        # Get optional theme
        theme = self.yaml.get("theme", "theme")

        # Get notification list - TODO: fix to reuse the old default git recipients
        pnotify = self.yaml.get("notify", f"commits@{self.repository.hostname}.apache.org")

        payload = {
            "method": "force",
            "jsonrpc": "2.0",
            "id": 0,
            "params": {
                "reason": "Triggered pelican auto-build via .asf.yaml by %s" % self.committer.username,
                "builderid": "3",
                "source": "https://gitbox.apache.org/repos/asf/%s.git" % str(self.repository.name),
                "sourcebranch": ref,
                "outputbranch": target,
                "project": self.repository.project,
                "theme": theme,
                "notify": pnotify,
            },
        }
        print("Triggering pelican build...")
        if not self.noop("pelican"):
            # Contact buildbot 2
            bbusr, bbpwd = open("/x1/gitbox/auth/bb2.txt").read().strip().split(":", 1)
            s = requests.Session()
            s.get("https://ci2.apache.org/auth/login", auth=(bbusr, bbpwd))
            s.post("https://ci2.apache.org/api/v2/forceschedulers/pelican_websites", json=payload)
        else:
            print(payload)
        print("Done!")
