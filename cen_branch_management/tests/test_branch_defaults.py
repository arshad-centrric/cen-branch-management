import frappe
from frappe.tests import IntegrationTestCase

from cen_branch_management.api import switcher
from cen_branch_management.tests import utils


class TestBranchDefaults(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        companies = utils.get_companies()
        cls.company = companies[0]
        cls.other_company = companies[1] if len(companies) > 1 else None

        # Two sibling trees in the branch's company: "inside" is the branch's
        # own parent, "outside" is a different one.
        cls.wh_parent = utils.make_warehouse(cls.company, is_group=1)
        cls.wh_inside = utils.make_warehouse(cls.company, parent=cls.wh_parent)
        cls.wh_other_parent = utils.make_warehouse(cls.company, is_group=1)
        cls.wh_outside = utils.make_warehouse(cls.company, parent=cls.wh_other_parent)

        cls.cc_parent = utils.make_cost_center(cls.company, is_group=1)
        cls.cc_inside = utils.make_cost_center(cls.company, parent=cls.cc_parent)
        cls.cc_other_parent = utils.make_cost_center(cls.company, is_group=1)
        cls.cc_outside = utils.make_cost_center(cls.company, parent=cls.cc_other_parent)

    def tearDown(self):
        frappe.set_user("Administrator")

    def make_branch(self, **fields):
        return utils.make_branch(company=self.company, **fields)

    def assert_rejected(self, expected_message, **fields):
        with self.assertRaises(frappe.ValidationError) as raised:
            self.make_branch(**fields)
        self.assertIn(expected_message, str(raised.exception))

    # Default Warehouse

    def test_default_warehouse_inside_parent_is_accepted(self):
        branch = self.make_branch(
            custom_cen_warehouse_parent=self.wh_parent, custom_cen_default_warehouse=self.wh_inside
        )
        self.assertEqual(branch.custom_cen_default_warehouse, self.wh_inside)

    def test_default_warehouse_cannot_be_a_group(self):
        self.assert_rejected(
            "is a group",
            custom_cen_warehouse_parent=self.wh_parent,
            custom_cen_default_warehouse=self.wh_parent,
        )

    def test_default_warehouse_must_be_inside_parent(self):
        self.assert_rejected(
            "is not under the Warehouse Parent",
            custom_cen_warehouse_parent=self.wh_parent,
            custom_cen_default_warehouse=self.wh_outside,
        )

    def test_default_warehouse_must_be_in_branch_company(self):
        if not self.other_company:
            self.skipTest("Needs a second company on the site")

        foreign_warehouse = utils.make_warehouse(self.other_company)
        self.assert_rejected("belongs to company", custom_cen_default_warehouse=foreign_warehouse)

    def test_default_warehouse_needs_a_company_on_the_branch(self):
        with self.assertRaises(frappe.ValidationError) as raised:
            utils.make_branch(company=None, custom_cen_default_warehouse=self.wh_inside)
        self.assertIn("set the Company", str(raised.exception))

    # Default Cost Center

    def test_default_cost_center_inside_parent_is_accepted(self):
        branch = self.make_branch(
            custom_cen_cost_center_parent=self.cc_parent, custom_cen_default_cost_center=self.cc_inside
        )
        self.assertEqual(branch.custom_cen_default_cost_center, self.cc_inside)

    def test_default_cost_center_cannot_be_a_group(self):
        self.assert_rejected(
            "is a group",
            custom_cen_cost_center_parent=self.cc_parent,
            custom_cen_default_cost_center=self.cc_parent,
        )

    def test_default_cost_center_must_be_inside_parent(self):
        self.assert_rejected(
            "is not under the Cost Center Parent",
            custom_cen_cost_center_parent=self.cc_parent,
            custom_cen_default_cost_center=self.cc_outside,
        )

    def test_default_cost_center_must_be_in_branch_company(self):
        if not self.other_company:
            self.skipTest("Needs a second company on the site")

        foreign_cost_center = utils.make_cost_center(self.other_company)
        self.assert_rejected("belongs to company", custom_cen_default_cost_center=foreign_cost_center)

    def test_default_cost_center_without_parent_still_checked(self):
        # No Cost Center Parent: any leaf of the company is fine, a group is not.
        branch = self.make_branch(custom_cen_default_cost_center=self.cc_outside)
        self.assertEqual(branch.custom_cen_default_cost_center, self.cc_outside)

        self.assert_rejected("is a group", custom_cen_default_cost_center=self.cc_other_parent)

    # Allowed Item Groups

    def test_same_item_group_cannot_be_added_twice(self):
        group = utils.make_item_group()
        self.assert_rejected("already in Allowed Item Groups", item_groups=[group, group])

    # Branch switch

    def test_switching_branch_sets_and_clears_the_defaults(self):
        user = utils.make_user()
        with_defaults = self.make_branch(
            users=[user],
            custom_cen_warehouse_parent=self.wh_parent,
            custom_cen_default_warehouse=self.wh_inside,
            custom_cen_cost_center_parent=self.cc_parent,
            custom_cen_default_cost_center=self.cc_inside,
        )
        without_defaults = self.make_branch(users=[user])

        def current(key):
            return frappe.defaults.get_user_default(key, user)

        frappe.set_user(user)

        scope = switcher.set_active_branch(with_defaults.name)["scope"]
        self.assertEqual(scope["cen_branch_default_warehouse"], self.wh_inside)
        self.assertEqual(scope["cen_branch_default_cost_center"], self.cc_inside)
        self.assertEqual(current("cen_branch_default_warehouse"), self.wh_inside)
        self.assertEqual(current("cen_branch_default_cost_center"), self.cc_inside)

        # A branch with no defaults must not inherit the previous branch's.
        switcher.set_active_branch(without_defaults.name)
        self.assertEqual(current("branch"), without_defaults.name)
        self.assertIsNone(current("cen_branch_default_warehouse"))
        self.assertIsNone(current("cen_branch_default_cost_center"))

        switcher.set_active_branch(with_defaults.name)
        self.assertEqual(current("cen_branch_default_warehouse"), self.wh_inside)

        switcher.set_active_branch("All Branches")
        self.assertIsNone(current("cen_branch_default_warehouse"))
        self.assertIsNone(current("cen_branch_default_cost_center"))
