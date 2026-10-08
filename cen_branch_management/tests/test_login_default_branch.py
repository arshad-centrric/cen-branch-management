from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from cen_branch_management.api import switcher
from cen_branch_management.api.user import default_branch_query
from cen_branch_management.tests import utils

FIELD = "custom_cen_default_branch"


class TestLoginDefaultBranch(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        companies = utils.get_companies()
        cls.company = companies[0]
        cls.other_company = companies[1] if len(companies) > 1 else None

    def tearDown(self):
        frappe.set_user("Administrator")

    def default_branch_of(self, user):
        return frappe.db.get_value("User", user, FIELD)

    def set_default_branch(self, user, branch):
        """As an admin would on the User form (runs the User validation)."""
        doc = frappe.get_doc("User", user)
        doc.set(FIELD, branch)
        doc.save(ignore_permissions=True)

    def force_default_branch(self, user, branch):
        """Straight into the database: a value the app would not have allowed."""
        frappe.db.set_value("User", user, FIELD, branch)

    def set_users(self, branch, users=(), default_users=()):
        rows = [{"user": user} for user in users] + [{"user": user, "is_default": 1} for user in default_users]
        branch.set("custom_cen_branch_users", rows)
        branch.save(ignore_permissions=True)

    def login(self, user):
        """What Frappe does at login: the hook runs while the session still
        belongs to someone else (Guest on a real login, Administrator here)."""
        switcher.initialize_session_branch(frappe._dict(user=user))

    def active(self, user, key="branch"):
        return frappe.defaults.get_user_default(key, user)

    # Field validation

    def test_default_branch_must_be_one_the_user_is_assigned_to(self):
        user = utils.make_user()
        branch = utils.make_branch(self.company)

        with self.assertRaises(frappe.ValidationError) as raised:
            self.set_default_branch(user, branch.name)
        self.assertIn("is not assigned to branch", str(raised.exception))

    def test_default_branch_of_an_assigned_user_is_accepted(self):
        user = utils.make_user()
        branch = utils.make_branch(self.company, users=[user])

        self.set_default_branch(user, branch.name)

        self.assertEqual(self.default_branch_of(user), branch.name)

    def test_stale_default_branch_does_not_block_other_user_edits(self):
        user = utils.make_user()
        branch = utils.make_branch(self.company)
        self.force_default_branch(user, branch.name)

        doc = frappe.get_doc("User", user)
        doc.first_name = "Renamed"
        doc.save(ignore_permissions=True)

        self.assertEqual(frappe.db.get_value("User", user, "first_name"), "Renamed")

    def test_query_lists_only_the_users_branches(self):
        user = utils.make_user()
        assigned = utils.make_branch(self.company, users=[user])
        not_assigned = utils.make_branch(self.company)

        found = {row[0] for row in default_branch_query("Branch", "", "name", 0, 100, {"user": user})}

        self.assertIn(assigned.name, found)
        self.assertNotIn(not_assigned.name, found)

    # Landing at login

    def test_login_lands_on_the_default_branch_with_its_full_scope(self):
        user = utils.make_user()
        parent = utils.make_warehouse(self.company, is_group=1)
        warehouse = utils.make_warehouse(self.company, parent=parent)
        branch = utils.make_branch(
            self.company,
            users=[user],
            custom_cen_warehouse_parent=parent,
            custom_cen_default_warehouse=warehouse,
            custom_cen_branch_address=utils.make_address(self.company),
        )
        self.set_default_branch(user, branch.name)
        administrator_branch = self.active("Administrator")

        self.login(user)

        # Exactly what picking the branch in the switcher would have set.
        expected = switcher.get_branch_scope(branch.name)
        self.assertEqual(expected["branch"], branch.name)
        self.assertEqual(expected["cen_branch_default_warehouse"], warehouse)
        for key in switcher.BRANCH_DEFAULT_KEYS:
            self.assertEqual(self.active(user, key), expected[key], key)

        # Written for the user logging in, not for whoever holds the session.
        self.assertEqual(self.active("Administrator"), administrator_branch)

    def test_login_without_a_default_branch_lands_on_all_branches(self):
        user = utils.make_user()
        branch = utils.make_branch(self.company, users=[user])

        # The branch used in the previous session is not remembered.
        frappe.set_user(user)
        switcher.set_active_branch(branch.name)
        frappe.set_user("Administrator")
        self.assertEqual(self.active(user), branch.name)

        self.login(user)

        for key in switcher.BRANCH_DEFAULT_KEYS:
            self.assertIsNone(self.active(user, key), key)

    def test_login_ignores_a_default_branch_the_user_was_removed_from(self):
        user = utils.make_user()
        branch = utils.make_branch(self.company)
        self.force_default_branch(user, branch.name)

        self.login(user)

        self.assertIsNone(self.active(user))

    def test_login_ignores_a_default_branch_that_no_longer_exists(self):
        user = utils.make_user()
        self.force_default_branch(user, "_Test CBM Branch That Was Deleted")

        self.login(user)

        self.assertIsNone(self.active(user))

    def test_login_can_pin_a_user_to_a_branch_of_another_company(self):
        if not self.other_company:
            self.skipTest("Needs a second company on the site")

        user = utils.make_user()
        utils.make_branch(self.company, users=[user])
        pinned = utils.make_branch(self.other_company, users=[user])
        self.set_default_branch(user, pinned.name)

        self.login(user)

        self.assertEqual(self.active(user), pinned.name)
        self.assertEqual(self.active(user, "cen_branch_company"), self.other_company)

    def test_login_never_fails_when_the_branch_cannot_be_resolved(self):
        user = utils.make_user()
        branch = utils.make_branch(self.company, users=[user])
        frappe.set_user(user)
        switcher.set_active_branch(branch.name)
        frappe.set_user("Administrator")

        with patch.object(switcher, "resolve_login_branch", side_effect=RuntimeError("boom")):
            self.login(user)

        self.assertIsNone(self.active(user))

    def test_login_never_fails_when_nothing_can_be_written(self):
        user = utils.make_user()

        with patch.object(switcher, "_write_user_defaults", side_effect=RuntimeError("boom")):
            self.login(user)

    # Clean-up

    def test_removing_a_user_from_the_branch_clears_a_matching_default(self):
        leaving, staying = utils.make_user(), utils.make_user()
        branch = utils.make_branch(self.company, users=[leaving, staying])
        self.set_default_branch(leaving, branch.name)
        self.set_default_branch(staying, branch.name)

        self.set_users(branch, users=[staying])

        self.assertIsNone(self.default_branch_of(leaving))
        self.assertEqual(self.default_branch_of(staying), branch.name)

    def test_removing_a_user_keeps_a_default_that_points_elsewhere(self):
        user = utils.make_user()
        home = utils.make_branch(self.company, users=[user])
        other = utils.make_branch(self.company, users=[user])
        self.set_default_branch(user, home.name)

        self.set_users(other, users=[])

        self.assertEqual(self.default_branch_of(user), home.name)

    def test_deleting_a_branch_clears_the_defaults_pointing_at_it(self):
        user, unaffected = utils.make_user(), utils.make_user()
        doomed = utils.make_branch(self.company)
        kept = utils.make_branch(self.company, users=[unaffected])
        self.force_default_branch(user, doomed.name)
        self.set_default_branch(unaffected, kept.name)

        frappe.delete_doc("Branch", doomed.name, ignore_permissions=True)

        self.assertIsNone(self.default_branch_of(user))
        self.assertEqual(self.default_branch_of(unaffected), kept.name)

    # Auto-fill from the "Is Default" flag

    def test_default_user_gets_the_branch_when_they_have_none(self):
        user = utils.make_user()

        branch = utils.make_branch(self.company, default_users=[user])

        self.assertEqual(self.default_branch_of(user), branch.name)

    def test_flagging_an_existing_user_row_fills_it_too(self):
        user = utils.make_user()
        branch = utils.make_branch(self.company, users=[user])
        self.assertIsNone(self.default_branch_of(user))

        self.set_users(branch, default_users=[user])

        self.assertEqual(self.default_branch_of(user), branch.name)

    def test_default_user_keeps_a_default_branch_they_already_have(self):
        user = utils.make_user()
        existing = utils.make_branch(self.company, users=[user])
        self.set_default_branch(user, existing.name)

        utils.make_branch(self.other_company or self.company, default_users=[user])

        self.assertEqual(self.default_branch_of(user), existing.name)

    def test_saving_the_branch_again_does_not_undo_an_admin_clearing_it(self):
        user = utils.make_user()
        branch = utils.make_branch(self.company, default_users=[user])
        self.set_default_branch(user, None)

        branch.reload()
        branch.save(ignore_permissions=True)
        branch.save(ignore_permissions=True)

        self.assertIsNone(self.default_branch_of(user))

    def test_disabled_default_user_is_not_filled(self):
        user = utils.make_user()
        frappe.db.set_value("User", user, "enabled", 0)

        utils.make_branch(self.company, default_users=[user])

        self.assertIsNone(self.default_branch_of(user))
