import frappe
from frappe import _

# User.custom_cen_default_branch: the branch a user lands on at login. It is
# the only input for that decision (see api/switcher.initialize_session_branch,
# which re-checks it at every login). Everything here just keeps the value sane.
USER_DEFAULT_BRANCH_FIELD = "custom_cen_default_branch"


def is_branch_user(user, branch):
    """Is the user listed in the branch's allowed users?"""
    return bool(
        frappe.db.exists("Branch User", {"parent": branch, "parenttype": "Branch", "user": user})
    )


def validate_user_default_branch(doc, method=None):
    """User validate: a Default Branch must be one the user is assigned to.

    Only checked when the value is being changed: a value that has gone stale
    (the login check ignores it anyway) must not block unrelated edits to the
    user, such as a password change.
    """
    branch = doc.get(USER_DEFAULT_BRANCH_FIELD)
    if not branch or not doc.has_value_changed(USER_DEFAULT_BRANCH_FIELD):
        return

    if not is_branch_user(doc.name, branch):
        frappe.throw(
            _("{0} is not assigned to branch {1}. Add the user under User Access on that branch first, or pick a branch they are assigned to.").format(
                frappe.bold(doc.full_name or doc.name), frappe.bold(branch)
            ),
            title=_("Invalid Default Branch"),
        )


def sync_default_branch_on_branch_update(doc, method=None):
    """Branch on_update, comparing the user rows with the ones before this save:

    - a user taken off the branch loses a Default Branch that pointed here;
    - a user newly marked "Is Default" gets this branch as Default Branch, but
      only if they have none. Acting on the change rather than on the flag
      means an admin who clears the field is not overruled by the next save.

    The User is updated in place: no User validations or hooks run for what is
    a side effect of editing a Branch.
    """
    previous = doc.get_doc_before_save()
    old_rows = (previous.get("custom_cen_branch_users") or []) if previous else []
    new_rows = doc.get("custom_cen_branch_users") or []

    old_users = {row.user for row in old_rows if row.user}
    new_users = {row.user for row in new_rows if row.user}
    for user in old_users - new_users:
        _clear_default_branch(user, doc.name)

    old_flagged = {row.user for row in old_rows if row.user and row.is_default}
    new_flagged = {row.user for row in new_rows if row.user and row.is_default}
    for user in new_flagged - old_flagged:
        _set_default_branch_if_empty(user, doc.name)


def clear_default_branch_on_branch_trash(doc, method=None):
    """Branch on_trash: nobody can land on a branch that is going away (and the
    link from User would otherwise block the deletion)."""
    for user in frappe.get_all("User", filters={USER_DEFAULT_BRANCH_FIELD: doc.name}, pluck="name"):
        _clear_default_branch(user, doc.name)


def _clear_default_branch(user, branch):
    if frappe.db.get_value("User", user, USER_DEFAULT_BRANCH_FIELD) == branch:
        frappe.db.set_value("User", user, USER_DEFAULT_BRANCH_FIELD, None, update_modified=False)


def _set_default_branch_if_empty(user, branch):
    details = frappe.db.get_value("User", user, ["enabled", USER_DEFAULT_BRANCH_FIELD], as_dict=True)
    if not details or not details.enabled or details.get(USER_DEFAULT_BRANCH_FIELD):
        return

    frappe.db.set_value("User", user, USER_DEFAULT_BRANCH_FIELD, branch, update_modified=False)
