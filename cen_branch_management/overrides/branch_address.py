import frappe
from frappe import _

# Branch.custom_cen_branch_address is the branch's own address; an Address says
# which branch it belongs to in custom_cen_address_branch. A branch can own
# several company addresses (billing, dispatch, ...); the Branch Address is the
# one picked on the Branch itself, and saving the Branch keeps it stamped.
BRANCH_ADDRESS_FIELD = "custom_cen_branch_address"
ADDRESS_BRANCH_FIELD = "custom_cen_address_branch"


def validate_branch_address(doc, method=None):
    """Branch validate: the Branch Address must be an address of the branch's
    company, and must not already belong to a different branch."""
    address = doc.get(BRANCH_ADDRESS_FIELD)
    if not address:
        return

    company = doc.get("custom_cen_default_company")
    if not company:
        frappe.throw(
            _("Please set the Company on this branch before choosing a Branch Address."),
            title=_("Company Required"),
        )

    if not frappe.db.exists("Address", address):
        # Left to the standard link validation, which runs after this hook.
        return

    if not _is_company_address(address, company):
        frappe.throw(
            _("Address {0} is not linked to company {1}. Add the company under Links on the address, or pick another address.").format(
                frappe.bold(address), frappe.bold(company)
            ),
            title=_("Invalid Branch Address"),
        )

    owner_branch = frappe.db.get_value("Address", address, ADDRESS_BRANCH_FIELD)
    if not owner_branch or owner_branch == doc.name:
        # Not stamped (yet): make sure no other branch already picked it.
        owner_branch = frappe.db.get_value(
            "Branch", {BRANCH_ADDRESS_FIELD: address, "name": ["!=", doc.name]}, "name"
        )

    if owner_branch and owner_branch != doc.name:
        frappe.throw(
            _("Address {0} already belongs to branch {1}. Please pick another address.").format(
                frappe.bold(address), frappe.bold(owner_branch)
            ),
            title=_("Invalid Branch Address"),
        )


def sync_branch_address(doc, method=None):
    """Branch on_update: stamp the chosen address with this branch, and release
    the previous one -- but only if it still points here, so an address that was
    meanwhile given to another branch is left alone."""
    previous = doc.get_doc_before_save()
    old_address = previous.get(BRANCH_ADDRESS_FIELD) if previous else None
    new_address = doc.get(BRANCH_ADDRESS_FIELD)

    if old_address and old_address != new_address:
        _release_address(old_address, doc.name)

    if new_address and frappe.db.get_value("Address", new_address, ADDRESS_BRANCH_FIELD) != doc.name:
        frappe.db.set_value("Address", new_address, ADDRESS_BRANCH_FIELD, doc.name)


def release_branch_addresses(doc, method=None):
    """Branch on_trash: addresses stop pointing at a branch that is going away
    (the link would otherwise block the deletion)."""
    for address in frappe.get_all("Address", filters={ADDRESS_BRANCH_FIELD: doc.name}, pluck="name"):
        frappe.db.set_value("Address", address, ADDRESS_BRANCH_FIELD, None)


def validate_address_branch(doc, method=None):
    """Address validate: an address can only belong to a branch of a company it
    is linked to."""
    branch = doc.get(ADDRESS_BRANCH_FIELD)
    if not branch:
        return

    company = frappe.db.get_value("Branch", branch, "custom_cen_default_company")
    if not company:
        frappe.throw(
            _("Branch {0} has no Company set, so addresses cannot be assigned to it yet.").format(frappe.bold(branch)),
            title=_("Invalid Branch"),
        )

    linked_to_company = any(
        link.link_doctype == "Company" and link.link_name == company for link in doc.get("links") or []
    )
    if not linked_to_company:
        frappe.throw(
            _("Branch {0} is under company {1}. Add that company under Links on this address, or clear the Branch.").format(
                frappe.bold(branch), frappe.bold(company)
            ),
            title=_("Invalid Branch"),
        )


def _is_company_address(address, company):
    return bool(
        frappe.db.exists(
            "Dynamic Link",
            {"parenttype": "Address", "parent": address, "link_doctype": "Company", "link_name": company},
        )
    )


def _release_address(address, branch_name):
    if frappe.db.get_value("Address", address, ADDRESS_BRANCH_FIELD) == branch_name:
        frappe.db.set_value("Address", address, ADDRESS_BRANCH_FIELD, None)
