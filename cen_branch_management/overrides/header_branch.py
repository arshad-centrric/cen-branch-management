import frappe

HEADER_BRANCH_FIELD = "custom_cen_branch"
LINE_BRANCH_FIELD = "branch"

# Documents with a header Branch whose lines carry the Branch accounting
# dimension: doctype -> (lines table, lines doctype). Keep in step with
# line_branch_tables in branch_filters.js.
LINE_TABLES = {
    "Journal Entry": ("accounts", "Journal Entry Account"),
    "Material Request": ("items", "Material Request Item"),
    "Stock Entry": ("items", "Stock Entry Detail"),
}


def sync_header_branch(doc, method=None):
    """validate hook for the LINE_TABLES doctypes.

    With a header Branch, lines that have none take it. Lines set to another
    branch keep theirs: an entry can span branches.

    Without one, the header is filled when every line has the same branch. That
    covers documents made outside the form (imports, the API, ERPNext's own
    entries), so they still show up under their branch.

    Stock Entry also has ERPNext's own header Branch (the accounting dimension,
    used for any line without one). It is kept equal to ours.
    """
    table, _ = LINE_TABLES[doc.doctype]
    lines = doc.get(table) or []
    has_dimension_header = doc.meta.has_field(LINE_BRANCH_FIELD)

    header = doc.get(HEADER_BRANCH_FIELD)
    if not header and has_dimension_header:
        header = doc.get(LINE_BRANCH_FIELD)

    if not header:
        header = get_single_line_branch(lines)
        if not header:
            return
    else:
        for line in lines:
            if not line.get(LINE_BRANCH_FIELD):
                line.set(LINE_BRANCH_FIELD, header)

    doc.set(HEADER_BRANCH_FIELD, header)
    if has_dimension_header:
        doc.set(LINE_BRANCH_FIELD, header)


def get_single_line_branch(lines):
    """The branch shared by every line, or None if any line has none or they differ."""
    branches = {line.get(LINE_BRANCH_FIELD) for line in lines}
    if len(branches) != 1:
        return None
    return branches.pop() or None


def backfill_header_branch(doctype):
    """Set the header Branch on existing documents, the same way a save would:
    from ERPNext's own header Branch where the doctype has one, else from the
    lines when they all share one branch. Documents with mixed or missing line
    branches are left empty. Only the new header field is written; the ledger
    is not touched.
    """
    _, lines_doctype = LINE_TABLES[doctype]

    if frappe.get_meta(doctype).has_field(LINE_BRANCH_FIELD):
        frappe.db.sql(
            f"""
            update `tab{doctype}`
            set custom_cen_branch = branch
            where ifnull(custom_cen_branch, '') = '' and ifnull(branch, '') != ''
            """
        )

    frappe.db.sql(
        f"""
        update `tab{doctype}` doc
        join (
            select parent, max(branch) as branch
            from `tab{lines_doctype}`
            where parenttype = %(doctype)s
            group by parent
            having count(*) = sum(ifnull(branch, '') != '') and count(distinct branch) = 1
        ) line_branch on line_branch.parent = doc.name
        set doc.custom_cen_branch = line_branch.branch
        where ifnull(doc.custom_cen_branch, '') = ''
        """,
        {"doctype": doctype},
    )
