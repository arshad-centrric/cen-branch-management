import frappe
from frappe.tests import IntegrationTestCase

from cen_branch_management.api.address import branch_address_query
from cen_branch_management.tests import utils

ADDRESS_BRANCH = "custom_cen_address_branch"


class TestBranchAddress(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        companies = utils.get_companies()
        cls.company = companies[0]
        cls.other_company = companies[1] if len(companies) > 1 else None

    def branch_of(self, address):
        return frappe.db.get_value("Address", address, ADDRESS_BRANCH)

    def set_branch_address(self, branch, address):
        branch.custom_cen_branch_address = address
        branch.save(ignore_permissions=True)

    def assert_rejected(self, expected_message, action):
        with self.assertRaises(frappe.ValidationError) as raised:
            action()
        self.assertIn(expected_message, str(raised.exception))

    def search(self, company, branch):
        rows = branch_address_query("Address", "", "name", 0, 100, {"company": company, "branch": branch})
        return {row[0] for row in rows}

    # Branch validation

    def test_address_must_be_linked_to_the_branch_company(self):
        unlinked = utils.make_address()
        self.assert_rejected(
            "is not linked to company",
            lambda: utils.make_branch(self.company, custom_cen_branch_address=unlinked),
        )

    def test_address_of_another_company_is_rejected(self):
        if not self.other_company:
            self.skipTest("Needs a second company on the site")

        foreign = utils.make_address(self.other_company)
        self.assert_rejected(
            "is not linked to company",
            lambda: utils.make_branch(self.company, custom_cen_branch_address=foreign),
        )

    def test_address_of_another_branch_is_rejected(self):
        address = utils.make_address(self.company)
        owner = utils.make_branch(self.company, custom_cen_branch_address=address)

        with self.assertRaises(frappe.ValidationError) as raised:
            utils.make_branch(self.company, custom_cen_branch_address=address)
        self.assertIn("already belongs to branch", str(raised.exception))
        self.assertIn(owner.name, str(raised.exception))

    def test_address_needs_a_company_on_the_branch(self):
        address = utils.make_address(self.company)
        self.assert_rejected(
            "set the Company",
            lambda: utils.make_branch(company=None, custom_cen_branch_address=address),
        )

    # Stamping on Branch save

    def test_saving_the_branch_stamps_the_address(self):
        address = utils.make_address(self.company)
        self.assertIsNone(self.branch_of(address))

        branch = utils.make_branch(self.company, custom_cen_branch_address=address)

        self.assertEqual(self.branch_of(address), branch.name)

    def test_changing_the_address_moves_the_stamp(self):
        first, second = utils.make_address(self.company), utils.make_address(self.company)
        branch = utils.make_branch(self.company, custom_cen_branch_address=first)

        self.set_branch_address(branch, second)

        self.assertIsNone(self.branch_of(first))
        self.assertEqual(self.branch_of(second), branch.name)

    def test_clearing_the_address_removes_the_stamp(self):
        address = utils.make_address(self.company)
        branch = utils.make_branch(self.company, custom_cen_branch_address=address)

        self.set_branch_address(branch, None)

        self.assertIsNone(self.branch_of(address))

    def test_old_address_given_to_another_branch_keeps_that_branch(self):
        old, new = utils.make_address(self.company), utils.make_address(self.company)
        branch = utils.make_branch(self.company, custom_cen_branch_address=old)
        other = utils.make_branch(self.company)

        # Someone re-assigned the old address directly on the Address.
        frappe.db.set_value("Address", old, ADDRESS_BRANCH, other.name)
        self.set_branch_address(branch, new)

        self.assertEqual(self.branch_of(old), other.name)
        self.assertEqual(self.branch_of(new), branch.name)

    def test_saving_again_keeps_the_stamp(self):
        address = utils.make_address(self.company)
        branch = utils.make_branch(self.company, custom_cen_branch_address=address)

        branch.save(ignore_permissions=True)

        self.assertEqual(self.branch_of(address), branch.name)

    def test_deleting_the_branch_releases_its_addresses(self):
        address = utils.make_address(self.company)
        branch = utils.make_branch(self.company, custom_cen_branch_address=address)

        frappe.delete_doc("Branch", branch.name, ignore_permissions=True)

        self.assertIsNone(self.branch_of(address))

    # Address validation

    def test_address_can_be_given_to_a_branch_of_its_company(self):
        branch = utils.make_branch(self.company)
        address = utils.make_address(self.company, branch=branch.name)
        self.assertEqual(self.branch_of(address), branch.name)

    def test_address_without_the_company_link_cannot_take_the_branch(self):
        branch = utils.make_branch(self.company)
        self.assert_rejected("is under company", lambda: utils.make_address(branch=branch.name))

    def test_address_of_another_company_cannot_take_the_branch(self):
        if not self.other_company:
            self.skipTest("Needs a second company on the site")

        branch = utils.make_branch(self.company)
        self.assert_rejected(
            "is under company", lambda: utils.make_address(self.other_company, branch=branch.name)
        )

    def test_address_without_a_branch_is_not_checked(self):
        self.assertIsNone(self.branch_of(utils.make_address()))

    # Branch form query

    def test_query_offers_free_and_own_addresses_only(self):
        branch = utils.make_branch(self.company)
        other = utils.make_branch(self.company)
        free = utils.make_address(self.company)
        own = utils.make_address(self.company, branch=branch.name)
        taken = utils.make_address(self.company, branch=other.name)
        not_company = utils.make_address()

        found = self.search(self.company, branch.name)

        self.assertIn(free, found)
        self.assertIn(own, found)
        self.assertNotIn(taken, found)
        self.assertNotIn(not_company, found)

    def test_query_needs_a_company(self):
        utils.make_address(self.company)
        self.assertEqual(self.search("", ""), set())
