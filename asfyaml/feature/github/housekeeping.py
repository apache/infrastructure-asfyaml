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

"""GitHub housekeeping features: delete branch on merge, dependabot.."""
from . import directive, ASFGitHubFeature

@directive
def housekeeping_features(self: ASFGitHubFeature):
    del_branch_on_merge = self.yaml.get("del_branch_on_merge", None)
    if del_branch_on_merge is not None and not self.noop("del_branch_on_merge"):
        self.ghrepo.edit(delete_branch_on_merge=del_branch_on_merge)

    dependabot_alerts = self.yaml.get("dependabot_alerts", None)
    if dependabot_alerts is not None and not self.noop("dependabot_alerts"):
        if dependabot_alerts is True:
            self.ghrepo.enable_vulnerability_alert()
        elif dependabot_alerts is False:
            self.ghrepo.disable_vulnerability_alert()

    dependabot_updates = self.yaml.get("dependabot_updates", None)
    if dependabot_updates is not None and not self.noop("dependabot_updates"):
        if dependabot_updates is True:
            self.ghrepo.enable_automated_security_fixes()
        elif dependabot_updates is False:
            self.ghrepo.disable_automated_security_fixes()
