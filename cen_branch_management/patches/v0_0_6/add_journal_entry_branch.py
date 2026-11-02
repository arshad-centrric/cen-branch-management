from cen_branch_management.overrides.header_branch import backfill_header_branch
from cen_branch_management.setup import add_custom_fields


def execute():
    """Add the header Branch field on Journal Entry and fill it on existing
    entries whose account lines all share one branch.
    """
    add_custom_fields()
    backfill_header_branch("Journal Entry")
