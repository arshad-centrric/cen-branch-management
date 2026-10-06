import frappe
from frappe.tests import IntegrationTestCase

from cen_branch_management.api import permissions
from cen_branch_management.tests import utils


class TestBranchPermissionSync(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = utils.get_companies()[0]

    def tearDown(self):
        frappe.set_user("Administrator")

    def item_groups_of(self, user):
        return utils.managed_permissions(user, "Item Group")

    def set_item_groups(self, branch, groups):
        branch.set("custom_cen_allowed_item_groups", [{"item_group": group} for group in groups])
        branch.save(ignore_permissions=True)

    def set_users(self, branch, users):
        branch.set("custom_cen_branch_users", [{"user": user} for user in users])
        branch.save(ignore_permissions=True)

    def make_legacy_cost_center_permission(self, user, branches):
        """What branch setup used to create before it stopped syncing cost centers."""
        doc = frappe.new_doc("User Permission")
        doc.user = user
        doc.allow = "Cost Center"
        doc.for_value = utils.make_cost_center(self.company)
        doc.apply_to_all_doctypes = 1
        doc.custom_cen_from_branch_setup = 1
        for branch in branches:
            doc.append("custom_cen_source_branch", {"branch": branch.name})
        doc.insert(ignore_permissions=True)
        return doc.name

    # Item Group permissions

    def test_branch_users_get_a_permission_per_allowed_item_group(self):
        first_user, second_user = utils.make_user(), utils.make_user()
        group_a, group_b = utils.make_item_group(), utils.make_item_group()

        branch = utils.make_branch(self.company, users=[first_user, second_user], item_groups=[group_a, group_b])

        for user in (first_user, second_user):
            self.assertEqual(self.item_groups_of(user), {group_a: [branch.name], group_b: [branch.name]})

    def test_only_listed_groups_are_granted_not_children_or_root(self):
        user = utils.make_user()
        parent_group = utils.make_item_group(is_group=1)
        utils.make_item_group(parent=parent_group)

        utils.make_branch(self.company, users=[user], item_groups=[parent_group])

        self.assertEqual(list(self.item_groups_of(user)), [parent_group])
        self.assertNotIn(utils.get_root_item_group(), self.item_groups_of(user))

    def test_group_removed_from_branch_removes_the_permission(self):
        user = utils.make_user()
        kept, removed = utils.make_item_group(), utils.make_item_group()
        branch = utils.make_branch(self.company, users=[user], item_groups=[kept, removed])

        self.set_item_groups(branch, [kept])

        self.assertEqual(self.item_groups_of(user), {kept: [branch.name]})

    def test_user_removed_from_branch_loses_the_permission(self):
        staying, leaving = utils.make_user(), utils.make_user()
        group = utils.make_item_group()
        branch = utils.make_branch(self.company, users=[staying, leaving], item_groups=[group])

        self.set_users(branch, [staying])

        self.assertEqual(self.item_groups_of(leaving), {})
        self.assertEqual(self.item_groups_of(staying), {group: [branch.name]})

    def test_permission_shared_by_two_branches_survives_until_both_drop_it(self):
        user = utils.make_user()
        shared, only_first = utils.make_item_group(), utils.make_item_group()
        first = utils.make_branch(self.company, users=[user], item_groups=[shared, only_first])
        second = utils.make_branch(self.company, users=[user], item_groups=[shared])

        self.assertEqual(self.item_groups_of(user)[shared], sorted([first.name, second.name]))

        # Group taken off the first branch: still granted by the second.
        self.set_item_groups(first, [only_first])
        self.assertEqual(self.item_groups_of(user), {shared: [second.name], only_first: [first.name]})

        # User taken off the second branch: nobody grants it any more.
        self.set_users(second, [])
        self.assertEqual(self.item_groups_of(user), {only_first: [first.name]})

    def test_disabled_user_loses_permissions_and_gets_them_back(self):
        user = utils.make_user()
        group = utils.make_item_group()
        branch = utils.make_branch(self.company, users=[user], item_groups=[group])

        user_doc = frappe.get_doc("User", user)
        user_doc.enabled = 0
        user_doc.save(ignore_permissions=True)

        self.assertEqual(self.item_groups_of(user), {})
        self.assertEqual(utils.managed_permissions(user, "Branch"), {})

        user_doc.enabled = 1
        user_doc.save(ignore_permissions=True)

        self.assertEqual(self.item_groups_of(user), {group: [branch.name]})
        self.assertEqual(utils.managed_permissions(user, "Branch"), {branch.name: [branch.name]})

    # Sync endpoint

    def test_sync_endpoint_rejects_users_who_cannot_edit_the_branch(self):
        branch = utils.make_branch(self.company)
        outsider = utils.make_user()

        frappe.set_user(outsider)
        with self.assertRaises(frappe.PermissionError):
            permissions.sync_branch_permissions(branch.name)

    def test_sync_endpoint_works_for_users_who_can_edit_the_branch(self):
        user = utils.make_user()
        group = utils.make_item_group()
        branch = utils.make_branch(self.company, users=[user], item_groups=[group])

        # Same plain delete core's "Clear User Permissions" does: the permissions
        # go, their source-branch rows stay behind. The sync has to cope.
        frappe.db.delete("User Permission", {"user": user})
        self.assertEqual(self.item_groups_of(user), {})

        permissions.sync_branch_permissions(branch.name)

        self.assertEqual(self.item_groups_of(user), {group: [branch.name]})

    # Cleanup scope

    def test_cleanup_only_touches_permissions_of_the_synced_branch(self):
        user = utils.make_user()
        synced = utils.make_branch(self.company, users=[user])
        other = utils.make_branch(self.company, users=[user])

        of_synced = self.make_legacy_cost_center_permission(user, [synced])
        of_other = self.make_legacy_cost_center_permission(user, [other])
        of_both = self.make_legacy_cost_center_permission(user, [synced, other])

        synced.save(ignore_permissions=True)

        self.assertFalse(frappe.db.exists("User Permission", of_synced))
        self.assertTrue(frappe.db.exists("User Permission", of_other))
        self.assertEqual(
            frappe.get_all("User Permission Source Branch", filters={"parent": of_both}, pluck="branch"),
            [other.name],
        )

    def test_other_branch_permissions_of_a_removed_user_are_kept(self):
        user = utils.make_user()
        group = utils.make_item_group()
        leaving = utils.make_branch(self.company, users=[user], item_groups=[group])
        staying = utils.make_branch(self.company, users=[user], item_groups=[group])

        self.set_users(leaving, [])

        self.assertEqual(self.item_groups_of(user), {group: [staying.name]})
        self.assertEqual(utils.managed_permissions(user, "Branch"), {staying.name: [staying.name]})
