import pathlib
import mappings


class Repository:
    """Simple class that holds information about the repository (and branch) being processed."""
    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.name = self.path.name.removesuffix(".git")

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


class Committer:
    """"Simple info class for committer(pusher) of code"""
    def __init__(self, username):
        self.username = username
        self.email = f"{username}@apache.org"
