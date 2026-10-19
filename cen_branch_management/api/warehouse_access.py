import frappe

# Branch.custom_cen_user_warehouses (Branch User Warehouse rows: user, warehouse)
# narrows what a branch user may use. A user with no rows there gets every
# warehouse under the branch's Warehouse Parent, which is how every branch
# worked before this table existed.
#
# This module is the one answer to "which warehouses may this user use on this
# branch": the permission sync, the branch switcher and cen_crm_addons' mobile
# profile all read it, so they cannot disagree.
USER_WAREHOUSES_FIELD = "custom_cen_user_warehouses"
SUMMARY_LENGTH = 140


def get_restricted_warehouses(branch, user):
    """The warehouses the user is narrowed to on this branch, or [] if they are
    not restricted. Group warehouses stand for everything under them."""
    branch = _get_branch(branch)
    return sorted({row.warehouse for row in branch.get(USER_WAREHOUSES_FIELD) or [] if row.user == user and row.warehouse})


def get_user_warehouse_roots(branch, user):
    """What the user is granted on this branch, as stored: their restricted
    warehouses, else the Warehouse Parent, else nothing."""
    branch = _get_branch(branch)
    restricted = get_restricted_warehouses(branch, user)
    if restricted:
        return restricted

    parent = branch.get("custom_cen_warehouse_parent")
    return [parent] if parent else []


def get_user_branch_warehouses(branch, user):
    """The non-group warehouses the user may use on this branch, sorted by name.
    Empty when the branch has no Warehouse Parent (nothing to restrict to)."""
    return get_leaf_warehouses(get_user_warehouse_roots(branch, user))


def get_user_default_warehouse(branch, user, warehouses=None):
    """The branch's Default Warehouse, unless the user is restricted away from
    it -- then the first warehouse (by name) the user is allowed."""
    branch = _get_branch(branch)
    default = branch.get("custom_cen_default_warehouse") or None
    if not get_restricted_warehouses(branch, user):
        return default

    if warehouses is None:
        warehouses = get_user_branch_warehouses(branch, user)
    if default in warehouses:
        return default
    return warehouses[0] if warehouses else None


def get_leaf_warehouses(roots):
    """Non-group warehouses at or under any of the given warehouses. A
    non-group root counts as itself."""
    leaves = set()
    for root in roots:
        bounds = frappe.db.get_value("Warehouse", root, ["lft", "rgt"], as_dict=True)
        if not bounds:
            continue
        leaves.update(
            frappe.get_all(
                "Warehouse",
                filters={"lft": [">=", bounds.lft], "rgt": ["<=", bounds.rgt], "is_group": 0},
                pluck="name",
            )
        )
    return sorted(leaves)


def get_warehouse_access_summary(branch, user):
    """The text shown in the Warehouse Access column of Assigned Branch Users."""
    restricted = get_restricted_warehouses(branch, user)
    if not restricted:
        return "All warehouses"

    text = "Only: " + ", ".join(restricted)
    return text if len(text) <= SUMMARY_LENGTH else text[: SUMMARY_LENGTH - 3] + "..."


def _get_branch(branch):
    return frappe.get_doc("Branch", branch) if isinstance(branch, str) else branch
