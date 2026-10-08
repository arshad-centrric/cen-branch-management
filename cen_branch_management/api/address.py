import frappe
from frappe.desk.search import search_widget

from cen_branch_management.overrides.branch_address import ADDRESS_BRANCH_FIELD


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def branch_address_query(doctype, txt, searchfield, start, page_len, filters):
    """Link query for Branch > Branch Address: addresses of the branch's company
    that are free or already this branch's.

    Frappe's own address_query only takes equality filters, which cannot say
    "branch is empty OR this branch". Read-only; both lookups go through the
    normal permission checks, so a user only sees addresses they can read.
    """
    company = filters.get("company")
    if not company:
        return []

    candidates = frappe.get_list(
        "Address",
        filters=[
            ["Dynamic Link", "link_doctype", "=", "Company"],
            ["Dynamic Link", "link_name", "=", company],
            ["Dynamic Link", "parenttype", "=", "Address"],
        ],
        or_filters=[
            ["Address", ADDRESS_BRANCH_FIELD, "is", "not set"],
            ["Address", ADDRESS_BRANCH_FIELD, "=", filters.get("branch") or ""],
        ],
        pluck="name",
        limit_page_length=0,
    )
    if not candidates:
        return []

    return search_widget(
        "Address",
        txt,
        filters=[["Address", "name", "in", candidates]],
        searchfield=searchfield,
        start=start,
        page_length=page_len,
    )
