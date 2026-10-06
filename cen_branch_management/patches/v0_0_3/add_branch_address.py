from cen_branch_management.setup import add_custom_fields


def execute():
    """Bring existing sites the Branch Address field on Branch and the Branch
    field on Address. add_custom_fields() defines both and is safe to re-run.
    """
    add_custom_fields()
