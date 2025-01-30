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
