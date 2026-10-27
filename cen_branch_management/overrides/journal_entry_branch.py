import frappe

HEADER_BRANCH_FIELD = "custom_cen_branch"
LINE_BRANCH_FIELD = "branch"


def sync_journal_entry_branch(doc, method=None):
    """Journal Entry doc_event (validate).

    With a header Branch, account lines that have none take it. Lines set to
    another branch keep theirs: an entry can move money between branches.

    Without one, the header is filled when every line has the same branch. That
    covers entries made outside the form (imports, the API, ERPNext's own
    entries), so they still show up under their branch in the list.
    """
    lines = doc.get("accounts") or []
    header = doc.get(HEADER_BRANCH_FIELD)

    if header:
        for line in lines:
            if not line.get(LINE_BRANCH_FIELD):
                line.set(LINE_BRANCH_FIELD, header)
        return

    branch = get_single_line_branch(lines)
    if branch:
        doc.set(HEADER_BRANCH_FIELD, branch)


def get_single_line_branch(lines):
    """The branch shared by every line, or None if any line has none or they differ."""
    branches = {line.get(LINE_BRANCH_FIELD) for line in lines}
    if len(branches) != 1:
        return None
    return branches.pop() or None


def backfill_journal_entry_branch():
    """Set the header Branch on existing entries whose lines all share one
    branch. Entries with mixed or missing line branches are left empty. Only the
    new header field is written; the ledger is not touched.
    """
    frappe.db.sql(
        """
        update `tabJournal Entry` je
        join (
            select parent, max(branch) as branch
            from `tabJournal Entry Account`
            where parenttype = 'Journal Entry'
            group by parent
            having count(*) = sum(ifnull(branch, '') != '') and count(distinct branch) = 1
        ) line_branch on line_branch.parent = je.name
        set je.custom_cen_branch = line_branch.branch
        where ifnull(je.custom_cen_branch, '') = ''
        """
    )
