# Simple init that gathers all the features and short-circuits ASFYamlFeature so it won't shadow itself inside
# the features.
from asfyaml import ASFYamlFeature

from . import testfeature
