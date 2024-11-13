#!/usr/bin/env python3
"""Environment variables carried over from earlier Git platforms."""

import os

DEBUG = False

if DEBUG:
    os.environ['PATH_INFO'] = 'debug'
    os.environ['GIT_PROJECT_ROOT'] = 'debug'
    os.environ['GIT_COMMITTER_NAME'] = 'debug'
    os.environ['GIT_COMMITTER_EMAIL'] = 'debug'
    os.environ['SCRIPT_NAME'] = 'debug'
    os.environ['WEB_HOST'] = 'debug'
    os.environ['WRITE_LOCK'] = 'debug'
    os.environ['AUTH_FILE'] = 'debug'


def _repo_name():
    path = filter(None, os.environ.get("PATH_INFO", '').split("/"))
    path = filter(lambda p: p != "git-receive-pack", list(path))
    plist = list(path)
    if len(plist) != 1:
        raise ValueError("Invalid PATH_INFO: %s" % os.environ.get("PATH_INFO"))
    return plist[0].removesuffix(".git")


def getvar(key, default: str = None):
    """Gets an OS env var, with a fallback value of None (or whatever)"""
    return os.environ.get(key, default)


class Environment:

    def __init__(self):
        self.repo_name = _repo_name()
        self.repo_dir = os.path.join(getvar("GIT_PROJECT_ROOT"), u"%s.git" % self.repo_name)
        self.committer = getvar("GIT_COMMITTER_NAME")
        self.remote_user = getvar("GIT_COMMITTER_EMAIL")
        self.script_name = getvar("SCRIPT_NAME")
        self.web_host = getvar("WEB_HOST")
        self.archived_lock = os.path.join(self.repo_dir, "nocommit")  # Lock file for archived read-only repositories
        self.write_locks = [getvar("WRITE_LOCK"), self.archived_lock]  # Global maintenance lock, plus archived locks
        self.auth_file = getvar("AUTH_FILE")
        self.ip = os.environ.get("REMOTE_ADDR", "127.0.0.1")

