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

import pathlib
import asfyaml.mappings as mappings
import os
import subprocess

DEFAULT_BRANCH = "main"
GIT_CMD = "/usr/bin/git"
# COMMIT_FIELDS represent the data points we collect from commits when iterating over the change-sets
COMMIT_FIELDS = [
    ("commit", "%h"),
    ("parents", "%p"),
    ("tree", "%t"),
    ("author", "%aN <%ae>"),
    ("authored", "%ad"),
    ("author_name", "%aN"),
    ("author_email", "%ae"),
    ("committer", "%cN <%ce>"),
    ("committer_email", "%ce"),
    ("committed", "%cd"),
    ("committed_unix", "%ct"),
    ("ref_names", "%d"),
    ("subject", "%s"),
    ("body", "%B")
]


def gitcmd(*args):
    """Runs a git command and returns the output as a string"""
    xargs = list(args)
    xargs.insert(0, GIT_CMD)
    try:
        rv = subprocess.check_output(xargs, stderr=subprocess.PIPE, universal_newlines=True)
    except subprocess.CalledProcessError as e:
        print(e.stderr)
        rv = ""
    return rv


class Committer:
    """"Simple info class for committer(pusher) of code"""
    def __init__(self, username):
        #: str: The ASF user id of the person that pushed this commit, for instance :samp:`humbedooh`
        self.username = username
        #: str: The ASF email address of the person that pushed this commit, for instance :samp:`humbedooh@apache.org`.
        self.email = f"{username}@apache.org"



class Commit(object):
    def __init__(self, ref, sha):
        self.ref = ref
        self.sha = sha

        fmt = "--format=format:%s%%x00" % r'%x00'.join([s for _, s in COMMIT_FIELDS])
        args = ["show", "--stat=75", fmt, self.sha]
        parts = gitcmd(*args).split("\x00")

        self.stats = u"\n".join(filter(None, parts.pop(-1).splitlines()))
        for pos, (key, _) in enumerate(COMMIT_FIELDS):
            setattr(self, key, parts[pos])

        self.committed_unix = int(self.committed_unix)
        parts = self.committer_email.split(u"@")
        self.committer_uname = parts[0]
        if len(parts) > 1:
            self.committer_domain = parts[1]
        else:
            self.committer_domain = ""

    def __cmp__(self, other):
        return self.committed_unix == other.committed_unix

    @property
    def is_merge(self):
        return len(self.parents.split()) > 1

    @property
    def files(self):
        files = gitcmd("show", "--name-only", "--format=format:", self.sha)
        return [l.strip() for l in files.splitlines() if l.strip()]

    def diff(self, fname):
        args = ["show", "--format=format:", self.sha, "--", fname]
        return gitcmd(*args).lstrip()


class ChangeSet(object):
    def __init__(self, name, oldsha, newsha):
        self.name = name
        self.oldsha = oldsha
        self.newsha = newsha

    @property
    def created(self):
        """Returns True if this tag or branch was just created"""
        return self.oldsha == ("0" * 40)

    @property
    def deleted(self):
        """Returns True if this branch or tag was deleted"""
        return self.newsha == ("0" * 40)

    @property
    def is_tag(self):
        """Returns True if this ref is a tag rather than a branch"""
        return self.name.startswith("refs/tags/")

    @property
    def is_branch(self):
        """Returns True if this ref is a branch rather than a tag"""
        return self.name.startswith("refs/heads/")

    @property
    def is_rewrite(self):
        """Returns true if this is a history rewrite"""
        return self.merge_base != self.oldsha

    @property
    def commits(self, num=None, reverse=False):
        """Lists all commits in this ref update as Commit objects"""
        # Deleted refs have no commits.
        if self.deleted:
            return
        # Only report commits that aren't reachable from any other branch
        refs = []
        args = ["for-each-ref", "--format=%(refname)"]

        for r in gitcmd(*args).splitlines():
            if r.strip() == self.name:
                continue
            if r.strip().startswith("refs/heads/"):
                refs.append("^%s" % r.strip())
        args = ["rev-list"]
        if num is not None:
            args += ["-n", str(num)]
        if reverse:
            args.append("--reverse")
        if self.created:
            args += refs
            args.append(self.newsha)
        else:
            args.append("%s..%s" % (self.oldsha, self.newsha))
        for line in gitcmd(*args).splitlines():
            sha = line.strip()
            yield Commit(self, sha)

    @property
    def merge_base(self):
        """finds the best common ancestor(s) between two commits to use in a three-way merge."""
        if ("0" * 40) in (self.oldsha, self.newsha):
            return "0" * 40
        sha = gitcmd("merge-base", self.oldsha, self.newsha)
        return sha.strip()



class Repository:
    """Simple class that holds information about the repository (and branch) being processed.

    :parameter path: The filesystem path to the .git directory for this repository.

    Example::

        import dataobjects
        repo = dataobjects.Repository("/x1/repos/asf/tomcat/tomcat9.git")
        assert repo.is_private is False, "This should not be a private repo!"
        website = f"https://{repo.hostname}.apache.org/"

    """
    def __init__(self, path, reflog="", org_id: str = "apache"):
        #: str|Pathlike: The filesystem path to this repository directory
        self.path = pathlib.Path(path)
        #: str: The name of this repository (sans the .git part), for instance :samp:`whimsy-website`.
        self.name = self.path.name.removesuffix(".git")
        #: str: Ref update log, if found. Follows standard git syntax, one entry per line
        #  with: "oldsha newsha refname". Used for populating self.changesets
        self._reflog = reflog or ""
        #: str: The GitHub organization this repository belongs to, by default `apache`.
        self.org_id = org_id

    @property
    def is_private(self):
        """"Set to True if the repository is a private repository, False if it is public"""
        return "private" in self.path.parts

    @property
    def project(self):
        """Returns the LDAP name of the project owning this repository, for instance httpd or openoffice"""
        match = mappings.REPO_RE.match(self.name)
        if match:
            return match.group(1)
        return "infrastructure"   # Weird repo name, default to infra owning it.

    @property
    def hostname(self):
        """Returns the hostname for the project. httpd for httpd, but whimsical for whimsy."""
        return mappings.LDAP_TO_HOSTNAME.get(self.project, self.project)

    @property
    def default_branch(self):
        """Returns the default branch for this repository."""
        head_path = os.path.join(self.path, "HEAD")
        if os.path.isfile(head_path):
            hb = open(head_path).read().removeprefix("ref: refs/heads/").strip()
        else:
            hb = DEFAULT_BRANCH
        return hb


    @property
    def changesets(self):
        """Yields a ChangeSet for each ref update seen in this push.
        Each ChangeSet can have several commits bundled"""
        for line in self._reflog.splitlines():
            oldsha, newsha, name = line.split(None, 2)
            yield ChangeSet(name.strip(), oldsha, newsha)

