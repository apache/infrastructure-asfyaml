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

"""Validates the JSON Schemas shipped next to the feature modules.

Checks that every *.schema.json file is a valid draft-07 schema whose $id
mirrors its location in the repository, and validates known-good and
known-bad .asf.yaml samples against the root schema. Cross-file $refs are
resolved offline through a registry keyed by $id.
"""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft7Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_ROOT = REPO_ROOT / "asfyaml"
RAW_URL_BASE = "https://raw.githubusercontent.com/apache/infrastructure-asfyaml/refs/heads/main/"

SCHEMA_FILES = sorted(SCHEMA_ROOT.rglob("*.schema.json"))
ROOT_SCHEMA_FILE = SCHEMA_ROOT / "asfyaml.schema.json"

FIXTURE_ROOT = REPO_ROOT / "tests" / "data" / "schema"
VALID_FIXTURES = sorted((FIXTURE_ROOT / "valid").glob("*.yaml")) + [REPO_ROOT / "tests" / "data" / "basic-dev-env.yaml"]
INVALID_FIXTURES = sorted((FIXTURE_ROOT / "invalid").glob("*.yaml"))


def _load_schema(path: Path) -> dict:
    return json.loads(path.read_text())


def _relative_id(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _root_validator() -> Draft7Validator:
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema, default_specification=DRAFT7))
        for schema in map(_load_schema, SCHEMA_FILES)
    )
    return Draft7Validator(_load_schema(ROOT_SCHEMA_FILE), registry=registry)


@pytest.mark.parametrize("schema_file", SCHEMA_FILES, ids=_relative_id)
def test_schema_is_valid_draft7(schema_file: Path):
    Draft7Validator.check_schema(_load_schema(schema_file))


@pytest.mark.parametrize("schema_file", SCHEMA_FILES, ids=_relative_id)
def test_schema_id_mirrors_path(schema_file: Path):
    """Relative $refs resolve against $id, so $id must mirror the file location."""
    expected = RAW_URL_BASE + schema_file.relative_to(REPO_ROOT).as_posix()
    assert _load_schema(schema_file)["$id"] == expected


@pytest.mark.parametrize("fixture", VALID_FIXTURES, ids=lambda p: p.name)
def test_valid_asfyaml(fixture: Path):
    document = yaml.safe_load(fixture.read_text())
    errors = list(_root_validator().iter_errors(document))
    assert not errors, "\n".join(f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in errors)


@pytest.mark.parametrize("fixture", INVALID_FIXTURES, ids=lambda p: p.name)
def test_invalid_asfyaml(fixture: Path):
    document = yaml.safe_load(fixture.read_text())
    assert list(_root_validator().iter_errors(document)), "expected validation errors, got none"
