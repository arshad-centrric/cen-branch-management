import frappe

# Everything a branch grants its users, as User Permission "allow" doctypes.
# A managed permission of any other type that still points at a branch (e.g.
# Cost Center, which branch setup created in the past and no longer does) is
# treated as no longer granted by that branch.
MANAGED_PERMISSION_TYPES = ("Branch", "Company", "Warehouse", "Price List", "Item Group")


def sync_permissions_on_update(doc, method):
    """Branch doc_event (on_update): keep this branch's User Permissions in sync
    automatically on every save, instead of relying on someone remembering to
    click "Sync User Permissions" by hand. A user added to a second branch that
    hasn't been (re-)synced yet would otherwise end up with a stale "Branch"
    User Permission pointing only at their first branch, which silently hides
    the second branch from their switcher (frappe.get_all permission-filters it
    out) even though they are a valid member of it.

    Assigned users and allowed item groups are child tables of Branch, so any
    change to them arrives here as a Branch save.
    """
    if _sync_is_suspended():
        return

    _sync_branch_permissions(doc)


def sync_permissions_on_user_update(doc, method=None):
    """User doc_event (on_update): a disabled user loses what their branches
    granted, and gets it back when re-enabled. Nothing on the Branch changes in
    either case, so this is the only place that can react to it.
    """
    if _sync_is_suspended() or not doc.has_value_changed("enabled"):
        return

    branch_names = set(frappe.get_all("Branch User", filters={"user": doc.name, "parenttype": "Branch"}, pluck="parent"))
    for branch_name in branch_names:
        _sync_branch_permissions(frappe.get_doc("Branch", branch_name))


@frappe.whitelist(methods=["POST"])
def sync_branch_permissions(branch_name):
    """Manual re-sync from the Branch form. The sync itself writes User
    Permissions with ignore_permissions, so the caller has to be someone who
    could trigger the very same sync by saving this branch.
    """
    branch = frappe.get_doc("Branch", branch_name)
    branch.check_permission("write")
    _sync_branch_permissions(branch)


def _sync_is_suspended():
    return bool(
        frappe.flags.in_install or frappe.flags.in_patch or frappe.flags.in_migrate or frappe.flags.in_import
    )


def _sync_branch_permissions(branch):
    active_users = _get_active_branch_users(branch)
    granted = _get_granted_values(branch)

    # 1. Ghost Cleanup: only permissions that this branch is a source of. One
    # that another branch also grants just loses this branch's reference and
    # lives on until no branch references it.
    for perm_name in _get_permissions_sourced_from(branch.name):
        perm_doc = frappe.get_doc("User Permission", perm_name)

        if not _is_still_granted(perm_doc, active_users, granted):
            _remove_branch_source(perm_doc, branch.name)

    # 2. Active User Sync
    for user in active_users:
        for allow, values in granted.items():
            for for_value in values:
                _grant(user, allow, for_value, branch.name)


def _get_active_branch_users(branch):
    users = {row.user for row in branch.get("custom_cen_branch_users") or [] if row.user}
    if not users:
        return set()

    return set(frappe.get_all("User", filters={"name": ["in", list(users)], "enabled": 1}, pluck="name"))


def _get_granted_values(branch):
    """allow doctype -> the values this branch permits its users.

    Item Group: only the groups listed on the branch. A User Permission on a
    tree doctype already covers the node's descendants, so child groups are not
    expanded here. The root ("All Item Groups") is deliberately never added: it
    is not needed (the tree view does not apply user permissions, and items are
    created against the allowed groups themselves), and since it covers every
    group it would undo the restriction altogether.
    """
    price_lists = {
        branch.get("custom_cen_default_selling_price_list"),
        branch.get("custom_cen_default_buying_price_list"),
    }
    for fieldname in ("custom_cen_allowed_selling_price_lists", "custom_cen_allowed_buying_price_lists"):
        price_lists.update(row.price_list for row in branch.get(fieldname) or [])

    granted = {
        "Branch": {branch.name},
        "Company": {branch.get("custom_cen_default_company")},
        "Warehouse": {branch.get("custom_cen_warehouse_parent")},
        "Price List": price_lists,
        "Item Group": {row.item_group for row in branch.get("custom_cen_allowed_item_groups") or []},
    }

    return {allow: {value for value in values if value} for allow, values in granted.items()}


def _get_permissions_sourced_from(branch_name):
    """Managed User Permissions that list this branch as a source.

    Resolved against the User Permission table itself rather than trusting the
    source rows alone: core's "Clear User Permissions" deletes permissions with
    a plain SQL delete, which leaves their source rows behind.
    """
    referenced = set(
        frappe.get_all(
            "User Permission Source Branch",
            filters={"branch": branch_name, "parenttype": "User Permission"},
            pluck="parent",
        )
    )
    if not referenced:
        return set()

    return set(
        frappe.get_all(
            "User Permission",
            filters={"name": ["in", list(referenced)], "custom_cen_from_branch_setup": 1},
            pluck="name",
        )
    )


def _is_still_granted(perm_doc, active_users, granted):
    if perm_doc.user not in active_users:
        return False

    if perm_doc.allow not in MANAGED_PERMISSION_TYPES:
        return False

    # A group taken off the branch's Allowed Item Groups stops being granted.
    if perm_doc.allow == "Item Group":
        return perm_doc.for_value in granted["Item Group"]

    return True


def _remove_branch_source(perm_doc, branch_name):
    for row in [row for row in perm_doc.get("custom_cen_source_branch") if row.branch == branch_name]:
        perm_doc.remove(row)

    if perm_doc.get("custom_cen_source_branch"):
        perm_doc.save(ignore_permissions=True)
    else:
        frappe.delete_doc("User Permission", perm_doc.name, ignore_permissions=True)


def _grant(user, allow, for_value, branch_name):
    existing_name = frappe.db.exists("User Permission", {
        "user": user,
        "allow": allow,
        "for_value": for_value
    })

    if existing_name:
        perm_doc = frappe.get_doc("User Permission", existing_name)
        has_branch = any(row.branch == branch_name for row in perm_doc.get("custom_cen_source_branch"))

        if not has_branch:
            perm_doc.append("custom_cen_source_branch", {"branch": branch_name})

        if not perm_doc.custom_cen_from_branch_setup:
            perm_doc.custom_cen_from_branch_setup = 1

        perm_doc.save(ignore_permissions=True)
    else:
        doc = frappe.new_doc("User Permission")
        doc.user = user
        doc.allow = allow
        doc.for_value = for_value
        doc.apply_to_all_doctypes = 1
        doc.custom_cen_from_branch_setup = 1
        doc.append("custom_cen_source_branch", {"branch": branch_name})
        doc.insert(ignore_permissions=True)
