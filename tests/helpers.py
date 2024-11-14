#!/usr/bin/env python3
"""Simple pytest helper objects"""

import contextlib
import pytest

class YamlTest:
    """A validator test that has an expected outcome (exception, errormessage) and a YAML input"""
    def __init__(self, exc=None, errstr: str = None, yml=""):
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
