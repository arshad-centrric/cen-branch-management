from cen_branch_management.setup import add_custom_fields


def execute():
    """Bring existing sites the Warehouse Access section and the Restricted
    Warehouses table on Branch. add_custom_fields() defines them and is safe to
    re-run. (The new Branch User columns come with the doctype itself.)
    """
    add_custom_fields()
