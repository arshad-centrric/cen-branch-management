frappe.ui.form.on("User", {
    setup: function(frm) {
        // Only branches this user is assigned to. The server checks the choice
        // again on save (overrides/user_default_branch.py).
        frm.set_query("custom_cen_default_branch", function() {
            return {
                query: "cen_branch_management.api.user.default_branch_query",
                filters: { user: frm.is_new() ? "" : frm.doc.name }
            };
        });
    }
});
