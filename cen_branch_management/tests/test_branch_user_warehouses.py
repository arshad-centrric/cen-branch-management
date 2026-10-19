import frappe
from frappe.tests import IntegrationTestCase

from cen_branch_management.api import switcher
from cen_branch_management.api.warehouse_access import get_user_branch_warehouses, get_user_default_warehouse
from cen_branch_management.tests import utils

FIELD = "custom_cen_user_warehouses"


class TestBranchUserWarehouses(IntegrationTestCase):
    """A branch's Warehouse Parent here:

        parent (group)
        ├── a        <- branch Default Warehouse
        ├── b
        └── sub (group)
            └── d
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = utils.get_companies()[0]
        cls.parent = utils.make_warehouse(cls.company, is_group=1)
        cls.a = utils.make_warehouse(cls.company, parent=cls.parent)
        cls.b = utils.make_warehouse(cls.company, parent=cls.parent)
        cls.sub = utils.make_warehouse(cls.company, is_group=1, parent=cls.parent)
        cls.d = utils.make_warehouse(cls.company, parent=cls.sub)
        cls.outside = utils.make_warehouse(cls.company)

    def tearDown(self):
        frappe.set_user("Administrator")

    def make_branch(self, users, restrictions=(), **fields):
        return utils.make_branch(
            self.company,
            users=users,
            custom_cen_warehouse_parent=self.parent,
            custom_cen_default_warehouse=self.a,
            **{FIELD: [{"user": user, "warehouse": warehouse} for user, warehouse in restrictions]},
            **fields,
        )

    def restrict(self, branch, restrictions):
        branch.set(FIELD, [{"user": user, "warehouse": warehouse} for user, warehouse in restrictions])
        branch.save(ignore_permissions=True)

    def warehouse_permissions(self, user):
        return utils.managed_permissions(user, "Warehouse")

    def summary(self, branch, user):
        return frappe.db.get_value("Branch User", {"parent": branch.name, "user": user}, "warehouse_access")

    def assert_rejected(self, expected_message, action):
        with self.assertRaises(frappe.ValidationError) as raised:
            action()
        self.assertIn(expected_message, str(raised.exception))

    # Who gets what

    def test_user_without_restrictions_gets_the_whole_warehouse_parent(self):
        user = utils.make_user()
        branch = self.make_branch([user])

        self.assertEqual(self.warehouse_permissions(user), {self.parent: [branch.name]})
        self.assertEqual(get_user_branch_warehouses(branch, user), sorted([self.a, self.b, self.d]))
        self.assertEqual(self.summary(branch, user), "All warehouses")

    def test_restricted_user_gets_only_their_warehouses(self):
        user = utils.make_user()
        branch = self.make_branch([user], restrictions=[(user, self.b)])

        self.assertEqual(self.warehouse_permissions(user), {self.b: [branch.name]})
        self.assertEqual(get_user_branch_warehouses(branch, user), [self.b])
        self.assertEqual(self.summary(branch, user), f"Only: {self.b}")

    def test_restricting_an_existing_user_removes_the_parent_permission(self):
        user = utils.make_user()
        branch = self.make_branch([user])

        self.restrict(branch, [(user, self.b)])

        self.assertEqual(self.warehouse_permissions(user), {self.b: [branch.name]})

    def test_lifting_the_restriction_gives_the_whole_parent_back(self):
        user = utils.make_user()
        branch = self.make_branch([user], restrictions=[(user, self.b)])

        self.restrict(branch, [])

        self.assertEqual(self.warehouse_permissions(user), {self.parent: [branch.name]})
        self.assertEqual(self.summary(branch, user), "All warehouses")

    def test_a_group_warehouse_covers_what_is_under_it(self):
        user = utils.make_user()
        branch = self.make_branch([user], restrictions=[(user, self.sub)])

        self.assertEqual(self.warehouse_permissions(user), {self.sub: [branch.name]})
        self.assertEqual(get_user_branch_warehouses(branch, user), [self.d])

    def test_restricting_one_user_leaves_the_others_alone(self):
        restricted, free = utils.make_user(), utils.make_user()
        branch = self.make_branch([restricted, free], restrictions=[(restricted, self.b)])

        self.assertEqual(self.warehouse_permissions(free), {self.parent: [branch.name]})
        self.assertEqual(get_user_branch_warehouses(branch, free), sorted([self.a, self.b, self.d]))

    def test_access_granted_by_another_branch_is_kept(self):
        user = utils.make_user()
        restricting = self.make_branch([user])
        other = self.make_branch([user])

        self.restrict(restricting, [(user, self.b)])

        # The whole parent still comes from the other branch; b now also from this one.
        self.assertEqual(self.warehouse_permissions(user), {self.parent: [other.name], self.b: [restricting.name]})

    def test_changing_the_warehouse_parent_removes_the_old_one(self):
        user = utils.make_user()
        branch = self.make_branch([user])
        new_parent = utils.make_warehouse(self.company, is_group=1)
        utils.make_warehouse(self.company, parent=new_parent)

        branch.custom_cen_warehouse_parent = new_parent
        branch.custom_cen_default_warehouse = None
        branch.save(ignore_permissions=True)

        self.assertEqual(self.warehouse_permissions(user), {new_parent: [branch.name]})

    # Saving rules

    def test_warehouse_outside_the_parent_is_rejected(self):
        user = utils.make_user()
        self.assert_rejected(
            "is not under this branch's Warehouse Parent",
            lambda: self.make_branch([user], restrictions=[(user, self.outside)]),
        )

    def test_same_warehouse_twice_for_a_user_is_rejected(self):
        user = utils.make_user()
        self.assert_rejected(
            "is listed twice",
            lambda: self.make_branch([user], restrictions=[(user, self.b), (user, self.b)]),
        )

    def test_restrictions_need_a_warehouse_parent(self):
        user = utils.make_user()
        self.assert_rejected(
            "Set a Warehouse Parent",
            lambda: utils.make_branch(self.company, users=[user], **{FIELD: [{"user": user, "warehouse": self.b}]}),
        )

    def test_removing_a_user_drops_their_restrictions(self):
        leaving, staying = utils.make_user(), utils.make_user()
        branch = self.make_branch([leaving, staying], restrictions=[(leaving, self.b), (staying, self.d)])

        branch.set("custom_cen_branch_users", [{"user": staying}])
        branch.save(ignore_permissions=True)

        self.assertEqual([(row.user, row.warehouse) for row in branch.get(FIELD)], [(staying, self.d)])
        self.assertEqual(self.warehouse_permissions(leaving), {})

    # What the user works with after switching to the branch

    def test_restricted_user_scope_and_default_warehouse(self):
        user = utils.make_user()
        branch = self.make_branch([user], restrictions=[(user, self.b), (user, self.sub)])

        frappe.set_user(user)
        scope = switcher.set_active_branch(branch.name)["scope"]

        self.assertEqual(scope["cen_branch_warehouses"].split(","), sorted([self.b, self.d]))
        # The branch default (a) isn't allowed, so the first allowed one.
        self.assertEqual(scope["cen_branch_default_warehouse"], sorted([self.b, self.d])[0])
        self.assertEqual(frappe.defaults.get_user_default("cen_branch_default_warehouse", user), scope["cen_branch_default_warehouse"])

    def test_restricted_user_keeps_the_branch_default_when_allowed(self):
        user = utils.make_user()
        branch = self.make_branch([user], restrictions=[(user, self.a), (user, self.b)])

        self.assertEqual(get_user_default_warehouse(branch, user), self.a)

    def test_unrestricted_user_scope_is_unchanged(self):
        user = utils.make_user()
        branch = self.make_branch([user])

        frappe.set_user(user)
        scope = switcher.set_active_branch(branch.name)["scope"]

        self.assertEqual(scope["cen_branch_warehouses"].split(","), sorted([self.a, self.b, self.d]))
        self.assertEqual(scope["cen_branch_default_warehouse"], self.a)
        self.assertEqual(scope["cen_branch_warehouse"], self.parent)
