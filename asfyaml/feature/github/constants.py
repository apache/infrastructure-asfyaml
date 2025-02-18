
# Valid variables that can be used in custom github subject formatting
# Corresponds to what's available in https://github.com/apache/infrastructure-github-event-notifier
# N.B. Must agree with the user documentation at:
# https://cwiki.apache.org/confluence/display/INFRA/Git+-+.asf.yaml+features#Git.asf.yamlfeatures-Supportedtemplatevariables
VALID_GITHUB_SUBJECT_VARIABLES = (
    "repository",
    "user",
    "pr_id",
    "issue_id",
    "link",
    "title",
    "category",
)

# GitHub events for which custom subjects are supported (catchall is a fallback for any action without a template)
# Corresponds to templates available at https://github.com/apache/infrastructure-github-event-notifier/tree/main/templates
VALID_GITHUB_ACTIONS = (
    "close_issue",
    "close_pr",
    "comment_issue",
    "comment_pr",
    "diffcomment",
    "merge_pr",
    "new_issue",
    "new_pr",
    "catchall",
    "new_discussion",
    "edit_discussion",
    "close_discussion",
    "close_discussion_with_comment",
    "reopen_discussion",
    "new_comment_discussion",
    "edit_comment_discussion",
    "delete_comment_discussion",
    "catchall_discussions",
)

# Maximum number of non-committer collaborators per repository on GitHub.
# The only way to increase the limit is by talking to vp infra.
MAX_COLLABORATORS = 10
