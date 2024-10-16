# Testing new features

Any git repository within the ASF ecosystem can be used for testing new or upcoming features.
Enabling a feature branch can be done via the `meta` feature:

~~~yaml
meta:
    environment: preview/gh_discussions
~~~

The above mock example could be used for testing a new GitHub Discussions feature in 
.asf.yaml that exists in a certain preview environment of the .asf.yaml parser.

All testing environments specifically enabled through your repository's .asf.yaml
configuration are merged with the production environment before running, 
allowing you to make full use of existing production features as well as the preview 
features. In the case of a feature existing in both environments, the feature in the 
preview environment will take precedence.

When a new feature is available, we will be listing it on [this page](features/readme.md). Once a feature
has been merged into the production environment, any old references will stop yielding a 
different feature from production.
