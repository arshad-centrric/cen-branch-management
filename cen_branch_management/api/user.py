import frappe
from frappe.desk.search import search_widget


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def default_branch_query(doctype, txt, searchfield, start, page_len, filters):
    """Link query for User > Default Branch: the branches that user is assigned to.

    Read-only. The caller must be able to read that User, and the result goes
    through the normal Branch permission checks, so it only ever narrows what
    the caller could already see.
    """
    user = filters.get("user")
    if not user or not frappe.db.exists("User", user) or not frappe.has_permission("User", "read", user):
        return []

    branches = frappe.get_all("Branch User", filters={"user": user, "parenttype": "Branch"}, pluck="parent")
    if not branches:
        return []

    return search_widget(
        "Branch",
        txt,
        filters=[["Branch", "name", "in", branches]],
        searchfield=searchfield,
        start=start,
        page_length=page_len,
    )
