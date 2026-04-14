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

from typing import Any

from . import directive, ASFGitHubFeature
from .rulesets import (
    COPILOT_RULESET_NAME,
    COPILOT_RULE_TYPE,
    get_ruleset_names,
    reconcile_rulesets,
    ruleset_has_rule_type,
)

RULESET_NAME = COPILOT_RULESET_NAME


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


def _rulesets_configure_copilot(rulesets: Any) -> bool:
    if not isinstance(rulesets, list):
        return False
    return any(ruleset_has_rule_type(ruleset, COPILOT_RULE_TYPE) for ruleset in rulesets)


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

    if not enabled and not was_previously_configured:
        return

    configured_rulesets = self.yaml.get("rulesets")
    ruleset_names = get_ruleset_names(configured_rulesets)
    rulesets_configure_copilot = _rulesets_configure_copilot(configured_rulesets)

    if enabled and (RULESET_NAME in ruleset_names or rulesets_configure_copilot):
        raise Exception(
            "Cannot configure Copilot Code Review via both 'github.copilot_code_review' and 'github.rulesets'."
        )

    # If generic rulesets owns this name, avoid deleting it during migration from the convenience block.
    if not enabled and (RULESET_NAME in ruleset_names or rulesets_configure_copilot):
        return

    if self.noop("copilot_code_review"):
        return

    desired_rulesets = [_build_copilot_ruleset_payload(review_drafts, review_on_push)] if enabled else []
    previous_managed_names = {RULESET_NAME} if was_previously_configured else set()

    reconcile_rulesets(self, desired_rulesets, previous_managed_names)
