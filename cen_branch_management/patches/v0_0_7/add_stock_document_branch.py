from cen_branch_management.overrides.header_branch import backfill_header_branch
from cen_branch_management.setup import add_custom_fields


def execute():
    """Add the header Branch field on Material Request and Stock Entry and fill
    it on existing documents (see backfill_header_branch).
    """
    add_custom_fields()
    backfill_header_branch("Material Request")
    backfill_header_branch("Stock Entry")
