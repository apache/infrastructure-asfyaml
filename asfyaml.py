#!/usr/bin/env python3
import strictyaml
import easydict
import repository
DEFAULT_ENVIRONMENT = "production"
DEBUG = False


# Default priority for features. If set to this, they will be executed in the order they appear
# in the YAML. If a priority other than this (five) is set, the feature will be moved ahead or
# behind the rest in the feature run queue, depending on the integer value. Features are run
# according to their priority level, going from priority 0 to 10.
DEFAULT_PRIORITY = 5


class FeatureList(dict):
    """Simple dictionary-style object with a default return value of None for non-existent features"""
    def __init__(self):
        super().__init__()

    def __getattr__(self, item):
        return super(FeatureList, self).get(item)

    def __setattr__(self, key, value):
        super(FeatureList, self).__setattr__(key, value)
        super(FeatureList, self).__setitem__(key, value)


class ASFYamlInstance:
    def __init__(self, repo: repository.Repository, committer: str, config_data: str):
        self.yaml = strictyaml.load(config_data)
        self.repository = repo
        self.committer = repository.Committer(committer)
        self.features = FeatureList()  # Placeholder for enabled and verified features during runtime.
        # TODO: Set up repo details inside this class (repo name, file-path, project, private/public, etc)

        # Sort out which environments we are going to be using. This will determine which
        # features to add, or which version of a feature to use.
        self.environments_enabled = {DEFAULT_ENVIRONMENT}
        if "meta" in self.yaml:
            if "environment" in self.yaml["meta"]:
                self.environments_enabled.add(str(self.yaml["meta"]["environment"]))
        if DEBUG:
            print("")
            print(f"Using environment(s): {', '.join(self.environments_enabled)}")

        # Make a list of enabled features for this repo, based on the environments enabled for it.
        # Features are loaded in environment order, sop later environments can override features from other envs.
        # For instance, a production+test env list would load all production features and mix in test
        # features, overriding any features that are already in production.
        self.enabled_features = {}
        for env in self.environments_enabled:
            for feat in ASFYamlFeature.features:
                if feat.env == env:
                    self.enabled_features[feat.name] = feat
        if DEBUG:
            print(f"Enabled features for this run: {', '.join(self.enabled_features.keys())}")
            print(f"Features seen inside .asf.yaml: {', '.join([str(x) for x in self.yaml.keys()])}")

    def run_parts(self):

        # For each enabled feature, spin up validation and runtime processing if directives are found
        # for the feature inside our .asf.yaml file.
        features_to_run = []
        for feature_name, feature_yaml in self.yaml.items():
            if feature_name in self.enabled_features:
                feature_yaml_as_string = feature_yaml.as_yaml()
                feature_class = self.enabled_features[feature_name]
                # If the feature has a schema, validate the sub-yaml before running the feature.
                if hasattr(feature_class, "schema"):
                    try:
                        yaml_parsed = strictyaml.load(feature_yaml_as_string, feature_class.schema)
                    except strictyaml.exceptions.YAMLValidationError as e:
                        feature_start = feature_yaml.start_line
                        problem_line = feature_start + e.problem_mark.line
                        problem_column = e.problem_mark.column
                        # TODO: Make this much more reader friendly!
                        print(problem_line, problem_column, str(e))
                        raise e  # Just pass back the original exception for now
                else:
                    yaml_parsed = strictyaml.load(feature_yaml_as_string)
                # Everything seems in order, spin up an instance of the feature class for future use.
                feature = feature_class(self, yaml_parsed)
                features_to_run.append(feature)
                # Log that this feature is enabled, configured, and validated. For cross-feature access.
                self.features[str(feature_name)] = feature
            elif feature_name != "meta":  # meta is reserved for asfyaml.py, all else needs a feature or it should break.
                raise KeyError(f"No such .asf.yaml feature: {feature_name}")

        # If everything validated okay, we will sort the features by priority and then run them
        for feature in sorted(features_to_run, key=lambda x: x.priority):
            feature.run()

class ASFYamlFeature:
    features = []  # List for tracking all sub-classes we come across in any environment.

    def __init__(self, parent: ASFYamlInstance, yaml: strictyaml.YAML):
        self.yaml_raw = yaml.data  # The YAML configuration for this feature, in raw format.
        self.yaml = easydict.EasyDict(yaml.data)  # The YAML, but in EasyDict format.
        self.instance = parent  # This is the parent .asf.yaml instance class.
        self.repository = parent.repository  # The repository we're working on, and its push info.
        self.committer = parent.committer

    def __init_subclass__(cls, name: str, env: str = "production", priority: int = DEFAULT_PRIORITY, **kwargs):
        """Instantiates a new sub-class of ASFYamlFeature. The `name` argument should be the
        top dict keyword for this feature in .asf.yaml, for instance 'github' or 'pelican'.
        The `env` variable can be used to denote which environment this .asf.yaml feature will
        be available in. The default environment is 'production', but this can be any name."
        If a priority other than the default (5) is set, the feature will be run based on
        that priority level (0 is highest, 10 lowest)m otherwise it will be run in order of
        appearance in the YAML with the rest of the default priority features."""
        cls.name = name
        cls.env = env
        cls.features.append(cls)
        cls.priority = priority
        super().__init_subclass__(**kwargs)


# Import all the feature classes. TODO: move this import elsewhere.
from feature import *

