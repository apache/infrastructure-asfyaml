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

"""GitHub Copilot code review ruleset support."""

import json
from typing import Any

from . import directive, ASFGitHubFeature

RULESET_NAME = "Copilot Code Review"


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


def _ruleset_has_copilot_rule(ruleset: dict[str, Any]) -> bool:
    return any(rule.get("type") == "copilot_code_review" for rule in ruleset.get("rules", []))


def _list_rulesets(self: ASFGitHubFeature) -> list[dict[str, Any]]:
    response = self.ghrepo._requester.requestJson("GET", _rulesets_endpoint(self))
    payload = _extract_json_payload(response)
    if not isinstance(payload, list):
        return []
    return [ruleset for ruleset in payload if isinstance(ruleset, dict)]


def _find_copilot_ruleset(rulesets: list[dict[str, Any]]) -> dict[str, Any] | None:
    for ruleset in rulesets:
        if ruleset.get("name") == RULESET_NAME or _ruleset_has_copilot_rule(ruleset):
            return ruleset
    return None


def _build_copilot_ruleset_payload(review_drafts: bool, review_on_push: bool) -> dict[str, Any]:
    return {
        "name": RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "conditions": {
            "ref_name": {
                "include": ["~DEFAULT_BRANCH"],
                "exclude": [],
            }
        },
        "rules": [
            {
                "type": "copilot_code_review",
                "parameters": {
                    "review_draft_pull_requests": review_drafts,
                    "review_on_push": review_on_push,
                },
            }
        ],
    }


@directive
def copilot_code_review(self: ASFGitHubFeature):
    copilot = self.yaml.get("copilot_code_review")
    previous_yaml = self.previous_yaml if isinstance(self.previous_yaml, dict) else {}
    was_previously_configured = "copilot_code_review" in previous_yaml

    if copilot:
        enabled = copilot.get("enabled", False)
        review_drafts = copilot.get("review_drafts", False)
        review_on_push = copilot.get("review_on_push", False)
    elif was_previously_configured:
        enabled = False
        review_drafts = False
        review_on_push = False
    else:
        return

    if self.noop("copilot_code_review"):
        return

    endpoint = _rulesets_endpoint(self)
    existing_ruleset = _find_copilot_ruleset(_list_rulesets(self))

    if enabled:
        payload = _build_copilot_ruleset_payload(review_drafts, review_on_push)
        if existing_ruleset:
            ruleset_id = existing_ruleset.get("id")
            if ruleset_id is None:
                raise Exception("Found Copilot Code Review ruleset without an id")
            print(f"Updating Copilot code review ruleset ({ruleset_id})")
            self.ghrepo._requester.requestJson("PUT", f"{endpoint}/{ruleset_id}", input=payload)
        else:
            print("Creating Copilot code review ruleset")
            self.ghrepo._requester.requestJson("POST", endpoint, input=payload)
    elif existing_ruleset:
        ruleset_id = existing_ruleset.get("id")
        if ruleset_id is None:
            raise Exception("Found Copilot Code Review ruleset without an id")
        print(f"Deleting Copilot code review ruleset ({ruleset_id})")
        self.ghrepo._requester.requestJson("DELETE", f"{endpoint}/{ruleset_id}")
