from cen_branch_management.setup import add_custom_fields


def execute():
    """Bring existing sites up to the restructured Branch form: Warehouse and
    Cost Center sections with their new default fields, the "Pricing" tab
    relabelled "Configuration", and the Allowed Item Groups table.

    add_custom_fields() is the single definition of these fields (it also runs
    on every migrate) and is safe to run repeatedly, so this patch just calls it.
    """
    add_custom_fields()
