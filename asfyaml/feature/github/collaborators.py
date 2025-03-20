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

"""GitHub collaborator features"""

import re

from . import directive, ASFGitHubFeature, constants


@directive
def collaborators(self: ASFGitHubFeature):
    # Collaborator list for triage rights
    collabs = self.yaml.get("collaborators", [])

    new_collabs = set(collabs)

    if collabs and self.repository.is_private:
        raise Exception("You cannot set outside collaborators for private repositories.")

    if len(new_collabs) > constants.MAX_COLLABORATORS:
        raise Exception(
            f"You can only have a maximum of {constants.MAX_COLLABORATORS} external triage collaborators, "
            f"please contact vp-infra@apache.org to request an exception."
        )

    for user in collabs:
        if not re.match(r"^[A-Za-z\d](?:[-A-Za-z\d]|-(?=[A-Za-z\d])){0,38}$", user):
            raise Exception("Username %s in collaborator list is not a valid GitHub ID!" % user)

    if self.can_access_live_data:
        existing_collaborators = {c.login: c.permissions for c in self.ghrepo.get_collaborators()}
    else:
        existing_collaborators = {}

    existing_collaborators_by_login = set(existing_collaborators)

    to_remove = existing_collaborators_by_login - new_collabs
    to_add = new_collabs - existing_collaborators_by_login

    def has_elevated_permissions(user_login: str) -> bool:
        permissions = existing_collaborators.get(user_login)
        if permissions is None:
            return False
        return permissions.push or permissions.maintain or permissions.admin

    # set of all existing collaborators with permissions other than triage
    to_modify = {u for u in new_collabs if has_elevated_permissions(u)}

    if len(to_add) > 0 or len(to_remove) > 0 or len(to_modify) > 0:
        print("Updating collaborator list:")

        for user in to_remove:
            print("  - Removing %s from list of collaborators" % user)
            if not self.noop("collaborators"):
                self.ghrepo.remove_from_collaborators(user)

        for user in to_add:
            print("  - Adding %s to list of collaborators with permission='triage'" % user)
            if not self.noop("collaborators"):
                self.ghrepo.add_to_collaborators(user, permission="triage")

        for user in to_modify:
            print("  - Modifying collaborator permissions for %s to permission='triage'" % user)
            if not self.noop("collaborators"):
                self.ghrepo.add_to_collaborators(user, permission="triage")
