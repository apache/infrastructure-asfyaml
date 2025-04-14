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

"""Simple pytest helper objects"""

import contextlib
import pytest

class YamlTest:
    """A validator test that has an expected outcome (exception, errormessage) and a YAML input"""
    def __init__(self, exc = None, errstr: str | None = None, yml: str = ""):
        self.exception = exc
        self.errmsg = errstr
        self.yaml = yml

    @contextlib.contextmanager
    def ctx(self):
        if self.exception:
            if self.errmsg:
                my_ctx = pytest.raises(self.exception, match=self.errmsg)
            else:
                my_ctx = pytest.raises(self.exception)
        else:
            my_ctx = contextlib.nullcontext()
        with my_ctx:
            try:
                yield self
            finally:
                pass
