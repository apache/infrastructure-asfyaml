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

"""GitHub protected tags feature. Doesn't work atm, GitHub has EOL'ed tag protections
in favor of rulesets, which has not been implemented in .asf.yaml yet."""
from . import directive, ASFGitHubFeature

@directive
def configure_protected_tags(self: ASFGitHubFeature):
    # Jira auto-linking
    protected_tags = self.yaml.get("protected_tags", [])
    if protected_tags:
        print("Notice: protected_tags are currently not supported, so this setting will not apply.")
