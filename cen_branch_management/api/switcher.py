import frappe


def initialize_session_branch(login_manager):
    # Every login starts unfiltered on "All Branches". Users switch explicitly
    # from there; we no longer try to auto-restore/auto-pick a branch at login,
    # since that relied on frappe.boot.user.defaults being refreshed before any
    # list/form JS ran, which is not guaranteed on the very first page load.
    clear_branch_context()


@frappe.whitelist()
def get_user_branches():
    user_branches = frappe.get_all(
        "Branch User",
        filters={"user": frappe.session.user},
        pluck="parent"
    )

    branch_names = list(user_branches)
    branch_names.insert(0, "All Branches")

    active_branch = frappe.defaults.get_user_default("branch") or "All Branches"

    grouped_branches = {}

    physical_branches = [b for b in branch_names if b != "All Branches"]
    if physical_branches:
        # ignore_permissions: this list is gated by Branch User membership above,
        # not by the "Branch" User Permission created by sync_branch_permissions.
        # Without this, a user assigned to two branches would only see whichever
        # branch their (possibly out-of-date/partially-synced) User Permission
        # happens to restrict them to, silently dropping the other from the menu.
        branch_docs = frappe.get_all(
            "Branch",
            filters={"name": ["in", physical_branches]},
            fields=["name", "custom_cen_default_company"],
            ignore_permissions=True
        )
        for b in branch_docs:
            company = b.custom_cen_default_company or "Unassigned Company"
            if company not in grouped_branches:
                grouped_branches[company] = []
            grouped_branches[company].append(b.name)

    return {
        "branches": branch_names,
        "grouped_branches": grouped_branches,
        "active_branch": active_branch
    }


@frappe.whitelist()
def set_active_branch(branch_name):
    if branch_name == "All Branches":
        clear_branch_context()
    else:
        if not frappe.db.exists("Branch User", {"user": frappe.session.user, "parent": branch_name}):
            frappe.throw("You do not have permission to access this branch.")

        apply_branch_context(branch_name)

    frappe.clear_cache(user=frappe.session.user)
    return {"status": "success"}


def clear_branch_context():
    frappe.defaults.clear_default("branch")
    frappe.defaults.clear_default("custom_cen_branch")
    frappe.defaults.clear_default("cen_branch_company")
    frappe.defaults.clear_default("cen_branch_warehouse")
    frappe.defaults.clear_default("cen_branch_warehouses")
    frappe.defaults.clear_default("cen_branch_cost_center")
    frappe.defaults.clear_default("cen_branch_cost_centers")
    frappe.defaults.clear_default("cen_branch_selling_price_lists")
    frappe.defaults.clear_default("cen_branch_buying_price_lists")
    frappe.defaults.clear_default("cen_branch_default_selling_price_list")
    frappe.defaults.clear_default("cen_branch_default_buying_price_list")


def apply_branch_context(branch_name):
    branch_doc = frappe.get_doc("Branch", branch_name)

    frappe.defaults.set_user_default("branch", branch_name)
    frappe.defaults.set_user_default("custom_cen_branch", branch_name)

    if branch_doc.custom_cen_default_company:
        frappe.defaults.set_user_default("cen_branch_company", branch_doc.custom_cen_default_company)
    else:
        frappe.defaults.clear_default("cen_branch_company")

    if branch_doc.custom_cen_warehouse_parent:
        frappe.defaults.set_user_default("cen_branch_warehouse", branch_doc.custom_cen_warehouse_parent)
        wh_data = frappe.db.get_value("Warehouse", branch_doc.custom_cen_warehouse_parent, ["lft", "rgt"], as_dict=True)
        if wh_data:
            wh_list = frappe.get_all("Warehouse", filters={"lft": [">=", wh_data.lft], "rgt": ["<=", wh_data.rgt], "is_group": 0}, pluck="name")
            frappe.defaults.set_user_default("cen_branch_warehouses", ",".join(wh_list))
    else:
        frappe.defaults.clear_default("cen_branch_warehouse")
        frappe.defaults.clear_default("cen_branch_warehouses")

    if branch_doc.custom_cen_cost_center_parent:
        frappe.defaults.set_user_default("cen_branch_cost_center", branch_doc.custom_cen_cost_center_parent)
        cc_data = frappe.db.get_value("Cost Center", branch_doc.custom_cen_cost_center_parent, ["lft", "rgt"], as_dict=True)
        if cc_data:
            cc_list = frappe.get_all("Cost Center", filters={"lft": [">=", cc_data.lft], "rgt": ["<=", cc_data.rgt], "is_group": 0}, pluck="name")
            frappe.defaults.set_user_default("cen_branch_cost_centers", ",".join(cc_list))
    else:
        frappe.defaults.clear_default("cen_branch_cost_center")
        frappe.defaults.clear_default("cen_branch_cost_centers")

    selling_price_lists = set()
    for row in branch_doc.get("custom_cen_allowed_selling_price_lists", []):
        if row.price_list:
            selling_price_lists.add(row.price_list)
    if branch_doc.custom_cen_default_selling_price_list:
        selling_price_lists.add(branch_doc.custom_cen_default_selling_price_list)

    if selling_price_lists:
        frappe.defaults.set_user_default("cen_branch_selling_price_lists", ",".join(selling_price_lists))
    else:
        frappe.defaults.clear_default("cen_branch_selling_price_lists")

    # Kept separate from the "allowed" list above: this one drives auto-fill on
    # transaction forms, the allowed list only drives the link-field dropdown filter.
    if branch_doc.custom_cen_default_selling_price_list:
        frappe.defaults.set_user_default("cen_branch_default_selling_price_list", branch_doc.custom_cen_default_selling_price_list)
    else:
        frappe.defaults.clear_default("cen_branch_default_selling_price_list")

    buying_price_lists = set()
    for row in branch_doc.get("custom_cen_allowed_buying_price_lists", []):
        if row.price_list:
            buying_price_lists.add(row.price_list)
    if branch_doc.custom_cen_default_buying_price_list:
        buying_price_lists.add(branch_doc.custom_cen_default_buying_price_list)

    if buying_price_lists:
        frappe.defaults.set_user_default("cen_branch_buying_price_lists", ",".join(buying_price_lists))
    else:
        frappe.defaults.clear_default("cen_branch_buying_price_lists")

    if branch_doc.custom_cen_default_buying_price_list:
        frappe.defaults.set_user_default("cen_branch_default_buying_price_list", branch_doc.custom_cen_default_buying_price_list)
    else:
        frappe.defaults.clear_default("cen_branch_default_buying_price_list")
