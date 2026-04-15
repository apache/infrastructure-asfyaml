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

from github import UnknownObjectException

from . import directive, ASFGitHubFeature

COPILOT_RULESET_NAME = "Copilot Code Review"
COPILOT_RULE_TYPE = "copilot_code_review"
_RAW_RULESET_KEYS = {"target", "enforcement", "conditions", "rules", "bypass_actors"}
_CONVENIENCE_RULESET_KEYS = {
    "type",
    "branches",
    "refs",
    "bypass_teams",
    "bypass_mode",
    "restrict_deletion",
    "restrict_force_push",
    "required_signatures",
    "required_linear_history",
    "required_conversation_resolution",
    "required_pull_request_reviews",
    "required_status_checks",
    "required_status_checks_strict",
}


def _rulesets_endpoint(self: ASFGitHubFeature) -> str:
    return f"/repos/{self.repository.org_id}/{self.repository.name}/rulesets"


def list_rulesets(self: ASFGitHubFeature) -> list[dict[str, Any]]:
    status, _headers, body = self.ghrepo._requester.requestJson("GET", _rulesets_endpoint(self))
    if status == 404:
        raise Exception(f"Repository '{self.repository.org_id}/{self.repository.name}' not found or not accessible")
    if status == 500:
        raise Exception("GitHub server error while listing rulesets")
    if status != 200:
        raise Exception(f"Unexpected response while listing rulesets: HTTP {status}")
    payload = json.loads(body)
    if not isinstance(payload, list):
        raise Exception(f"Unexpected response format while listing rulesets: expected a list, got {type(payload).__name__}")
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
        raise Exception(
            "Cannot configure Copilot Code Review via both 'github.copilot_code_review' and 'github.rulesets'."
        )


def _expect_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise Exception(f"{field_name} must be a boolean")


def _expect_int(value: Any, field_name: str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.lstrip("-").isdigit():
            return int(normalized)
    raise Exception(f"{field_name} must be an integer")


def _expect_string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise Exception(f"{field_name} must be a list")
    if not all(isinstance(v, str) and v.strip() for v in value):
        raise Exception(f"{field_name} must contain non-empty strings only")
    return value


def _resolve_team_id(self: ASFGitHubFeature, team: Any, *, resolve_references: bool, team_cache: dict[str, int]) -> int:
    if isinstance(team, int):
        return team
    if not isinstance(team, str) or not team.strip():
        raise Exception("bypass_teams entries must be team slugs or numeric IDs")
    if not resolve_references:
        return -1
    if team not in team_cache:
        try:
            team_cache[team] = self.gh.get_organization(self.repository.org_id).get_team_by_slug(team).id
        except UnknownObjectException as exc:
            raise Exception(f"Unable to resolve bypass_team '{team}' to team ID") from exc
    return team_cache[team]


def _resolve_integration_id(
    self: ASFGitHubFeature, app_slug_or_id: Any, *, resolve_references: bool, app_cache: dict[str, int]
) -> int:
    if isinstance(app_slug_or_id, int):
        return app_slug_or_id
    if isinstance(app_slug_or_id, str):
        candidate = app_slug_or_id.strip()
        if not candidate:
            raise Exception("required_status_checks.app_slug cannot be empty")
        if candidate.lstrip("-").isdigit():
            return int(candidate)
        if not resolve_references:
            return -1
        if candidate not in app_cache:
            try:
                app = self.gh.get_app(candidate)
                app_cache[candidate] = app.id
            except UnknownObjectException as exc:
                raise Exception(f"Unable to resolve app_slug '{candidate}' to integration_id") from exc
        return app_cache[candidate]

    raise Exception("required_status_checks.app_slug must be a string or integer")


def _build_ref_name_condition(ruleset: dict[str, Any], target: str) -> dict[str, list[str]]:
    ref_config = ruleset.get("branches", ruleset.get("refs"))
    if ref_config is None:
        if target == "branch":
            return {"include": ["~DEFAULT_BRANCH"], "exclude": []}
        raise Exception("Tag rulesets must define branches.includes or refs.includes")

    if not isinstance(ref_config, dict):
        raise Exception("ruleset branches/refs must be a mapping")

    include_default = ["~DEFAULT_BRANCH"] if target == "branch" else None
    include = ref_config.get("includes", include_default)
    if include is None:
        raise Exception("ruleset branches/refs must define includes")

    exclude = ref_config.get("excludes", [])

    return {
        "include": _expect_string_list(include, "ruleset branches.includes"),
        "exclude": _expect_string_list(exclude, "ruleset branches.excludes"),
    }


def _build_bypass_actors(
    self: ASFGitHubFeature,
    ruleset: dict[str, Any],
    *,
    resolve_references: bool,
    team_cache: dict[str, int],
) -> list[dict[str, Any]]:
    teams = ruleset.get("bypass_teams", [])
    if not isinstance(teams, list):
        raise Exception("bypass_teams must be a list")

    bypass_mode = ruleset.get("bypass_mode", "always")
    if not isinstance(bypass_mode, str) or not bypass_mode.strip():
        raise Exception("bypass_mode must be a non-empty string")

    actors = []
    for team in teams:
        actors.append(
            {
                "actor_id": _resolve_team_id(self, team, resolve_references=resolve_references, team_cache=team_cache),
                "actor_type": "Team",
                "bypass_mode": bypass_mode,
            }
        )

    return actors


def _build_pull_request_rule(ruleset: dict[str, Any]) -> dict[str, Any] | None:
    has_reviews = "required_pull_request_reviews" in ruleset
    has_conversation_resolution = "required_conversation_resolution" in ruleset

    if not has_reviews and not has_conversation_resolution:
        return None

    required_review_thread_resolution = False
    if has_conversation_resolution:
        required_review_thread_resolution = _expect_bool(
            ruleset.get("required_conversation_resolution"), "required_conversation_resolution"
        )

    if not has_reviews and not required_review_thread_resolution:
        return None

    params: dict[str, Any] = {
        "required_review_thread_resolution": required_review_thread_resolution,
    }

    if has_reviews:
        reviews = ruleset.get("required_pull_request_reviews")
        if not isinstance(reviews, dict):
            raise Exception("required_pull_request_reviews must be a mapping")

        params["dismiss_stale_reviews_on_push"] = _expect_bool(
            reviews.get("dismiss_stale_reviews", False),
            "required_pull_request_reviews.dismiss_stale_reviews",
        )
        params["require_last_push_approval"] = _expect_bool(
            reviews.get("require_last_push_approval", False),
            "required_pull_request_reviews.require_last_push_approval",
        )
        params["require_code_owner_review"] = _expect_bool(
            reviews.get("require_code_owner_reviews", False),
            "required_pull_request_reviews.require_code_owner_reviews",
        )
        params["required_approving_review_count"] = _expect_int(
            reviews.get("required_approving_review_count", 0),
            "required_pull_request_reviews.required_approving_review_count",
        )

    return {"type": "pull_request", "parameters": params}


def _build_status_checks_rule(
    self: ASFGitHubFeature,
    ruleset: dict[str, Any],
    *,
    resolve_references: bool,
    app_cache: dict[str, int],
) -> dict[str, Any] | None:
    if "required_status_checks" not in ruleset:
        return None

    checks = ruleset.get("required_status_checks")
    if not isinstance(checks, list):
        raise Exception("required_status_checks must be a list")
    if not checks:
        return None

    strict = _expect_bool(ruleset.get("required_status_checks_strict", False), "required_status_checks_strict")

    normalized_checks: list[dict[str, Any]] = []
    for i, check in enumerate(checks):
        if isinstance(check, str):
            context = check
            app_source: Any = -1
        elif isinstance(check, dict):
            context = check.get("name", check.get("context"))
            app_source = check.get("app_slug", check.get("integration_id", -1))
        else:
            raise Exception(f"required_status_checks[{i}] must be a string or mapping")

        if not isinstance(context, str) or not context.strip():
            raise Exception(f"required_status_checks[{i}] must define a non-empty check name")

        normalized_checks.append(
            {
                "context": context,
                "integration_id": _resolve_integration_id(
                    self, app_source, resolve_references=resolve_references, app_cache=app_cache
                ),
            }
        )

    return {
        "type": "required_status_checks",
        "parameters": {
            "strict_required_status_checks_policy": strict,
            "required_status_checks": normalized_checks,
        },
    }


def _is_raw_ruleset_definition(ruleset: dict[str, Any]) -> bool:
    return any(key in ruleset for key in _RAW_RULESET_KEYS)


def _is_safety_rule_enabled(ruleset: dict[str, Any], field_name: str) -> bool:
    if field_name not in ruleset:
        return True
    return _expect_bool(ruleset.get(field_name), field_name)


def _to_payload_ruleset(
    self: ASFGitHubFeature,
    ruleset: dict[str, Any],
    *,
    resolve_references: bool,
    team_cache: dict[str, int],
    app_cache: dict[str, int],
) -> dict[str, Any]:
    if _is_raw_ruleset_definition(ruleset):
        mixed_keys = _CONVENIENCE_RULESET_KEYS.intersection(ruleset)
        if mixed_keys:
            mixed_keys_as_str = ", ".join(sorted(mixed_keys))
            raise Exception(f"Raw ruleset payload cannot mix convenience syntax keys: {mixed_keys_as_str}")
        return dict(ruleset)

    target = ruleset.get("type", "branch")
    if not isinstance(target, str) or target not in {"branch", "tag"}:
        raise Exception("ruleset type must be one of: branch, tag")

    payload: dict[str, Any] = {
        "name": ruleset["name"],
        "target": target,
        "enforcement": "active",
        "conditions": {
            "ref_name": _build_ref_name_condition(ruleset, target),
        },
    }

    bypass_actors = _build_bypass_actors(
        self,
        ruleset,
        resolve_references=resolve_references,
        team_cache=team_cache,
    )
    if bypass_actors:
        payload["bypass_actors"] = bypass_actors

    rules: list[dict[str, Any]] = []
    if "required_signatures" in ruleset and _expect_bool(ruleset.get("required_signatures"), "required_signatures"):
        rules.append({"type": "required_signatures"})
    if "required_linear_history" in ruleset and _expect_bool(
        ruleset.get("required_linear_history"), "required_linear_history"
    ):
        rules.append({"type": "required_linear_history"})
    if _is_safety_rule_enabled(ruleset, "restrict_deletion"):
        rules.append({"type": "deletion"})
    if _is_safety_rule_enabled(ruleset, "restrict_force_push"):
        rules.append({"type": "non_fast_forward"})

    pull_request_rule = _build_pull_request_rule(ruleset)
    if pull_request_rule:
        rules.append(pull_request_rule)

    status_checks_rule = _build_status_checks_rule(
        self,
        ruleset,
        resolve_references=resolve_references,
        app_cache=app_cache,
    )
    if status_checks_rule:
        rules.append(status_checks_rule)

    payload["rules"] = rules
    return payload


def normalize_rulesets(
    self: ASFGitHubFeature,
    rulesets: Any,
    *,
    resolve_references: bool = True,
) -> list[dict[str, Any]]:
    if rulesets is None:
        return []
    if not isinstance(rulesets, list):
        raise Exception("github.rulesets must be a list of mappings")

    normalized: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    team_cache: dict[str, int] = {}
    app_cache: dict[str, int] = {}

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
        normalized.append(
            _to_payload_ruleset(
                self,
                dict(ruleset),
                resolve_references=resolve_references,
                team_cache=team_cache,
                app_cache=app_cache,
            )
        )

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
    if "github_rulesets" not in self.instance.environments_enabled:
        return
    previous_yaml = self.previous_yaml if isinstance(self.previous_yaml, dict) else {}
    rulesets_configured = "rulesets" in self.yaml
    was_previously_configured = "rulesets" in previous_yaml

    if not rulesets_configured and not was_previously_configured:
        return

    noop_mode = self.noop("rulesets")
    desired_rulesets = (
        normalize_rulesets(self, self.yaml.get("rulesets"), resolve_references=not noop_mode)
        if rulesets_configured
        else []
    )
    ensure_no_copilot_overlap(desired_rulesets, is_copilot_code_review_enabled(self.yaml.get("copilot_code_review")))

    previous_managed_names = (
        get_ruleset_names(previous_yaml.get("rulesets", [])) if was_previously_configured else set()
    )

    if noop_mode:
        return

    reconcile_rulesets(self, desired_rulesets, previous_managed_names)
