import frappe


def sync_permissions_on_update(doc, method):
    """Branch doc_event (on_update): keep this branch's User Permissions in sync
    automatically on every save, instead of relying on someone remembering to
    click "Sync User Permissions" by hand. A user added to a second branch that
    hasn't been (re-)synced yet would otherwise end up with a stale "Branch"
    User Permission pointing only at their first branch, which silently hides
    the second branch from their switcher (frappe.get_all permission-filters it
    out) even though they are a valid member of it.
    """
    if frappe.flags.in_install or frappe.flags.in_patch or frappe.flags.in_migrate or frappe.flags.in_import:
        return

    _sync_branch_permissions(doc)


@frappe.whitelist()
def sync_branch_permissions(branch_name):
    branch = frappe.get_doc("Branch", branch_name)
    _sync_branch_permissions(branch)


def _sync_branch_permissions(branch):
    active_users = list(set([row.user for row in branch.get("custom_cen_branch_users") if row.user]))

    # 1. Ghost User Cleanup
    managed_perms = frappe.get_all("User Permission", filters={"custom_cen_from_branch_setup": 1}, pluck="name")
    for perm_name in managed_perms:
        perm_doc = frappe.get_doc("User Permission", perm_name)

        # Cost Center used to be synced here too, but mapping it via User Permission
        # caused permission/view issues elsewhere, so branch setup stopped creating
        # these. This purges any leftover ones from before that change, wherever
        # they are found (not scoped to this branch) -- there should be none left
        # going forward since create_perm() below no longer creates this type.
        if perm_doc.allow == "Cost Center":
            frappe.delete_doc("User Permission", perm_name, ignore_permissions=True)
            continue

        has_branch = False
        row_to_remove = None

        for row in perm_doc.get("custom_cen_source_branch"):
            if row.branch == branch.name:
                has_branch = True
                row_to_remove = row
                break

        if has_branch and perm_doc.user not in active_users:
            perm_doc.remove(row_to_remove)
            if len(perm_doc.get("custom_cen_source_branch")) == 0:
                perm_doc.delete()
            else:
                perm_doc.save(ignore_permissions=True)

    # 2. Active User Sync
    for user in active_users:
        def create_perm(allow, for_value):
            if not for_value:
                return

            existing_name = frappe.db.exists("User Permission", {
                "user": user,
                "allow": allow,
                "for_value": for_value
            })

            if existing_name:
                perm_doc = frappe.get_doc("User Permission", existing_name)
                has_branch = any(row.branch == branch.name for row in perm_doc.get("custom_cen_source_branch"))

                if not has_branch:
                    perm_doc.append("custom_cen_source_branch", {"branch": branch.name})

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
                doc.append("custom_cen_source_branch", {"branch": branch.name})
                doc.insert(ignore_permissions=True)

        create_perm("Branch", branch.name)
        create_perm("Company", branch.custom_cen_default_company)
        create_perm("Warehouse", branch.custom_cen_warehouse_parent)

        price_lists = set()
        if branch.custom_cen_default_selling_price_list:
            price_lists.add(branch.custom_cen_default_selling_price_list)
        if branch.custom_cen_default_buying_price_list:
            price_lists.add(branch.custom_cen_default_buying_price_list)

        for row in branch.get("custom_cen_allowed_selling_price_lists", []):
            if row.price_list:
                price_lists.add(row.price_list)

        for row in branch.get("custom_cen_allowed_buying_price_lists", []):
            if row.price_list:
                price_lists.add(row.price_list)

        for pl in price_lists:
            create_perm("Price List", pl)
