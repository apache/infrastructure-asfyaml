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

"""GitHub merge buttons"""
from . import directive, ASFGitHubFeature


@directive
def enabled_merge_buttons(self: ASFGitHubFeature):
    # Merge buttons
    merges = self.yaml.get("enabled_merge_buttons")
    if merges:
        if not self.noop("enabled_merge_buttons"):
            self.ghrepo.edit(
                allow_squash_merge=merges.get("squash", False),
                allow_merge_commit=merges.get("merge", False),
                allow_rebase_merge=merges.get("rebase", False),
            )
