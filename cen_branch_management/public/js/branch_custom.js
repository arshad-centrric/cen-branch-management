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

    // Server-side: someone who may edit branches can lack read access to the tree itself.
    frappe.xcall("cen_branch_management.api.warehouse_access.get_tree_bounds", { doctype: config.doctype, name: parent }).then(bounds => {
        if (bounds && frm.doc[config.parent_field] === parent) {
            frm._cen_parent_bounds[config.parent_field] = { parent: parent, lft: bounds.lft, rgt: bounds.rgt };
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

        // Addresses of the branch's company that are free or already this branch's.
        // "Empty or this branch" is more than a plain filter can say, hence the
        // server-side query. The server re-checks the choice on save.
        frm.set_query("custom_cen_branch_address", function() {
            if (!frm.doc.custom_cen_default_company) {
                frm.scroll_to_field("custom_cen_default_company");
                frappe.show_alert({ message: __("Please set Company first."), indicator: "orange" });
            }

            return {
                query: "cen_branch_management.api.address.branch_address_query",
                filters: {
                    company: frm.doc.custom_cen_default_company || "",
                    branch: frm.is_new() ? (frm.doc.branch || "") : frm.doc.name
                }
            };
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
        if (frm.doc.custom_cen_branch_address) frm.set_value("custom_cen_branch_address", null);
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

// ---------------------------------------------------------------------------
// Warehouse access per user
//
// A branch user gets every warehouse under the Warehouse Parent unless they
// have rows in Restricted Warehouses (custom_cen_user_warehouses), in which
// case they get only those. Rows are edited through the "Warehouses" button on
// each Assigned Branch Users row. The server applies the same rules on save
// (overrides/branch_validation.py, api/warehouse_access.py).
// ---------------------------------------------------------------------------
const CEN_USER_WAREHOUSES_FIELD = "custom_cen_user_warehouses";
const CEN_ACCESS_ALL = "All warehouses";
const CEN_ACCESS_ONLY = "Only the selected warehouses";

function cen_restricted_warehouses(frm, user) {
    let names = (frm.doc[CEN_USER_WAREHOUSES_FIELD] || [])
        .filter(row => row.user === user && row.warehouse)
        .map(row => row.warehouse);
    return [...new Set(names)].sort();
}

// Same text the server writes on save (get_warehouse_access_summary).
function cen_warehouse_access_summary(frm, user) {
    let restricted = cen_restricted_warehouses(frm, user);
    if (!restricted.length) return "All warehouses";

    let text = "Only: " + restricted.join(", ");
    return text.length <= 140 ? text : text.slice(0, 137) + "...";
}

function cen_refresh_warehouse_access(frm) {
    (frm.doc.custom_cen_branch_users || []).forEach(row => {
        if (row.user) row.warehouse_access = cen_warehouse_access_summary(frm, row.user);
    });
    frm.refresh_field("custom_cen_branch_users");

    let field = frm.fields_dict.custom_cen_warehouse_access_html;
    if (!field) return;

    let parent = frm.doc.custom_cen_warehouse_parent;
    let esc = frappe.utils.escape_html;
    let html;
    if (!parent) {
        html = `<p class="text-muted">${__("Set a Warehouse Parent on the Details tab to manage warehouse access per user.")}</p>`;
    } else {
        let restricted_users = (frm.doc.custom_cen_branch_users || []).filter(row => row.user && cen_restricted_warehouses(frm, row.user).length);
        let lines = restricted_users.map(row => {
            let chips = cen_restricted_warehouses(frm, row.user)
                .map(name => `<span class="indicator-pill blue" style="margin: 2px 4px 2px 0;">${esc(name)}</span>`)
                .join("");
            return `<div style="padding: 6px 0; border-bottom: 1px solid var(--border-color);">
                <strong>${esc(row.full_name || row.user)}</strong> <span class="text-muted">${esc(row.user)}</span><br>${chips}
            </div>`;
        });
        html = `<p>${__("Users not listed here get every warehouse under {0}.", [`<strong>${esc(parent)}</strong>`])}</p>`
            + (lines.length ? lines.join("") : `<p class="text-muted">${__("No user is restricted on this branch.")}</p>`);
    }
    $(field.wrapper).html(`<div style="margin-bottom: 12px;">${html}</div>`);
}

// Users taken off Assigned Branch Users lose their rows (the server does the same on save).
function cen_prune_restrictions(frm) {
    let users = new Set((frm.doc.custom_cen_branch_users || []).map(row => row.user).filter(Boolean));
    let rows = frm.doc[CEN_USER_WAREHOUSES_FIELD] || [];
    let kept = rows.filter(row => users.has(row.user));
    if (kept.length !== rows.length) {
        frm.clear_table(CEN_USER_WAREHOUSES_FIELD);
        kept.forEach(row => frm.add_child(CEN_USER_WAREHOUSES_FIELD, { user: row.user, warehouse: row.warehouse }));
        frm.refresh_field(CEN_USER_WAREHOUSES_FIELD);
    }
}

function cen_open_warehouse_dialog(frm, branch_user_row) {
    let user = branch_user_row.user;
    let parent = frm.doc.custom_cen_warehouse_parent;
    if (!user) {
        frappe.msgprint(__("Pick the user on this row first."));
        return;
    }
    if (!parent) {
        frappe.msgprint(__("Set a Warehouse Parent on the Details tab first."));
        return;
    }

    frappe.xcall("cen_branch_management.api.warehouse_access.get_warehouses_under", { parent: parent }).then(warehouses => {
        warehouses = warehouses || [];
        if (!warehouses.length) {
            frappe.msgprint(__("There are no warehouses under {0} yet.", [parent]));
            return;
        }

        // Indent by depth under the Warehouse Parent so the tree reads naturally.
        let depth = {};
        warehouses.forEach(w => { depth[w.name] = w.parent_warehouse in depth ? depth[w.parent_warehouse] + 1 : 0; });
        let restricted = cen_restricted_warehouses(frm, user);
        let options = warehouses.map(w => ({
            value: w.name,
            label: "    ".repeat(depth[w.name]) + w.name + (w.is_group ? " " + __("(group: everything under it)") : ""),
            checked: restricted.includes(w.name)
        }));

        // Mirrors get_user_default_warehouse on the server.
        let default_for = selected => {
            let leaves = new Set();
            warehouses.filter(w => selected.includes(w.name)).forEach(sel => {
                warehouses.filter(w => !w.is_group && w.lft >= sel.lft && w.rgt <= sel.rgt).forEach(w => leaves.add(w.name));
            });
            let sorted = [...leaves].sort();
            let branch_default = frm.doc.custom_cen_default_warehouse;
            if (branch_default && leaves.has(branch_default)) return branch_default;
            return sorted[0] || null;
        };

        let dialog = new frappe.ui.Dialog({
            title: __("Warehouses for {0} on {1}", [branch_user_row.full_name || user, frm.doc.name || frm.doc.branch]),
            fields: [
                {
                    fieldname: "access",
                    fieldtype: "Select",
                    label: __("Access"),
                    options: [CEN_ACCESS_ALL, CEN_ACCESS_ONLY].join("\n"),
                    default: restricted.length ? CEN_ACCESS_ONLY : CEN_ACCESS_ALL,
                    description: __("All warehouses = every warehouse under {0}, as for any user without restrictions.", [parent]),
                    onchange: () => update_default_note()
                },
                {
                    fieldname: "warehouses",
                    fieldtype: "MultiCheck",
                    label: __("Warehouses"),
                    options: options,
                    sort_options: false,
                    columns: 1,
                    depends_on: `eval:doc.access=='${CEN_ACCESS_ONLY}'`
                },
                { fieldname: "default_note", fieldtype: "HTML" }
            ],
            primary_action_label: __("Apply"),
            primary_action: values => {
                let selected = values.access === CEN_ACCESS_ONLY ? dialog.fields_dict.warehouses.get_checked_options() : [];
                if (values.access === CEN_ACCESS_ONLY && !selected.length) {
                    frappe.msgprint(__("Tick at least one warehouse, or choose All warehouses."));
                    return;
                }

                let others = (frm.doc[CEN_USER_WAREHOUSES_FIELD] || []).filter(row => row.user !== user);
                frm.clear_table(CEN_USER_WAREHOUSES_FIELD);
                others.forEach(row => frm.add_child(CEN_USER_WAREHOUSES_FIELD, { user: row.user, warehouse: row.warehouse }));
                selected.forEach(name => frm.add_child(CEN_USER_WAREHOUSES_FIELD, { user: user, warehouse: name }));
                frm.refresh_field(CEN_USER_WAREHOUSES_FIELD);
                cen_refresh_warehouse_access(frm);
                frm.dirty();

                dialog.hide();
                frappe.show_alert({ message: __("Warehouse access updated for {0}. Save the branch to apply it.", [user]), indicator: "blue" });
            }
        });

        let update_default_note = () => {
            let access = dialog.get_value("access");
            let note;
            if (access === CEN_ACCESS_ALL) {
                note = __("Default warehouse: the branch's default ({0}).", [frm.doc.custom_cen_default_warehouse || __("none set")]);
            } else {
                let selected = dialog.fields_dict.warehouses.get_checked_options();
                let chosen = default_for(selected);
                let branch_default = frm.doc.custom_cen_default_warehouse;
                note = !chosen
                    ? __("Tick at least one warehouse.")
                    : chosen === branch_default
                        ? __("Default warehouse for this user: {0} (the branch default).", [chosen])
                        : __("Default warehouse for this user: {0} (the branch default isn't allowed, so the first allowed one).", [chosen]);
            }
            dialog.fields_dict.default_note.$wrapper.html(`<p class="text-muted small">${frappe.utils.escape_html(note)}</p>`);
        };

        dialog.fields_dict.warehouses.$wrapper.on("change", "input[type=checkbox]", update_default_note);
        dialog.show();
        update_default_note();
    });
}

frappe.ui.form.on("Branch", {
    setup: function(frm) {
        // Only the branch's own users, and only warehouses under its Warehouse Parent.
        frm.set_query("user", CEN_USER_WAREHOUSES_FIELD, function(doc) {
            let users = (doc.custom_cen_branch_users || []).map(row => row.user).filter(Boolean);
            return { filters: { name: ["in", users.length ? users : [""]] } };
        });
        frm.set_query("warehouse", CEN_USER_WAREHOUSES_FIELD, function() {
            let config = CEN_BRANCH_TREE_DEFAULTS.find(c => c.parent_field === "custom_cen_warehouse_parent");
            let filters = cen_branch_default_query(frm, config).filters.filter(f => f[1] !== "is_group");
            return { filters: filters };
        });
    },
    refresh: function(frm) {
        cen_refresh_warehouse_access(frm);
    },
    custom_cen_warehouse_parent: function(frm) {
        cen_refresh_warehouse_access(frm);
    },
    custom_cen_branch_users_remove: function(frm) {
        cen_prune_restrictions(frm);
        cen_refresh_warehouse_access(frm);
    },
    custom_cen_user_warehouses_remove: function(frm) {
        cen_refresh_warehouse_access(frm);
    }
});

frappe.ui.form.on("Branch User", {
    set_warehouses: function(frm, cdt, cdn) {
        cen_open_warehouse_dialog(frm, locals[cdt][cdn]);
    },
    user: function(frm) {
        cen_refresh_warehouse_access(frm);
    }
});

frappe.ui.form.on("Branch User Warehouse", {
    user: function(frm) {
        cen_refresh_warehouse_access(frm);
    },
    warehouse: function(frm) {
        cen_refresh_warehouse_access(frm);
    }
});
