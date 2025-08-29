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
import strictyaml
import strictyaml.exceptions


class BranchPattern(strictyaml.ScalarValidator):
    """Validates regex patterns for branch matching with security constraints"""
    
    MAX_PATTERN_LENGTH = 1000  # Prevent ReDoS attacks
    
    def validate_scalar(self, chunk):
        pattern = chunk.contents.strip()
        
        # Basic validation
        if not pattern:
            chunk.expecting_but_found("pattern cannot be empty")
            
        if len(pattern) > self.MAX_PATTERN_LENGTH:
            chunk.expecting_but_found(f"pattern too long ({len(pattern)} chars), maximum {self.MAX_PATTERN_LENGTH}")
        
        # Validate regex compilation
        try:
            compiled = re.compile(pattern)
            # Test compilation with empty string to catch some ReDoS patterns early
            compiled.match("")
            return pattern
        except re.error as e:
            chunk.expecting_but_found(f"invalid regex pattern: {e}")
        except Exception as e:
            chunk.expecting_but_found(f"regex compilation error: {e}")
    
    def to_yaml(self, data):
        return str(data)


class EmptyValue(strictyaml.ScalarValidator):
    """Legacy YAML null type that supports the tilde null marker not considered proper by strictyaml:
    a: null
    a: ~  (also null)
    """

    def validate_scalar(self, chunk):
        val = chunk.contents
        if val.lower() not in ("null", "~"):
            chunk.expecting_but_found(f"when expecting a 'null', got '{val}' instead.")
        else:
            return self.empty(chunk)

    def empty(self, chunk):
        return None

    def to_yaml(self, data):
        if data is None:
            return "null"
        raise strictyaml.exceptions.YAMLSerializationError("expected None, got '{}'")
