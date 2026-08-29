frappe.ui.form.on("Branch", {
    setup: function(frm) {
        frm.set_query("custom_cen_cost_center_parent", function() {
            return {
                filters: {
                    company: frm.doc.custom_cen_default_company,
                    is_group: 1
                }
            };
        });

        frm.set_query("custom_cen_warehouse_parent", function() {
            return {
                filters: {
                    company: frm.doc.custom_cen_default_company,
                    is_group: 1
                }
            };
        });

        frm.set_query("custom_cen_default_selling_price_list", function() {
            return {
                filters: {
                    selling: 1
                }
            };
        });

        frm.set_query("custom_cen_default_buying_price_list", function() {
            return {
                filters: {
                    buying: 1
                }
            };
        });

        frm.set_query("price_list", "custom_cen_allowed_selling_price_lists", function() {
            return {
                filters: {
                    selling: 1
                }
            };
        });

        frm.set_query("price_list", "custom_cen_allowed_buying_price_lists", function() {
            return {
                filters: {
                    buying: 1
                }
            };
        });
    },
    refresh: function(frm) {
        frm.trigger("update_user_count");
        frm.add_custom_button('Sync User Permissions', function() {
            frappe.show_alert({message: "Syncing Permissions...", indicator: 'blue'});
            frappe.call({
                method: "cen_branch_management.api.permissions.sync_branch_permissions",
                args: { branch_name: frm.doc.name },
                callback: function(r) {
                    if (!r.exc) {
                        frappe.msgprint("User Permissions have been successfully synced for this branch.");
                    }
                }
            });
        });
    },
    validate: function(frm) {
        if (frm.doc.custom_cen_default_selling_price_list) {
            let exists = (frm.doc.custom_cen_allowed_selling_price_lists || []).some(row => row.price_list === frm.doc.custom_cen_default_selling_price_list);
            if (!exists) {
                let row = frm.add_child("custom_cen_allowed_selling_price_lists");
                row.price_list = frm.doc.custom_cen_default_selling_price_list;
            }
        }
        if (frm.doc.custom_cen_default_buying_price_list) {
            let exists = (frm.doc.custom_cen_allowed_buying_price_lists || []).some(row => row.price_list === frm.doc.custom_cen_default_buying_price_list);
            if (!exists) {
                let row = frm.add_child("custom_cen_allowed_buying_price_lists");
                row.price_list = frm.doc.custom_cen_default_buying_price_list;
            }
        }
    },
    update_user_count: function(frm) {
        let count = frm.doc.custom_cen_branch_users ? frm.doc.custom_cen_branch_users.length : 0;
        $(frm.fields_dict.custom_cen_total_users_html.wrapper).html(
            `<div style="padding: 15px 20px; background-color: #f8f9fa; border-left: 4px solid #173b5c; border-radius: 4px; font-size: 16px; display: flex; align-items: center;">
                <strong style="margin-right: 15px;">Total Branch Users</strong>
                <span class="badge badge-primary" style="font-size: 16px; padding: 6px 12px;">${count}</span>
            </div>`
        );
    },
    custom_cen_branch_users_add: function(frm) {
        frm.trigger("update_user_count");
    },
    custom_cen_branch_users_remove: function(frm) {
        frm.trigger("update_user_count");
    }
});
