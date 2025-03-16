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

import strictyaml
import strictyaml.ruamel.scanner
import easydict
import asfyaml.dataobjects as dataobjects
import asfyaml.envvars as envvars

DEFAULT_ENVIRONMENT = "production"
DEBUG = False

# Default priority for features. If set to this, they will be executed in the order they appear
# in the YAML. If a priority other than this (five) is set, the feature will be moved ahead or
# behind the rest in the feature run queue, depending on the integer value. Features are run
# according to their priority level, going from priority 0 to 10.
DEFAULT_PRIORITY = 5


class ASFYAMLException(Exception):
    def __init__(self, repository: dataobjects.Repository, branch: str, feature: str = "", error_message: str = ""):
        self.repository = repository
        self.branch = branch
        self.feature = feature
        self.error_message = error_message

    def __str__(self):
        return self.error_message


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
    """This is the base instance class for a .asf.yaml process. It contains all the enabled features,
    as well as the repository and committer data needed to process events.
    """

    def __init__(self, repo: dataobjects.Repository, committer: str, config_data: str, branch: str | None = None):
        self.repository = repo
        self.committer = dataobjects.Committer(committer)
        if branch and branch.startswith("refs/heads/"):
            self.branch = branch[11:]  # If actual branch, crop and set
        else:
            self.branch = dataobjects.DEFAULT_BRANCH  # Not a valid branch pattern, set to default branch

        # Load YAML and, if any parsing errors happen, bail and raise exception
        try:
            self.yaml = strictyaml.dirty_load(config_data, label=f"{repo.name}.git/.asf.yaml", allow_flow_style=True)
        except strictyaml.ruamel.scanner.ScannerError as e:
            raise ASFYAMLException(repository=self.repository, branch=self.branch, feature="main", error_message=str(e))

        self.features = FeatureList()  # Placeholder for enabled and verified features during runtime.
        self.environment = envvars.Environment()
        self.no_cache = False  # Set "cache: false" in the meta section to force a complete parse in all features.
        # TODO: Set up repo details inside this class (repo name, file-path, project, private/public, etc)

        # Sort out which environments we are going to be using. This will determine which
        # features to add, or which version of a feature to use.
        self.environments_enabled = {DEFAULT_ENVIRONMENT}
        if "meta" in self.yaml:
            # environment: fooenv
            # merges a single environment with production
            if "environment" in self.yaml["meta"]:
                self.environments_enabled.add(str(self.yaml["meta"]["environment"]))
                self.no_cache = self.yaml["meta"].get("cache", True) is False
            # environments:
            #   - foobar
            #   - barbaz
            # merges a list of environments with production.
            # Merging happens in order of appearance in the yaml configuration, so having environments
            # a, b, c in the configuration will be based off production, with features then added or
            # overridden by a, then b, then c.
            if "environments" in self.yaml["meta"]:
                for env in self.yaml["meta"]["environments"]:
                    self.environments_enabled.add(str(env))
                self.no_cache = self.yaml["meta"].get("cache", True) is False
        if DEBUG:
            print("")
            print(f"Using environment(s): {', '.join(self.environments_enabled)}")

        self.enabled_features = {}
        """: FeatureList: This variable contains all features that are enabled for this run, as an object with of all the features that are enabled and their class instances as attributes.
        Each feature is accessible as an attribute with the feature name as key, for instance :code:`self.instance.enabled_features.gitub`.
        If a feature is not available (not enabled or not configured), a None value will be returned instead, 
        allowing you to easily test for whether a feature is enabled or not without running into key errors.
         
        Example use::
        
            class ASFTestFeature(ASFYamlFeature, name="test", priority=4):
                def run(self):
                    # Check if we have notification features enabled for this repo or not
                    notifs = self.instance.enabled_features.notifications
                    if notifs:  # If notifications are in use...
                        # The notifications feature runs before the rest, so we can
                        # access its data already.
                        print(f"We have these mailing lis targets: {notifs.valid_targets}")
                    else:
                        raise Exception("You need to enable notifications!")
        
        As the :class:`FeatureList` object acts like a dictionary (more precisely, like an EasyDict), 
        you can inspect the list as a dictionary and learn which features are currently enabled::
        
            def run(self):
                features_we_have = ", ".join(self.instance.enabled_features)  # Dicts act like lists of keys in join
                print(f"The following is enabled: {features_we_have}")  # Could be "notifications, github, jekyll"
        """

        # Make a list of enabled features for this repo, based on the environments enabled for it.
        # Features are loaded in environment order, sop later environments can override features from other envs.
        # For instance, a production+test env list would load all production features and mix in test
        # features, overriding any features that are already in production.
        for env in self.environments_enabled:
            for feat in ASFYamlFeature.features:
                if feat.env == env:
                    self.enabled_features[feat.name] = feat
        if DEBUG:
            print(f"Enabled features for this run: {', '.join(self.enabled_features.keys())}")
            print(f"Features seen inside .asf.yaml: {', '.join([str(x) for x in self.yaml.keys()])}")

    def run_parts(self, validate_only: bool = False):
        """Runs every enabled and configured feature for the .asf.yaml file.
        If an exception is encountered, the processing will halt at the module that raised
        it, and an email with the error message(s) will be sent to the git client as well as
        private@$project.apache.org. The validate_only flag will cause run_parts to only run
        the validation part and then exit immediately afterwards"""
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
                        yaml_parsed = strictyaml.dirty_load(
                            feature_yaml_as_string,
                            feature_class.schema,
                            label=f"{self.repository.name}.git/.asf.yaml::{feature_name}",
                            allow_flow_style=True,
                        )
                    except strictyaml.exceptions.YAMLValidationError as e:
                        feature_start = feature_yaml.start_line
                        problem_line = feature_start + e.problem_mark.line
                        problem_column = e.problem_mark.column
                        # TODO: Make this much more reader friendly!
                        raise ASFYAMLException(
                            repository=self.repository, branch=self.branch, feature=feature_name, error_message=str(e)
                        )
                else:
                    yaml_parsed = strictyaml.load(feature_yaml_as_string)
                # Everything seems in order, spin up an instance of the feature class for future use.
                feature = feature_class(self, yaml_parsed)
                features_to_run.append(feature)
                # Log that this feature is enabled, configured, and validated. For cross-feature access.
                self.features[str(feature_name)] = feature
            elif (
                feature_name != "meta"
            ):  # meta is reserved for asfyaml.py, all else needs a feature or it should break.
                raise KeyError(f"No such .asf.yaml feature: {feature_name}")
        # If validate_only, exit now
        if validate_only:
            return

        # If everything validated okay, we will sort the features by priority and then run them
        for feature in sorted(features_to_run, key=lambda x: x.priority):
            if DEBUG:
                print(f"Running feature: {feature.name}")
            try:
                feature.run()
            except strictyaml.YAMLValidationError as e:
                raise ASFYAMLException(
                    repository=self.repository, branch=self.branch, feature=feature.name, error_message=str(e)
                )
            except Exception as e:
                raise ASFYAMLException(
                    repository=self.repository, branch=self.branch, feature=feature.name, error_message=str(e)
                )


class ClassProperty(object):
    """Simple proxy class for base class objects"""

    def __init__(self, fget):
        self.fget = fget

    def __get__(self, parent_self, parent_cls):
        return self.fget(parent_cls)


class ASFYamlFeature:
    """The base .asf.yaml feature class.

    Example::

        class ASFTestFeature(ASFYamlFeature, name="test", priority=4):
             def run(self):  # run() is the function that gets called once all YAML is validated for all features.
                 pass

    For information on how to create your own feature sub-class, see :func:`asfyaml.ASFYamlFeature.__init_subclass__`
    """

    features = []
    """: list: List for tracking all ASFYamlFeature sub-classes we come across in any environment.
    
        Example use::
        
            class ASFTestFeature(ASFYamlFeature, name="test", priority=4):
                def run(self):
                    for feature in ASFYamlFeature.features:
                        print(feature.name, feature.env)  # prints all discovered features and their environments

        :meta hide-value:
    """

    def __init__(self, parent: ASFYamlInstance, yaml: strictyaml.YAML):
        #: dict: The YAML configuration for this feature, in raw format.
        self.yaml_raw = yaml.data

        #: easydict.EasyDict: The YAML, but in `EasyDict` format.
        self.yaml = easydict.EasyDict(yaml.data)

        #: ASFYamlInstance: This is the parent .asf.yaml instance class. Useful for accessing other features and their data.
        self.instance = parent

        #: repository.Repository: The repository we're working on, and its push info.
        self.repository = parent.repository

        #: repository.Committer: The committer (userid+email) that pushed this commit.
        self.committer = parent.committer

    def __init_subclass__(cls, name: str, env: str = "production", priority: int = DEFAULT_PRIORITY, **kwargs):
        """Instantiates a new sub-class of ASFYamlFeature. The :attr:`name` argument should be the
        top dict keyword for this feature in .asf.yaml, for instance :kbd:`github` or :kbd:`pelican`.
        The :attr:`env` variable can be used to denote which environment this .asf.yaml feature will
        be available in. The default environment is :kbd:`production`, but this can be any name.
        If a priority other than the default (5) is set, the feature will be run based on
        that priority level (0 is highest, 10 lowest)m otherwise it will be run in order of
        appearance in the YAML with the rest of the default priority features.

        Example sub-class definition::

            # Create a new feature that runs after most other features (priority 9)
            class ASFTestFeature(ASFYamlFeature, name="test", priority=9):
                schema = ... # If you want to supply a YAML schema, you can do so here. Otherwise, leave it out.
                def run(self):  # This is where your magic happens
                    pass

        """
        cls.name = name
        cls.env = env
        cls.features.append(cls)
        cls.priority = priority
        super().__init_subclass__(**kwargs)

    def noop(self, directivename):
        """Helper condition that determines whether to apply changes or not. If "no-op" mode is set, this returns true,
        and prints out "[feature::directivename] Not applying changes, noop mode active.

        Example use::

            def run(self):
                if not self.noop("foodirective"):
                    do_thing()

        When production mode is enabled, this would run do_thing(). When testing is enabled, this will
        print out something like `[github::foodirective] Not applying changes, noop mode active.` instead of
        running do_thing().
        """
        if "noop" in self.instance.environments_enabled:
            print(f"[{self.name}::{directivename}] Not applying changes, noop mode active.")
            return True
        return False


# Import all the feature classes. TODO: move this import elsewhere.
from asfyaml.feature import *
