# The ASFYamlFeature class

The base class for any .asf.yaml feature plugin is the `ASFYamlFeature` class.
For each new feature, you should generate a subclass of this, optionally specifying 
the [YAML schema](#the-yaml-schema), the [environment](#feature-environments) name, 
and/or [priority](#priority-scheduling) you wish to attach to this feature.

Features are located in the [feature/](../feature/) directory and needs to be manually 
enabled in [feature/__init__.py](../feature/__init__.py) prior to using.

## Example feature class
~~~python3
from asfyaml import ASFYamlFeature
import strictyaml


class ASFTestFeature(ASFYamlFeature, name="test", env="production", priority=4):
    schema = strictyaml.Map(
        {
            "foo": strictyaml.Str(),
            strictyaml.Optional("enable", default=False): strictyaml.Bool(),
        },
    )

    def run(self):
        # Do some things with the 'foo' directive in our section...
        if not do_things(self.yaml.foo):
            # Oh no, something bad! We better relay this back to .asf.yaml
            # This will notify the git client as well as send an error report to 
            # private@project.apache.org.
            raise Exception("Something bad happened")
~~~

This would create a new feature called `test` in .asf.yaml that is accessible to all repositories, 
with a required directive, `foo` which MUST be set, as well as an optional boolean value, `enable`, 
which defaults to `False`. It would also run at [priority](#priority-scheduling) `4`, meaning 
slightly before the default placement of features.

A valid .asf.yaml configuration section for this feature could look like this:

~~~yaml
test:
    foo: pony
    enable: true
~~~

## The YAML Schema

YAML schemas are validated using [StrictYAML](https://hitchdev.com/strictyaml/)
For detailed documentation on how to construct a schema, see the 
[StrictYAML Users Guide](https://hitchdev.com/strictyaml/using/)

A feature can associate itself with a schema by setting the `schema` variable inside the 
sub-class:

~~~python3
from asfyaml import ASFYamlFeature
import strictyaml

class ASFSchemaTestFeature(ASFYamlFeature, name="schematest"):
    schema = strictyaml.Map(
        {
            "email_address": strictyaml.Str(),
            "howmany": strictyaml.Int(),
            strictyaml.Optional("enable_feature", default=False): strictyaml.Bool(),
        },
    )

    def run(self):  # Only ever runs if the YAML is valid
        pass
~~~

The above schema example would require `email_address` to be set to a string value, 
`howmany` to be set to an integer value, and optionally `enable_feature` can be set 
to True or False, with False being the default if not set. If the YAML in a 
repository's .asf.yaml section for this feature does not conform to the schema, an 
error will be thrown and the .asf.yaml processing will be stopped.

All features with schemas are validated before any feature is actually run, so having a 
schema properly defined can help spot typical configuration errors early on.


## Priority Scheduling

Features are, by default, scheduled with a priority level of `5`. This means they will be run in 
order of appearance in the YAML file. If a feature needs to run before or after other features, 
you can specify a priority, where 0 is the greatest priority and 10 is the least priority.
A feature with priority of 1 will be run before the default group, whereas a feature with a 
priority of `9` would run after the default group.

TO-DO: Allow priority relative to other features.

## Feature Environments

A Feature can be enabled for specific environments, meaning only repositories set (and allowed) 
to use that environment will be able to run it. This can be used for protected features, as 
well as for feature previews that should only be enabled for one or more specific repositories, 
either during the initial testing, or because the feature is tailored to a specific project.

The default environment is `production`, which is available to all repositories.

A feature environment branch is declared in the subclass definition:
~~~python3
class ASFTestFeature(ASFYamlFeature, name="test", env="beta"):
    pass
~~~

If a feature of the same type exists in the `production` environment, this environment will 
override it for any repository that has `beta` set as their [.asf.yaml environment](testing.md):

~~~yaml
meta:  # The `meta` section manages things like which environment to use for .asf.yaml
  environment: beta
test:
   foo: bar
~~~

Environments can be set for any branch of a repository, although some features will only work on 
certain branches (such as the default branch or if a specific `whoami` is set).

You can also add multiple environments in order to merge several features:
~~~yaml
meta:  # The `meta` section manages things like which environment to use for .asf.yaml
  environments: # Note, this is a list instead of a single string
    - foobar
    - otherfoo
    - quietmode
~~~

## Accessing Other Features
Any feature can perform lookups on other enabled features in the .asf.yaml instance by 
iterating through the parent `ASFYamlInstance` object:

~~~python3
def run(self):
    # Make sure there is a valid target set for GitHub Discussions, through the notifications feature.
    if not (
            # Notifications must be configured
            self.instance.features.notifications
            and "discussions" in self.instance.features.notifications.valid_targets  # GH Discussions must have a validated mailing list destination.
    ):
        raise Exception("You need to set up a 'discussions' notification target before enabling GitHub Discussions")
    pass
~~~
