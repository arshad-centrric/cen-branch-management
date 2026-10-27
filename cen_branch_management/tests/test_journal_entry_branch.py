import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from cen_branch_management.overrides.journal_entry_branch import backfill_journal_entry_branch
from cen_branch_management.tests import utils

HEADER = "custom_cen_branch"


class TestJournalEntryBranch(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = utils.get_companies()[0]
        cls.cash = frappe.db.get_value("Account", {"company": cls.company, "is_group": 0, "account_type": "Cash"})
        cls.expense = frappe.db.get_value(
            "Account", {"company": cls.company, "is_group": 0, "root_type": "Expense", "account_type": ""}
        )
        cls.cost_center = frappe.get_cached_value("Company", cls.company, "cost_center")
        cls.kochi = utils.make_branch(cls.company).name
        cls.calicut = utils.make_branch(cls.company).name

    def make_entry(self, header=None, line_branches=(None, None)):
        """A draft entry: expense debit line, cash credit line, with the given branches."""
        expense_branch, cash_branch = line_branches
        doc = frappe.get_doc({
            "doctype": "Journal Entry",
            "company": self.company,
            "posting_date": today(),
            HEADER: header,
            "accounts": [
                {"account": self.expense, "debit_in_account_currency": 100, "cost_center": self.cost_center, "branch": expense_branch},
                {"account": self.cash, "credit_in_account_currency": 100, "cost_center": self.cost_center, "branch": cash_branch},
            ],
        })
        doc.insert(ignore_permissions=True)
        return doc

    def line_branches(self, doc):
        return [row.branch for row in doc.accounts]

    def test_header_fills_lines_without_a_branch(self):
        doc = self.make_entry(header=self.kochi)
        self.assertEqual(self.line_branches(doc), [self.kochi, self.kochi])

    def test_line_set_to_another_branch_is_kept(self):
        doc = self.make_entry(header=self.kochi, line_branches=(None, self.calicut))
        self.assertEqual(self.line_branches(doc), [self.kochi, self.calicut])
        self.assertEqual(doc.get(HEADER), self.kochi)

    def test_header_taken_from_lines_sharing_one_branch(self):
        doc = self.make_entry(line_branches=(self.calicut, self.calicut))
        self.assertEqual(doc.get(HEADER), self.calicut)

    def test_header_stays_empty_for_mixed_or_missing_line_branches(self):
        self.assertFalse(self.make_entry(line_branches=(self.kochi, self.calicut)).get(HEADER))
        self.assertFalse(self.make_entry(line_branches=(self.kochi, None)).get(HEADER))
        self.assertFalse(self.make_entry().get(HEADER))

    def test_ledger_uses_each_lines_branch(self):
        doc = self.make_entry(header=self.kochi, line_branches=(None, self.calicut))
        doc.submit()

        gl = dict(frappe.get_all(
            "GL Entry",
            filters={"voucher_type": "Journal Entry", "voucher_no": doc.name, "is_cancelled": 0},
            fields=["account", "branch"],
            as_list=True,
        ))
        self.assertEqual(gl, {self.expense: self.kochi, self.cash: self.calicut})

    def test_backfill_fills_only_single_branch_entries(self):
        single = self.make_entry(line_branches=(self.kochi, self.kochi))
        mixed = self.make_entry(line_branches=(self.kochi, self.calicut))
        partial = self.make_entry(line_branches=(self.kochi, None))
        kept = self.make_entry(header=self.calicut, line_branches=(self.kochi, self.kochi))

        # As they would be on a site from before the header field existed.
        for doc in (single, mixed, partial):
            frappe.db.set_value("Journal Entry", doc.name, HEADER, None, update_modified=False)

        backfill_journal_entry_branch()

        header_of = lambda doc: frappe.db.get_value("Journal Entry", doc.name, HEADER)
        self.assertEqual(header_of(single), self.kochi)
        self.assertFalse(header_of(mixed))
        self.assertFalse(header_of(partial))
        self.assertEqual(header_of(kept), self.calicut)
