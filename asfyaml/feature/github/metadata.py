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

"""GitHub metadata features"""
import re
import os
from . import directive, ASFGitHubFeature


@directive
def set_labels(self: ASFGitHubFeature):
    # Labels for repo
    labels = self.yaml.get("labels")
    if labels:
        if len(labels) > 20:
            raise Exception("Too many GitHub labels/topics - must be <= 20 items!")
        for label in labels:
            if not re.match(r"^[-a-z0-9]{1,35}$", label):
                raise Exception(
                    f".asf.yaml: Invalid GitHub label '{label}' - must be lowercase alphanumerical and <= 35 characters!"
                )
        # Apply changes, unless we are in no-op (test) mode.
        if not self.noop("labels"):
            self.ghrepo.replace_topics(labels)


@directive
def set_homepage_desc(self: ASFGitHubFeature):
    desc = self.yaml.get("description")
    homepage = self.yaml.get("homepage")
    if desc and not self.noop("description"):
        self.ghrepo.edit(description=desc)
        # Update on gitbox as well
        desc_path = os.path.join(self.repository.path, "description")
        with open(desc_path, "w", encoding="utf8") as f:
            f.write(desc)
    if homepage and not self.noop("homepage"):
        self.ghrepo.edit(homepage=homepage)
