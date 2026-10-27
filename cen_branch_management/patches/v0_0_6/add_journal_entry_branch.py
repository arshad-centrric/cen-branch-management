from cen_branch_management.overrides.journal_entry_branch import backfill_journal_entry_branch
from cen_branch_management.setup import add_custom_fields


def execute():
    """Add the header Branch field on Journal Entry and fill it on existing
    entries whose account lines all share one branch.
    """
    add_custom_fields()
    backfill_journal_entry_branch()
