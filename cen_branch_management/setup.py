import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def add_custom_fields():
    # custom_cen_config_col: the Details tab is now laid out as "Warehouse" and
    # "Cost Center" sections, so the old lone column break is obsolete.
    for fieldname in ["custom_cen_default_price_list", "custom_cen_config_section", "custom_cen_config_col"]:
        if frappe.db.exists("Custom Field", f"Branch-{fieldname}"):
            frappe.delete_doc("Custom Field", f"Branch-{fieldname}", force=True)

    # The "Configuration" tab (fieldname kept as custom_cen_pricing_section so
    # nothing referencing it breaks) started life as a Section Break. A custom
    # field's type can't be changed in place, so drop it only in that case; an
    # existing Tab Break is simply updated (label etc.) by create_custom_fields.
    pricing_fieldtype = frappe.db.get_value("Custom Field", "Branch-custom_cen_pricing_section", "fieldtype")
    if pricing_fieldtype and pricing_fieldtype != "Tab Break":
        frappe.delete_doc("Custom Field", "Branch-custom_cen_pricing_section", force=True)

    if frappe.db.exists("Custom Field", "User Permission-custom_cen_source_branch"):
        frappe.delete_doc("Custom Field", "User Permission-custom_cen_source_branch", force=True)

    custom_fields = {
        "Branch": [
            {"fieldname": "custom_cen_default_company", "label": "Company", "fieldtype": "Link", "options": "Company", "insert_after": "branch"},
            {"fieldname": "custom_cen_warehouse_section", "label": "Warehouse", "fieldtype": "Section Break", "insert_after": "custom_cen_default_company"},
            {"fieldname": "custom_cen_warehouse_parent", "label": "Warehouse Parent", "fieldtype": "Link", "options": "Warehouse", "insert_after": "custom_cen_warehouse_section"},
            {"fieldname": "custom_cen_warehouse_col", "fieldtype": "Column Break", "insert_after": "custom_cen_warehouse_parent"},
            {"fieldname": "custom_cen_default_warehouse", "label": "Default Warehouse", "fieldtype": "Link", "options": "Warehouse", "insert_after": "custom_cen_warehouse_col"},
            {"fieldname": "custom_cen_cost_center_section", "label": "Cost Center", "fieldtype": "Section Break", "insert_after": "custom_cen_default_warehouse"},
            {"fieldname": "custom_cen_cost_center_parent", "label": "Cost Center Parent", "fieldtype": "Link", "options": "Cost Center", "insert_after": "custom_cen_cost_center_section"},
            {"fieldname": "custom_cen_cost_center_col", "fieldtype": "Column Break", "insert_after": "custom_cen_cost_center_parent"},
            {"fieldname": "custom_cen_default_cost_center", "label": "Default Cost Center", "fieldtype": "Link", "options": "Cost Center", "insert_after": "custom_cen_cost_center_col"},
            {"fieldname": "custom_cen_address_section", "label": "Address", "fieldtype": "Section Break", "insert_after": "custom_cen_default_cost_center"},
            {"fieldname": "custom_cen_branch_address", "label": "Branch Address", "fieldtype": "Link", "options": "Address", "insert_after": "custom_cen_address_section"},
            {"fieldname": "custom_cen_pricing_section", "label": "Configuration", "fieldtype": "Tab Break", "insert_after": "custom_cen_branch_address"},
            {"fieldname": "custom_cen_default_selling_price_list", "label": "Default Selling Price List", "fieldtype": "Link", "options": "Price List", "insert_after": "custom_cen_pricing_section"},
            {"fieldname": "custom_cen_allowed_selling_price_lists", "label": "Allowed Selling Price Lists", "fieldtype": "Table", "options": "Branch Allowed Selling Price List", "insert_after": "custom_cen_default_selling_price_list"},
            {"fieldname": "custom_cen_pricing_col", "fieldtype": "Column Break", "insert_after": "custom_cen_allowed_selling_price_lists"},
            {"fieldname": "custom_cen_default_buying_price_list", "label": "Default Buying Price List", "fieldtype": "Link", "options": "Price List", "insert_after": "custom_cen_pricing_col"},
            {"fieldname": "custom_cen_allowed_buying_price_lists", "label": "Allowed Buying Price Lists", "fieldtype": "Table", "options": "Branch Allowed Buying Price List", "insert_after": "custom_cen_default_buying_price_list"},
            {"fieldname": "custom_cen_item_groups_section", "label": "Allowed Item Groups", "fieldtype": "Section Break", "insert_after": "custom_cen_allowed_buying_price_lists"},
            {"fieldname": "custom_cen_allowed_item_groups", "label": "Allowed Item Groups", "fieldtype": "Table", "options": "Branch Item Group", "insert_after": "custom_cen_item_groups_section"},
            {"fieldname": "custom_cen_users_tab", "label": "User Access", "fieldtype": "Tab Break", "insert_after": "custom_cen_allowed_item_groups"},
            {"fieldname": "custom_cen_counter_section", "fieldtype": "Section Break", "hidden": 0, "insert_after": "custom_cen_users_tab"},
            {"fieldname": "custom_cen_total_users_html", "fieldtype": "HTML", "insert_after": "custom_cen_counter_section"},
            {"fieldname": "custom_cen_table_section", "label": "Assigned Users", "fieldtype": "Section Break", "insert_after": "custom_cen_total_users_html"},
            {"fieldname": "custom_cen_branch_users", "label": "Assigned Branch Users", "fieldtype": "Table", "options": "Branch User", "insert_after": "custom_cen_table_section"}
        ],
        "Lead": [
            {"fieldname": "custom_cen_branch", "label": "Branch", "fieldtype": "Link", "options": "Branch", "insert_after": "company", "in_standard_filter": 1}
        ],
        "Opportunity": [
            {"fieldname": "custom_cen_branch", "label": "Branch", "fieldtype": "Link", "options": "Branch", "insert_after": "company", "in_standard_filter": 1}
        ],
        "Quotation": [
            {"fieldname": "custom_cen_branch", "label": "Branch", "fieldtype": "Link", "options": "Branch", "insert_after": "company", "in_standard_filter": 1}
        ],
        # Not named custom_cen_branch like the transaction fields: the switcher keeps
        # the active branch as a user default under that key, and Frappe fills any
        # new document's field from a same-named user default -- so every address a
        # branch user creates (customer addresses included) would get their branch.
        # ignore_user_permissions for the same reason: a user with a single Branch
        # permission would otherwise get it pre-filled as well. An address only
        # belongs to a branch when someone sets it.
        "Address": [
            {"fieldname": "custom_cen_address_branch", "label": "Branch", "fieldtype": "Link", "options": "Branch", "insert_after": "links", "in_standard_filter": 1, "ignore_user_permissions": 1,
             "description": "Set for a company address that belongs to one branch. Transactions of that branch only offer its addresses."}
        ],
        # The one input for which branch a user lands on at login. The name matches
        # none of the switcher's user-default keys (branch, custom_cen_branch,
        # cen_branch_*), which Frappe would otherwise copy into it on new users;
        # ignore_user_permissions stops the same pre-fill by doctype for an admin
        # who has a single Branch permission.
        "User": [
            {"fieldname": "custom_cen_default_branch", "label": "Default Branch", "fieldtype": "Link", "options": "Branch", "insert_after": "time_zone", "ignore_user_permissions": 1,
             "description": "The branch this user starts in after logging in. Leave empty to start on All Branches."}
        ],
        "User Permission": [
            {"fieldname": "custom_cen_branch_setup_section", "label": "Branch Setup Details", "fieldtype": "Section Break", "insert_after": "apply_to_all_doctypes"},
            {"fieldname": "custom_cen_from_branch_setup", "label": "Created via Branch Setup", "fieldtype": "Check", "default": "0", "read_only": 1, "insert_after": "custom_cen_branch_setup_section"},
            {"fieldname": "custom_cen_source_branch", "label": "Source Branch", "fieldtype": "Table", "options": "User Permission Source Branch", "read_only": 1, "insert_after": "custom_cen_from_branch_setup"}
        ]
    }
    create_custom_fields(custom_fields)

def setup_accounting_dimension():
    # Only create if it doesn't exist to prevent duplicate errors
    if not frappe.db.exists("Accounting Dimension", "Branch"):
        doc = frappe.new_doc("Accounting Dimension")
        doc.document_type = "Branch"
        doc.insert(ignore_permissions=True)

def setup_branch_role_permissions():
    role_perms = {
        "System Manager": {"read": 1, "write": 1, "create": 1, "delete": 1},
        "Supervisor": {"read": 1, "write": 1, "create": 1, "delete": 0},
        "Sales Person": {"read": 1, "write": 1, "create": 1, "delete": 0},
        "Sales User": {"read": 1, "write": 0, "create": 0, "delete": 0},
        "Purchase User": {"read": 1, "write": 0, "create": 0, "delete": 0},
        "Stock User": {"read": 1, "write": 0, "create": 0, "delete": 0}
    }
    
    for role, perms in role_perms.items():
        if not frappe.db.exists("Role", role):
            continue
            
        if frappe.db.exists("Custom DocPerm", {"parent": "Branch", "role": role}):
            continue
            
        doc = frappe.new_doc("Custom DocPerm")
        doc.parent = "Branch"
        doc.parenttype = "DocType"
        doc.parentfield = "permissions"
        doc.role = role
        for key, val in perms.items():
            doc.set(key, val)
        doc.insert(ignore_permissions=True)

def after_migrate():
    add_custom_fields()
    setup_accounting_dimension()
    setup_branch_role_permissions()


