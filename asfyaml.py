#!/usr/bin/env python3
import strictyaml

DEFAULT_ENVIRONMENT = "production"
DEBUG = False


class ASFYamlInstance:
    def __init__(self, config_data: str):
        self.yaml = strictyaml.load(config_data)

        # TODO: Set up repo details inside this class (repo name, file-path, project, private/public, etc)

        # Sort out which environments we are going to be using. This will determine which
        # features to add, or which version of a feature to use.
        self.environments_enabled = {DEFAULT_ENVIRONMENT}
        if "meta" in self.yaml:
            if "environment" in self.yaml["meta"]:
                self.environments_enabled.add(str(self.yaml["meta"]["environment"]))
        if DEBUG:
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
                # Everything seems in order, spin up an instance of the feature class and run it with our sub-yaml
                feature = feature_class(self, yaml_parsed)
                feature.run()
            elif feature_name != "meta":  # meta is reserved for asfyaml.py, all else needs a feature or it should break.
                raise KeyError(f"No such .asf.yaml feature: {feature_name}")


class ASFYamlFeature:
    features = []  # List for tracking all sub-classes we come across in any environment.

    def __init__(self, parent: ASFYamlInstance, yaml: dict):
        self.yaml = yaml  # Our sub-yaml for this feature
        self.instance = parent  # This is the parent .asf.yaml instance class

    def __init_subclass__(cls, name: str, env: str = "production", **kwargs):
        """Instantiates a new sub-class of ASFYamlFeature. The `name` argument should be the
        top dict keyword for this feature in .asf.yaml, for instance 'github' or 'pelican'.
        The `env` variable can be used to denote which environment this .asf.yaml feature will
        be available in. The default environment is 'production', but this can be any name."""
        cls.name = name
        cls.env = env
        cls.features.append(cls)
        super().__init_subclass__(**kwargs)


# Import all the feature classes. TODO: move this import elsewhere.
from feature import *

