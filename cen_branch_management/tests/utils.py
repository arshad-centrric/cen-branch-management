"""Record builders shared by the branch tests.

Everything is created inside the test transaction (rolled back when the test
class finishes), under whichever companies the site already has: setting up a
whole ERPNext company per test run would be slow and is not what is under test.
"""

import frappe

_counter = 0


def unique(prefix):
    global _counter
    _counter += 1
    return f"_Test CBM {prefix} {_counter}"


def get_companies():
    return frappe.get_all("Company", pluck="name", order_by="creation", limit=2)


def make_warehouse(company, is_group=0, parent=None):
    doc = frappe.get_doc({
        "doctype": "Warehouse",
        "warehouse_name": unique("WH"),
        "company": company,
        "is_group": is_group,
        "parent_warehouse": parent,
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def make_cost_center(company, is_group=0, parent=None):
    if not parent:
        parent = frappe.db.get_value(
            "Cost Center", {"company": company, "is_group": 1, "parent_cost_center": ("is", "not set")}
        )

    doc = frappe.get_doc({
        "doctype": "Cost Center",
        "cost_center_name": unique("CC"),
        "company": company,
        "is_group": is_group,
        "parent_cost_center": parent,
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def get_root_item_group():
    return frappe.db.get_value("Item Group", {"parent_item_group": ("is", "not set")})


def make_item_group(is_group=0, parent=None):
    doc = frappe.get_doc({
        "doctype": "Item Group",
        "item_group_name": unique("IG"),
        "is_group": is_group,
        "parent_item_group": parent or get_root_item_group(),
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def make_user():
    global _counter
    _counter += 1
    doc = frappe.get_doc({
        "doctype": "User",
        "email": f"cbm_test_{_counter}@example.com",
        "first_name": f"CBM Test {_counter}",
        "send_welcome_email": 0,
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def make_branch(company=None, users=None, item_groups=None, default_users=None, **fields):
    """`default_users` are added to the branch's users with "Is Default" ticked."""
    user_rows = [{"user": user} for user in users or []]
    user_rows += [{"user": user, "is_default": 1} for user in default_users or []]

    doc = frappe.get_doc({
        "doctype": "Branch",
        "branch": unique("Branch"),
        "custom_cen_default_company": company,
        "custom_cen_branch_users": user_rows,
        "custom_cen_allowed_item_groups": [{"item_group": group} for group in item_groups or []],
        **fields,
    })
    doc.insert(ignore_permissions=True)
    return doc


def managed_permissions(user, allow):
    """for_value -> list of source branches, for a user's branch-managed permissions."""
    out = {}
    for name, for_value in frappe.get_all(
        "User Permission",
        filters={"user": user, "allow": allow, "custom_cen_from_branch_setup": 1},
        fields=["name", "for_value"],
        as_list=True,
    ):
        out[for_value] = sorted(
            frappe.get_all(
                "User Permission Source Branch",
                filters={"parent": name, "parenttype": "User Permission"},
                pluck="branch",
            )
        )
    return out


def make_address(company=None, branch=None):
    """An address, linked to `company` when given (which makes it a company address)."""
    doc = frappe.get_doc({
        "doctype": "Address",
        "address_title": unique("Address"),
        "address_type": "Office",
        "address_line1": "1 Test Street",
        "city": "Test City",
        "country": frappe.db.get_value("Company", company or get_companies()[0], "country"),
        "state": frappe.db.get_value("Address", {"state": ("is", "set")}, "state"),
        "pincode": frappe.db.get_value("Address", {"pincode": ("is", "set")}, "pincode"),
        "links": [{"link_doctype": "Company", "link_name": company}] if company else [],
        "custom_cen_address_branch": branch,
    })
    doc.insert(ignore_permissions=True)
    return doc.name
