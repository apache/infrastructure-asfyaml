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

import re

# LDAP to hostname mappings for certain projects.
# We'll get this centralized somewhere...someday.
LDAP_TO_HOSTNAME = {
    'whimsy': 'whimsical',
    'empire': 'empire-db',
    'webservices': 'ws',
    'infrastructure': 'infra',
    'comdev': 'community',
}

# Repository filename syntax for inferring project names.
REPO_RE = re.compile(r"(?:incubator-)?([^-.]+)")

# Mailing list overrides. Also to be centralized elsewhere.
ML_OVERRIDES = {
    "www-site": "site-cvs@apache.org",
    "apachecon-planning": "private@apachecon.com",
    "privacy-website": "privacy-commits@apache.org",
}

# Repositories that override hostname for publishing
WS_HOSTNAME_OVERRIDES = {
    "comdev-events-site": "events.apache.org",
    "logging-flume-site": "flume.apache.org",
}
