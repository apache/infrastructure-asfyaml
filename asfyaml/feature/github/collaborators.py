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
import os
from . import directive, ASFGitHubFeature, constants


@directive
def collaborators(self: ASFGitHubFeature):
    # Collaborator list for triage rights
    collabs = self.yaml.get("collaborators", [])

    old_collabs = set()
    new_collabs = set(collabs)
    if collabs and self.repository.is_private:
        raise Exception("You cannot set outside collaborators for private repositories.")
    if len(new_collabs) > constants.MAX_COLLABORATORS:
        raise Exception(
            f"You can only have a maximum of {constants.MAX_COLLABORATORS} external triage collaborators, please contact vp-infra@apache.org to request an exception."
        )
    for user in collabs:
        if not re.match(r"^[A-Za-z\d](?:[-A-Za-z\d]|-(?=[A-Za-z\d])){0,38}$", user):
            raise Exception("Username %s in collaborator list is not a valid GitHub ID!" % user)
    collab_file = os.path.join(self.repository.path, "github_collaborators.txt")
    if os.path.exists(collab_file):
        old_collabs = set([x.strip() for x in open(collab_file) if x.strip()])
    if new_collabs != old_collabs:
        print("Updating collaborator list for GitHub")
        to_remove = old_collabs - new_collabs
        to_add = new_collabs - old_collabs
        for user in to_remove:
            print("Removing GitHub triage access for %s" % user)
            self.ghrepo.remove_from_collaborators(user)
        for user in to_add:
            print("Adding GitHub triage access for %s" % user)
            self.ghrepo.add_to_collaborators(user)
        with open(collab_file, "w") as f:
            f.write("\n".join(collabs))
            f.close()
