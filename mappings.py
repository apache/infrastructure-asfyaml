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
