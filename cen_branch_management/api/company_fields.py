"""Bring a draft back in line with its company after the company changes.

A branch switch on an open new document can move it to another company. ERPNext
filters the account, cost center and tax template fields by the new company, but
values already filled in (from the old company) stay, until someone clears and
re-picks them. get_company_corrections() finds those values and works out what
ERPNext would have filled in for the new company; branch_filters.js applies them.
"""

import json

import erpnext
import frappe
from erpnext.setup.doctype.brand.brand import get_brand_defaults
from erpnext.setup.doctype.item_group.item_group import get_item_group_defaults
from erpnext.stock.doctype.item.item import get_item_defaults
from erpnext.stock.get_item_details import (
    get_default_cost_center,
    get_default_expense_account,
    get_default_income_account,
)

TAX_TEMPLATE_DOCTYPES = ("Sales Taxes and Charges Template", "Purchase Taxes and Charges Template")
TAX_LINE_DOCTYPES = ("Sales Taxes and Charges", "Purchase Taxes and Charges")
COMPANY_LINK_DOCTYPES = ("Account", "Cost Center") + TAX_TEMPLATE_DOCTYPES


@frappe.whitelist()
def get_company_corrections(doctype, company, values, branch=None):
    """values: {"header": {fieldname: value},
                "rows": [{"name", "doctype", "parentfield", "item_code", "values": {fieldname: value}}]}

    Returns {"header": {fieldname: new value or None},
             "rows": {row name: {fieldname: new value or None}},
             "clear_tables": [parentfield, ...]}
    covering only values that belong to a company other than `company`.
    """
    frappe.has_permission(doctype, "read", throw=True)
    if isinstance(values, str):
        values = json.loads(values)

    meta = frappe.get_meta(doctype)
    header = _company_links(meta, values.get("header") or {})
    rows = []
    for row in values.get("rows") or []:
        if meta.get_field(row.get("parentfield")) and frappe.get_meta(row.get("doctype")).istable:
            rows.append((row, _company_links(frappe.get_meta(row["doctype"]), row.get("values") or {})))

    stale = _foreign_values(company, [header] + [links for _, links in rows])
    is_stale = lambda link: (link["options"], link["value"]) in stale

    out = {"header": {}, "rows": {}, "clear_tables": []}
    branch_cost_center = _branch_cost_center(branch, company)
    template_replaced = False

    for fieldname, link in header.items():
        if not is_stale(link):
            continue
        if link["options"] in TAX_TEMPLATE_DOCTYPES:
            new_template = _default_tax_template(link["options"], company)
            out["header"][fieldname] = new_template
            template_replaced = template_replaced or bool(new_template)
        elif link["options"] == "Cost Center":
            out["header"][fieldname] = branch_cost_center or frappe.get_cached_value("Company", company, "cost_center")

    for row, links in rows:
        stale_links = {fieldname: link for fieldname, link in links.items() if is_stale(link)}
        if not stale_links:
            continue

        # Tax lines come from the template: reloading it replaces them. Without a
        # template to reload they are cleared, as they all belong to the old company.
        if row["doctype"] in TAX_LINE_DOCTYPES:
            if not template_replaced and row["parentfield"] not in out["clear_tables"]:
                out["clear_tables"].append(row["parentfield"])
            continue

        defaults = _line_defaults(doctype, row, company, branch_cost_center)
        out["rows"][row["name"]] = {fieldname: defaults.get(fieldname) for fieldname in stale_links}

    return out


def _company_links(meta, values):
    """fieldname -> {options, value} for the values that point at a company-bound doctype."""
    links = {}
    for fieldname, value in values.items():
        df = meta.get_field(fieldname)
        if value and df and df.fieldtype == "Link" and df.options in COMPANY_LINK_DOCTYPES:
            links[fieldname] = {"options": df.options, "value": value}
    return links


def _foreign_values(company, link_groups):
    """(doctype, name) pairs, among the given links, that belong to another company."""
    by_doctype = {}
    for links in link_groups:
        for link in links.values():
            by_doctype.setdefault(link["options"], set()).add(link["value"])

    stale = set()
    for link_doctype, names in by_doctype.items():
        for name, owner in frappe.get_all(
            link_doctype, filters={"name": ["in", list(names)]}, fields=["name", "company"], as_list=True
        ):
            if owner and owner != company:
                stale.add((link_doctype, name))
    return stale


def _branch_cost_center(branch, company):
    """The branch's default cost center, when it belongs to `company`."""
    if not branch:
        return None
    cost_center = frappe.db.get_value("Branch", branch, "custom_cen_default_cost_center")
    if cost_center and frappe.get_cached_value("Cost Center", cost_center, "company") == company:
        return cost_center
    return None


def _default_tax_template(template_doctype, company):
    return frappe.db.get_value(template_doctype, {"company": company, "is_default": 1, "disabled": 0})


def _line_defaults(doctype, row, company, branch_cost_center):
    """What ERPNext fills in on a line for `company`: from the item's, item
    group's and brand's defaults for that company, else the company's own.
    Fields with no such default (e.g. an account picked by hand on a journal
    line) come back empty.
    """
    out = {"cost_center": branch_cost_center}
    item_code = row.get("item_code")

    if not item_code:
        out["cost_center"] = out["cost_center"] or frappe.get_cached_value("Company", company, "cost_center")
        return out

    item = get_item_defaults(item_code, company)
    item_group = get_item_group_defaults(item_code, company)
    brand = get_brand_defaults(item_code, company)
    ctx = frappe._dict(doctype=doctype, company=company, item_code=item_code)
    company_value = lambda fieldname: frappe.get_cached_value("Company", company, fieldname)

    if doctype == "Stock Entry":
        # Stock Entry's "Difference Account" (see StockEntry.get_item_details).
        out["expense_account"] = (
            item.get("expense_account") or item_group.get("expense_account") or company_value("stock_adjustment_account")
        )
    else:
        # As in get_item_details: a stock item received into stock books
        # against Stock Received But Not Billed.
        fallback = "default_expense_account"
        if doctype == "Purchase Receipt" and item.get("is_stock_item") and erpnext.is_perpetual_inventory_enabled(company):
            fallback = "stock_received_but_not_billed"
        out["expense_account"] = get_default_expense_account(ctx, item, item_group, brand) or company_value(fallback)
    out["income_account"] = get_default_income_account(ctx, item, item_group, brand) or company_value(
        "default_income_account"
    )

    if not out["cost_center"]:
        out["cost_center"] = get_default_cost_center(ctx, item, item_group, brand, company)

    return out
