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

"""GitHub custom subjects for prs/issues/discussions etc"""
from . import directive, ASFGitHubFeature, constants
import re

def validate_github_subject(subject):
    """Validates a github subject template:
     - MUST only contain valid references
     - MUST be a non-empty string
     - MUST not contain any reserved chars (newlines etc)
    """
    bad_chars = ("\r", "\n")
    assert isinstance(subject, str), "Subject template must be a string"
    assert subject, "Subject template must not be empty"
    assert not any(bad_char in subject for bad_char in bad_chars), "Subject template must not contain newlines!"
    found_refs = [x.group(1) for x in re.finditer(r"{(.+?)}", subject)]
    for ref in found_refs:
        assert ref in constants.VALID_GITHUB_SUBJECT_VARIABLES, f"Unknown variable '{ref}' found in subject template."

@directive
def config_custom_subjects(self: ASFGitHubFeature):
    # Custom subjects for events
    custom_subjects = self.yaml.get("custom_subjects")
    if custom_subjects and isinstance(custom_subjects, dict):
        # Validate each template
        for key, subject in custom_subjects.items():
            assert key in constants.VALID_GITHUB_ACTIONS, f"Unknown action '{key}' found in custom_subjects!"
            validate_github_subject(subject)
