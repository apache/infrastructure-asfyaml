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

"""GitHub Actions OIDC subject claim support.

Sets the format of the ``sub`` claim in the OIDC tokens GitHub Actions issues for the
repository: the immutable, ID-based format, and optionally a custom set of claim keys. See
https://docs.github.com/rest/actions/oidc#set-the-customization-template-for-an-oidc-subject-claim-for-a-repository
"""

import json
import re
from typing import Any

from . import directive, ASFGitHubFeature

# GitHub accepts claim keys made of alphanumerics and underscores only.
CLAIM_KEY_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _oidc_subject_url(self: ASFGitHubFeature) -> str:
    return f"/repos/{self.repository.org_id}/{self.repository.name}/actions/oidc/customization/sub"


def _check_oidc_subject_response(self: ASFGitHubFeature, status: int, body: str) -> None:
    """Raise unless GitHub accepted the OIDC subject claim update."""
    if 200 <= status < 300:
        return
    try:
        parsed = json.loads(body)
        detail = str(parsed.get("errors") or parsed.get("message") or body)
    except (json.JSONDecodeError, AttributeError):
        detail = body
    repo = f"{self.repository.org_id}/{self.repository.name}"
    match status:
        case 400:
            raise Exception(f"GitHub rejected the OIDC subject claim settings for '{repo}': {detail}")
        case 403:
            raise Exception(f"Not allowed to set the OIDC subject claim on '{repo}': {detail}")
        case 404:
            raise Exception(f"Repository '{repo}' not found or not accessible: {detail}")
        case 422:
            raise Exception(f"Validation failed while setting the OIDC subject claim: {detail}")
        case _:
            raise Exception(f"Unexpected response while setting the OIDC subject claim: HTTP {status}: {detail}")


@directive
def oidc_subject(self: ASFGitHubFeature):
    oidc = self.yaml.get("oidc_subject")

    previous_yaml = self.previous_yaml if isinstance(self.previous_yaml, dict) else {}
    was_previously_configured = "oidc_subject" in previous_yaml

    if oidc is not None:
        use_immutable_subject = oidc.get("use_immutable_subject")
        include_claim_keys = oidc.get("include_claim_keys")
    elif was_previously_configured:
        # The section was removed; go back to GitHub's default claim template.
        use_immutable_subject = None
        include_claim_keys = None
    else:
        return

    if include_claim_keys is not None:
        if not include_claim_keys:
            raise Exception("github.oidc_subject.include_claim_keys must list at least one claim key")
        invalid = [key for key in include_claim_keys if not CLAIM_KEY_RE.match(key)]
        if invalid:
            raise Exception(
                "github.oidc_subject.include_claim_keys may only contain letters, digits and underscores, "
                f"got {', '.join(invalid)}"
            )
        if len(set(include_claim_keys)) != len(include_claim_keys):
            raise Exception("github.oidc_subject.include_claim_keys must not repeat a claim key")

    payload: dict[str, Any] = {"use_default": include_claim_keys is None}
    if include_claim_keys is not None:
        payload["include_claim_keys"] = list(include_claim_keys)
    # Only sent when written down: turning the immutable format off breaks every cloud trust
    # policy written for it, so dropping the key (or the section) leaves the format as it is.
    if use_immutable_subject is not None:
        payload["use_immutable_subject"] = use_immutable_subject

    if include_claim_keys is None:
        print("Setting OIDC subject claim to the default template")
    else:
        print(f"Setting OIDC subject claim to the custom template: {', '.join(include_claim_keys)}")
    if use_immutable_subject is not None:
        print(f"OIDC subject claim {'uses' if use_immutable_subject else 'does not use'} the immutable format")

    if not self.noop("oidc_subject"):
        status, _headers, body = self.ghrepo._requester.requestJson("PUT", _oidc_subject_url(self), input=payload)
        _check_oidc_subject_response(self, status, body)
