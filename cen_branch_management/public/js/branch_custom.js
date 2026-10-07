// The branch's default warehouse / cost center must be a non-group record of the
// branch's company, inside the matching parent when one is set. The server
// enforces this (overrides/branch_validation.py); the queries below only keep
// the dropdowns from offering choices that would be rejected on save.
const CEN_BRANCH_TREE_DEFAULTS = [
    { doctype: "Warehouse", parent_field: "custom_cen_warehouse_parent", default_field: "custom_cen_default_warehouse" },
    { doctype: "Cost Center", parent_field: "custom_cen_cost_center_parent", default_field: "custom_cen_default_cost_center" }
];

// Descendants are matched by nested-set bounds, which the link query can't look
// up by itself, so the parent's lft/rgt are fetched once and kept on the form.
function cen_load_parent_bounds(frm, config) {
    frm._cen_parent_bounds = frm._cen_parent_bounds || {};
    let parent = frm.doc[config.parent_field];

    if (!parent) {
        delete frm._cen_parent_bounds[config.parent_field];
        return;
    }

    frappe.db.get_value(config.doctype, parent, ["lft", "rgt"]).then(r => {
        if (r && r.message && frm.doc[config.parent_field] === parent) {
            frm._cen_parent_bounds[config.parent_field] = { parent: parent, lft: r.message.lft, rgt: r.message.rgt };
        }
    });
}

function cen_branch_default_query(frm, config) {
    let filters = [
        [config.doctype, "is_group", "=", 0],
        [config.doctype, "company", "=", frm.doc.custom_cen_default_company || ""]
    ];

    let parent = frm.doc[config.parent_field];
    let bounds = (frm._cen_parent_bounds || {})[config.parent_field];
    if (parent && bounds && bounds.parent === parent) {
        filters.push([config.doctype, "lft", ">=", bounds.lft]);
        filters.push([config.doctype, "rgt", "<=", bounds.rgt]);
    }

    return { filters: filters };
}

// A default picked under the previous parent may sit outside the new one.
function cen_parent_changed(frm, parent_field) {
    let config = CEN_BRANCH_TREE_DEFAULTS.find(c => c.parent_field === parent_field);
    if (frm.doc[config.default_field]) frm.set_value(config.default_field, null);
    cen_load_parent_bounds(frm, config);
}

frappe.ui.form.on("Branch", {
    setup: function(frm) {
        CEN_BRANCH_TREE_DEFAULTS.forEach(config => {
            frm.set_query(config.default_field, function() {
                return cen_branch_default_query(frm, config);
            });
        });

        frm.set_query("item_group", "custom_cen_allowed_item_groups", function(doc, cdt, cdn) {
            let already_added = (doc.custom_cen_allowed_item_groups || [])
                .filter(row => row.name !== cdn && row.item_group)
                .map(row => row.item_group);

            return already_added.length ? { filters: { name: ["not in", already_added] } } : {};
        });

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
    custom_cen_default_company: function(frm) {
        // A default from the previous company can never be valid for the new one.
        CEN_BRANCH_TREE_DEFAULTS.forEach(config => {
            if (frm.doc[config.default_field]) frm.set_value(config.default_field, null);
        });
    },
    custom_cen_warehouse_parent: function(frm) {
        cen_parent_changed(frm, "custom_cen_warehouse_parent");
    },
    custom_cen_cost_center_parent: function(frm) {
        cen_parent_changed(frm, "custom_cen_cost_center_parent");
    },
    refresh: function(frm) {
        CEN_BRANCH_TREE_DEFAULTS.forEach(config => cen_load_parent_bounds(frm, config));
        frm.trigger("update_user_count");
        // The server only accepts this from someone who can edit the branch
        // (saving it runs the same sync), so don't offer it to anyone else.
        if (!frm.is_new() && frm.perm[0] && frm.perm[0].write) {
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
        }
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
