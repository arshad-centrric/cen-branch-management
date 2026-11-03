import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from cen_branch_management.api.company_fields import get_company_corrections
from cen_branch_management.overrides.header_branch import backfill_header_branch
from cen_branch_management.tests import utils

HEADER = "custom_cen_branch"


def company_value(company, fieldname):
    return frappe.get_cached_value("Company", company, fieldname)


class TestStockDocumentBranch(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = utils.get_companies()[0]
        cls.item = frappe.db.get_value(
            "Item", {"is_stock_item": 1, "disabled": 0, "has_variants": 0, "has_serial_no": 0, "has_batch_no": 0}
        )
        cls.warehouse = frappe.db.get_value("Warehouse", {"company": cls.company, "is_group": 0})
        cls.kochi = utils.make_branch(cls.company).name
        cls.calicut = utils.make_branch(cls.company).name

    def make_material_request(self, header=None, line_branches=(None, None)):
        doc = frappe.get_doc({
            "doctype": "Material Request",
            "material_request_type": "Purchase",
            "company": self.company,
            "transaction_date": today(),
            "schedule_date": add_days(today(), 1),
            HEADER: header,
            "items": [
                {"item_code": self.item, "qty": 1, "warehouse": self.warehouse, "schedule_date": add_days(today(), 1), "branch": branch}
                for branch in line_branches
            ],
        })
        doc.insert(ignore_permissions=True)
        return doc

    def make_stock_entry(self, header=None, dimension_header=None, line_branches=(None, None)):
        doc = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "company": self.company,
            "posting_date": today(),
            HEADER: header,
            "branch": dimension_header,
            "items": [
                {"item_code": self.item, "qty": 1, "basic_rate": 10, "t_warehouse": self.warehouse, "branch": branch}
                for branch in line_branches
            ],
        })
        doc.insert(ignore_permissions=True)
        return doc

    def test_material_request_lines_take_the_header_branch(self):
        doc = self.make_material_request(header=self.kochi, line_branches=(None, self.calicut))
        self.assertEqual([row.branch for row in doc.items], [self.kochi, self.calicut])

    def test_material_request_header_taken_from_lines_sharing_one_branch(self):
        self.assertEqual(self.make_material_request(line_branches=(self.calicut, self.calicut)).get(HEADER), self.calicut)
        self.assertFalse(self.make_material_request(line_branches=(self.kochi, self.calicut)).get(HEADER))

    def test_stock_entry_keeps_erpnexts_header_branch_equal(self):
        doc = self.make_stock_entry(header=self.kochi, dimension_header=self.calicut)
        self.assertEqual((doc.get(HEADER), doc.branch), (self.kochi, self.kochi))
        self.assertEqual([row.branch for row in doc.items], [self.kochi, self.kochi])

    def test_stock_entry_header_taken_from_erpnexts_header_branch(self):
        doc = self.make_stock_entry(dimension_header=self.calicut)
        self.assertEqual(doc.get(HEADER), self.calicut)

    def test_backfill(self):
        from_dimension = self.make_stock_entry(dimension_header=self.calicut)
        from_lines = self.make_material_request(line_branches=(self.kochi, self.kochi))
        mixed = self.make_material_request(line_branches=(self.kochi, self.calicut))
        for doc in (from_dimension, from_lines, mixed):
            frappe.db.set_value(doc.doctype, doc.name, HEADER, None, update_modified=False)

        backfill_header_branch("Stock Entry")
        backfill_header_branch("Material Request")

        header_of = lambda doc: frappe.db.get_value(doc.doctype, doc.name, HEADER)
        self.assertEqual(header_of(from_dimension), self.calicut)
        self.assertEqual(header_of(from_lines), self.kochi)
        self.assertFalse(header_of(mixed))


class TestCompanyCorrections(IntegrationTestCase):
    """Values left over from the old company after a draft moves to another one."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        companies = utils.get_companies()
        if len(companies) < 2:
            raise cls.skipTest(cls, "needs two companies")
        cls.old, cls.new = companies
        cls.item = frappe.db.get_value(
            "Item", {"is_stock_item": 1, "disabled": 0, "has_variants": 0, "has_serial_no": 0, "has_batch_no": 0}
        )

    def item_row(self, row_doctype, **values):
        return {"name": "row-1", "doctype": row_doctype, "parentfield": "items", "item_code": self.item, "values": values}

    def test_sales_invoice_lines_and_template_move_to_the_new_company(self):
        old_template = frappe.db.get_value("Sales Taxes and Charges Template", {"company": self.old})
        values = {
            "header": {"taxes_and_charges": old_template},
            "rows": [self.item_row(
                "Sales Invoice Item",
                income_account=company_value(self.old, "default_income_account"),
                expense_account=company_value(self.old, "default_expense_account"),
                cost_center=company_value(self.old, "cost_center"),
            )],
        }

        fix = get_company_corrections("Sales Invoice", self.new, values)

        row = fix["rows"]["row-1"]
        for fieldname, value in row.items():
            self.assertTrue(value, fieldname)
            self.assertEqual(frappe.db.get_value("Account" if "account" in fieldname else "Cost Center", value, "company"), self.new)
        self.assertEqual(
            fix["header"]["taxes_and_charges"],
            frappe.db.get_value("Sales Taxes and Charges Template", {"company": self.new, "is_default": 1, "disabled": 0}),
        )

    def test_values_of_the_right_company_are_left_alone(self):
        values = {
            "header": {},
            "rows": [self.item_row("Sales Invoice Item", income_account=company_value(self.new, "default_income_account"))],
        }
        self.assertEqual(get_company_corrections("Sales Invoice", self.new, values)["rows"], {})

    def test_stock_entry_difference_account_and_branch_cost_center(self):
        branch_cost_center = utils.make_cost_center(self.new)
        branch = utils.make_branch(self.new, custom_cen_default_cost_center=branch_cost_center).name
        values = {
            "header": {},
            "rows": [self.item_row(
                "Stock Entry Detail",
                expense_account=company_value(self.old, "stock_adjustment_account"),
                cost_center=company_value(self.old, "cost_center"),
            )],
        }

        row = get_company_corrections("Stock Entry", self.new, values, branch=branch)["rows"]["row-1"]

        self.assertEqual(row["cost_center"], branch_cost_center)
        self.assertEqual(frappe.db.get_value("Account", row["expense_account"], "company"), self.new)

    def test_tax_lines_cleared_when_the_new_company_has_no_default_template(self):
        frappe.db.set_value("Sales Taxes and Charges Template", {"company": self.new}, "is_default", 0)
        old_template = frappe.db.get_value("Sales Taxes and Charges Template", {"company": self.old})
        tax_account = frappe.db.get_value("Sales Taxes and Charges", {"parent": old_template}, "account_head")
        values = {
            "header": {"taxes_and_charges": old_template},
            "rows": [{"name": "tax-1", "doctype": "Sales Taxes and Charges", "parentfield": "taxes", "values": {"account_head": tax_account}}],
        }

        fix = get_company_corrections("Sales Invoice", self.new, values)

        self.assertIsNone(fix["header"]["taxes_and_charges"])
        self.assertEqual(fix["clear_tables"], ["taxes"])
