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

"""GitHub repository rulesets feature."""

import json
from typing import Any

from . import directive, ASFGitHubFeature

COPILOT_RULESET_NAME = "Copilot Code Review"
COPILOT_RULE_TYPE = "copilot_code_review"


def _rulesets_endpoint(self: ASFGitHubFeature) -> str:
    return f"/repos/{self.repository.org_id}/{self.repository.name}/rulesets"


def _extract_json_payload(response: Any) -> Any:
    if isinstance(response, (dict, list)):
        return response

    if isinstance(response, tuple):
        for item in reversed(response):
            if isinstance(item, (dict, list)):
                return item
        for item in reversed(response):
            if isinstance(item, str):
                try:
                    return json.loads(item)
                except json.JSONDecodeError:
                    continue

    return []


def list_rulesets(self: ASFGitHubFeature) -> list[dict[str, Any]]:
    response = self.ghrepo._requester.requestJson("GET", _rulesets_endpoint(self))
    payload = _extract_json_payload(response)
    if not isinstance(payload, list):
        return []
    return [ruleset for ruleset in payload if isinstance(ruleset, dict)]


def get_ruleset_names(rulesets: Any) -> set[str]:
    names: set[str] = set()
    if not isinstance(rulesets, list):
        return names

    for ruleset in rulesets:
        if not isinstance(ruleset, dict):
            continue
        name = ruleset.get("name")
        if isinstance(name, str) and name.strip():
            names.add(name)

    return names


def ruleset_has_rule_type(ruleset: Any, rule_type: str) -> bool:
    if not isinstance(ruleset, dict):
        return False
    rules = ruleset.get("rules", [])
    if not isinstance(rules, list):
        return False
    return any(isinstance(rule, dict) and rule.get("type") == rule_type for rule in rules)


def is_copilot_code_review_enabled(copilot: Any) -> bool:
    return isinstance(copilot, dict) and copilot.get("enabled", False)


def ensure_no_copilot_overlap(desired_rulesets: list[dict[str, Any]], copilot_enabled: bool) -> None:
    if not copilot_enabled:
        return

    has_overlap = COPILOT_RULESET_NAME in get_ruleset_names(desired_rulesets) or any(
        ruleset_has_rule_type(ruleset, COPILOT_RULE_TYPE) for ruleset in desired_rulesets
    )
    if has_overlap:
        raise Exception("Cannot configure Copilot Code Review via both 'github.copilot_code_review' and 'github.rulesets'.")


def normalize_rulesets(rulesets: Any) -> list[dict[str, Any]]:
    if rulesets is None:
        return []
    if not isinstance(rulesets, list):
        raise Exception("github.rulesets must be a list of mappings")

    normalized: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for i, ruleset in enumerate(rulesets):
        if not isinstance(ruleset, dict):
            raise Exception(f"github.rulesets[{i}] must be a mapping")
        if "name" not in ruleset:
            raise Exception(f"github.rulesets[{i}] must define 'name'")
        name = ruleset.get("name")
        if not isinstance(name, str) or not name.strip():
            raise Exception(f"github.rulesets[{i}].name must be a non-empty string")
        if name in seen_names:
            raise Exception(f"Duplicate ruleset name in github.rulesets: '{name}'")

        seen_names.add(name)
        normalized.append(dict(ruleset))

    return normalized


def reconcile_rulesets(
    self: ASFGitHubFeature,
    desired_rulesets: list[dict[str, Any]],
    previously_managed_names: set[str],
) -> None:
    endpoint = _rulesets_endpoint(self)
    existing_by_name: dict[str, dict[str, Any]] = {}

    existing_rulesets = list_rulesets(self)

    for ruleset in existing_rulesets:
        name = ruleset.get("name")
        if isinstance(name, str) and name not in existing_by_name:
            existing_by_name[name] = ruleset

    desired_names: set[str] = set()

    for ruleset in desired_rulesets:
        name = ruleset["name"]
        desired_names.add(name)
        existing_ruleset = existing_by_name.get(name)

        if existing_ruleset:
            ruleset_id = existing_ruleset.get("id")
            if ruleset_id is None:
                raise Exception(f"Found ruleset '{name}' without an id")
            print(f"Updating GitHub ruleset '{name}' ({ruleset_id})")
            self.ghrepo._requester.requestJson("PUT", f"{endpoint}/{ruleset_id}", input=ruleset)
        else:
            print(f"Creating GitHub ruleset '{name}'")
            self.ghrepo._requester.requestJson("POST", endpoint, input=ruleset)

    removed_names = previously_managed_names - desired_names
    for name in sorted(removed_names):
        existing_ruleset = existing_by_name.get(name)
        if not existing_ruleset:
            continue
        ruleset_id = existing_ruleset.get("id")
        if ruleset_id is None:
            raise Exception(f"Found ruleset '{name}' without an id")
        print(f"Deleting GitHub ruleset '{name}' ({ruleset_id})")
        self.ghrepo._requester.requestJson("DELETE", f"{endpoint}/{ruleset_id}")


@directive
def rulesets(self: ASFGitHubFeature):
    previous_yaml = self.previous_yaml if isinstance(self.previous_yaml, dict) else {}
    rulesets_configured = "rulesets" in self.yaml
    was_previously_configured = "rulesets" in previous_yaml

    if not rulesets_configured and not was_previously_configured:
        return

    desired_rulesets = normalize_rulesets(self.yaml.get("rulesets")) if rulesets_configured else []
    ensure_no_copilot_overlap(desired_rulesets, is_copilot_code_review_enabled(self.yaml.get("copilot_code_review")))

    previous_managed_names = get_ruleset_names(previous_yaml.get("rulesets", [])) if was_previously_configured else set()

    if self.noop("rulesets"):
        return

    reconcile_rulesets(self, desired_rulesets, previous_managed_names)
