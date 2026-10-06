import frappe
from frappe import _

def validate_default_branch(doc, method):
    if not doc.get("custom_cen_default_company"):
        return
        
    default_users = [row.user for row in doc.get("custom_cen_branch_users") if row.is_default]
    
    if not default_users:
        return
        
    other_branches = frappe.get_all("Branch", 
        filters={"custom_cen_default_company": doc.custom_cen_default_company, "name": ["!=", doc.name]}, 
        pluck="name"
    )
    
    if other_branches:
        for user in default_users:
            duplicate = frappe.db.exists("Branch User", {
                "parent": ["in", other_branches],
                "user": user,
                "is_default": 1
            })
            
            if duplicate:
                other_branch = frappe.db.get_value("Branch User", duplicate, "parent")
                full_name = frappe.db.get_value("User", user, "full_name") or user
                frappe.throw(_(f"User {full_name} is already set as the default user for branch {other_branch} under company {doc.custom_cen_default_company}."))


def validate_default_warehouse_and_cost_center(doc, method=None):
    _validate_branch_default(
        doc,
        doctype="Warehouse",
        default_field="custom_cen_default_warehouse",
        parent_field="custom_cen_warehouse_parent",
        default_label=_("Default Warehouse"),
        parent_label=_("Warehouse Parent"),
    )
    _validate_branch_default(
        doc,
        doctype="Cost Center",
        default_field="custom_cen_default_cost_center",
        parent_field="custom_cen_cost_center_parent",
        default_label=_("Default Cost Center"),
        parent_label=_("Cost Center Parent"),
    )


def _validate_branch_default(doc, doctype, default_field, parent_field, default_label, parent_label):
    """A branch default must be a usable leaf of the branch's own tree: not a
    group, in the branch's company, and (when a parent is set) inside it. The
    parent is optional, so with no parent only the first two rules apply.
    """
    default = doc.get(default_field)
    if not default:
        return

    details = frappe.db.get_value(doctype, default, ["is_group", "company", "lft", "rgt"], as_dict=True)
    if not details:
        # Not a real record: leave it to the standard link validation, which
        # runs after this hook and reports it properly.
        return

    if details.is_group:
        frappe.throw(
            _("{0} {1} is a group. Please select a non-group {2}.").format(
                default_label, frappe.bold(default), _(doctype)
            ),
            title=_("Invalid {0}").format(default_label),
        )

    company = doc.get("custom_cen_default_company")
    if not company:
        frappe.throw(
            _("Please set the Company on this branch before choosing a {0}.").format(default_label),
            title=_("Company Required"),
        )

    if details.company != company:
        frappe.throw(
            _("{0} {1} belongs to company {2}, but this branch is under company {3}.").format(
                default_label, frappe.bold(default), frappe.bold(details.company), frappe.bold(company)
            ),
            title=_("Invalid {0}").format(default_label),
        )

    parent = doc.get(parent_field)
    if not parent:
        return

    parent_details = frappe.db.get_value(doctype, parent, ["lft", "rgt"], as_dict=True)
    if parent_details and not (parent_details.lft <= details.lft and details.rgt <= parent_details.rgt):
        frappe.throw(
            _("{0} {1} is not under the {2} {3}. Please select one that is inside it.").format(
                default_label, frappe.bold(default), parent_label, frappe.bold(parent)
            ),
            title=_("Invalid {0}").format(default_label),
        )


def validate_allowed_item_groups(doc, method=None):
    seen = set()
    for row in doc.get("custom_cen_allowed_item_groups") or []:
        if not row.item_group:
            continue

        if row.item_group in seen:
            frappe.throw(
                _("Row #{0}: Item Group {1} is already in Allowed Item Groups. Please remove the duplicate.").format(
                    row.idx, frappe.bold(row.item_group)
                ),
                title=_("Duplicate Item Group"),
            )
        seen.add(row.item_group)
