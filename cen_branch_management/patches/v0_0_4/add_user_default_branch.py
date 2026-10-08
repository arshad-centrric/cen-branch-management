from cen_branch_management.setup import add_custom_fields


def execute():
    """Bring existing sites the Default Branch field on User.
    add_custom_fields() defines it and is safe to re-run.
    """
    add_custom_fields()
