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

import json

import requests
import strictyaml

from asfyaml.asfyaml import ASFYamlFeature

# Path to the ATR client config, rendered onto the box by puppet (eyaml).
# Expected JSON shape: {"url": "https://atr.example/api", "token": "<bearer-jwt>"}
ATR_CONFIG_PATH = "/x1/gitbox/auth/atr.json"

_METADATA_SCHEMA = strictyaml.Map(
    {
        strictyaml.Optional("committee"): strictyaml.Str(),
        strictyaml.Optional("name"): strictyaml.Str(),
        strictyaml.Optional("description"): strictyaml.Str(),
        strictyaml.Optional("short_description"): strictyaml.Str(),
        strictyaml.Optional("homepage"): strictyaml.Str(),
        strictyaml.Optional("lifecycle_page"): strictyaml.Str(),
        strictyaml.Optional("download_page"): strictyaml.Str(),
        strictyaml.Optional("bug_database"): strictyaml.Str(),
        strictyaml.Optional("mailing_lists"): strictyaml.Str(),
        strictyaml.Optional("repositories"): strictyaml.Seq(strictyaml.Str()),
        strictyaml.Optional("standards"): strictyaml.Seq(strictyaml.Str()),
        strictyaml.Optional("categories"): strictyaml.Seq(strictyaml.Str()),
        strictyaml.Optional("programming_languages"): strictyaml.Seq(strictyaml.Str()),
    }
)

_FEATURES_SCHEMA = strictyaml.Map(
    {
        strictyaml.Optional("atr_sync"): strictyaml.Bool(),
    }
)


class ASFATRFeature(ASFYamlFeature, name="project", env="production", priority=5):
    """Push project metadata from .asf.yaml to the Apache Trusted Releases (ATR) platform."""

    schema = strictyaml.Map(
        {
            "metadata": _METADATA_SCHEMA,
            strictyaml.Optional("features"): _FEATURES_SCHEMA,
        }
    )

    def run(self):
        """
        Sync project metadata to ATR. Sample entry:
            project:
              metadata:
                committee: tooling   # optional; defaults to the project key
                name: Apache Foo
                description: ...
                homepage: https://foo.apache.org/
                repositories:
                  - git+ssh://git@github.com:apache/foo.git
                ...
              features:
                atr_sync: true
        """
        # Only sync from the default branch — metadata is repo-wide, not per-branch.
        if self.instance.branch != self.repository.default_branch:
            return

        # `features.sync: false` is an explicit opt-out without removing the block.
        features = self.yaml.get("features") or {}
        if features.get("atr_sync") is False:
            return

        metadata = dict(self.yaml.get("metadata") or {})
        project_key = self.repository.project
        # `committee` lives inside the metadata block for authoring, but the ATR API expects it
        # at the top level — pop it before forwarding the rest as the project payload.
        # Sub-projects need to set this explicitly; otherwise it tracks the project key.
        committee_key = metadata.pop("committee", project_key)
        payload = {
            "project_key": project_key,
            "committee_key": committee_key,
            "project": metadata,
        }

        if self.noop("atr"):
            print(json.dumps(payload, indent=2))
            return

        config = _load_config(ATR_CONFIG_PATH)
        url = f"{config['url'].rstrip('/')}/project/config"
        headers = {
            "Authorization": f"Bearer {config['token']}",
            "Content-Type": "application/json",
        }
        print(f"[project] POST {url} for project {project_key}")
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        if not resp.ok:
            # Surface the API's error body — it's the most useful thing to put in the bounce email.
            raise Exception(f"ATR API call failed ({resp.status_code}): {resp.text}")
        print(f"[project] ok: {resp.text}")


def _load_config(path: str) -> dict:
    with open(path) as fh:
        config = json.load(fh)
    for required in ("url", "token"):
        if required not in config:
            raise Exception(f"ATR config at {path} is missing required key '{required}'")
    return config
