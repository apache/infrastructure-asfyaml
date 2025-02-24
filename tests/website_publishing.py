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

"""Unit tests for .asf.yaml website publishing"""

import asfyaml.asfyaml
import asfyaml.dataobjects
from helpers import YamlTest

# Set .asf.yaml to debug mode
asfyaml.asfyaml.DEBUG = True

valid_staging = YamlTest(
    None,
    None,
    """
staging:
  subdir: foo
  profile: foo
  autostage: foo/*
""",
)

# Valid staging section, but invalid subdir directive
invalid_staging_subdir_slash = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "cannot start with a forward slash",
    """
staging:
  subdir: /foo
  autostage: foo/*
""",
)

# Valid staging section, but invalid profile directive
invalid_staging_bad_profile = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "Must only contain permitted DNS characters",
    """
staging:
  profile: a+b+c
  autostage: foo/*
""",
)

# Valid staging section, but invalid autostage directive
invalid_staging_bad_autostage = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "autostage parameter must be",
    """
staging:
  profile: a+b+c
  autostage: foo/bar
""",
)

# Valid staging section, but invalid unknown directive
invalid_staging_unknown_directive = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "key not in schema",
    """
staging:
  blorp: foo
  autostage: foo/bar
""",
)

# Valid publish section
valid_publish = YamlTest(
    None,
    None,
    """
publish:
  whoami: main
  subdir: foobar
  type: website
""",
)

# Valid publish, but invalid hostname
invalid_publish_hostname = YamlTest(
    asfyaml.asfyaml.ASFYAMLException,
    "you cannot specify .*?apache.org hostnames, they must be inferred!",
    """
publish:
  whoami: main
  subdir: foobar
  type: website
  hostname: foo.apache.org
""",
)


def test_basic_yaml(test_repo: asfyaml.dataobjects.Repository):
    print("STAGING TESTS")

    tests_to_run = (
        valid_staging,
        invalid_staging_subdir_slash,
        invalid_staging_bad_profile,
        invalid_staging_bad_autostage,
        invalid_staging_unknown_directive,
    )

    for test in tests_to_run:
        with test.ctx() as vs:
            a = asfyaml.asfyaml.ASFYamlInstance(test_repo, "humbedooh", test.yaml)
            a.environments_enabled.add("noop")
            a.run_parts()

    print("PUBLISHING TESTS")
    tests_to_run = (
        valid_publish,
        invalid_publish_hostname,
    )

    for test in tests_to_run:
        with test.ctx() as vs:
            a = asfyaml.asfyaml.ASFYamlInstance(test_repo, "humbedooh", test.yaml)
            a.environments_enabled.add("noop")
            a.run_parts()
