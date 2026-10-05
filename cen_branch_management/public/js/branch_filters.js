// Shared namespace: also used by branch_switcher.js for the soft-refresh after
// a branch switch (no full page reload -- see branch_switcher.js).
window.cen_branch_management = window.cen_branch_management || {};

Object.assign(window.cen_branch_management, {

    branch_doctypes: [
        "Lead",
        "Opportunity",
        "Quotation",
        "Sales Order",
        "Sales Invoice",
        "Purchase Order",
        "Purchase Invoice",
        "Delivery Note",
        "Purchase Receipt",
        "Journal Entry",
        "Payment Entry"
    ],

    // branch name -> scope dict (same shape the server returns from
    // set_active_branch/get_branch_scope). Populated whenever a switch
    // succeeds or a document's own branch is resolved, so re-visiting a
    // previously-seen branch (via the switcher or a doc's branch field)
    // never needs a second server round trip.
    branch_scope_cache: {},

    // Reads the active branch straight out of frappe.boot.user.defaults, bypassing
    // frappe.defaults.get_user_default("branch"). That helper additionally checks
    // the value against the user's cached User Permission list for "Branch" (since
    // "branch" unscrubs to that real doctype name) -- a check meant for link-field
    // default suggestions, not for us. That cache is captured once at page boot and
    // never refreshed by our soft (no-reload) branch switch, so on a long-lived tab
    // it can reject a just-switched-to branch even though the server-side switch
    // (already gated by Branch User membership, server-side) succeeded -- which is
    // exactly why a hard refresh "fixes" it: that's the only thing that re-fetches
    // the permission cache. Reading the raw default here sidesteps that entirely.
    get_active_branch: function() {
        let defaults = frappe.boot && frappe.boot.user && frappe.boot.user.defaults;
        let value = defaults && defaults["branch"];
        if (Array.isArray(value)) value = value[0];
        return value || null;
    },

    // List-view filter fields this app owns. Shared by compute_list_view_branch_filters
    // (to strip stale entries from the plain filters array) and by the soft-refresh in
    // branch_switcher.js (to actually remove them from an already-rendered FilterArea --
    // FilterArea.set() only adds/skips-duplicates, it never removes a filter that's no
    // longer wanted, so switching branches repeatedly would otherwise stack up multiple
    // "Branch = X" chips instead of replacing the previous one).
    MANAGED_LIST_FILTER_FIELDS: ["branch", "custom_cen_branch", "company", "cost_center"],

    // The session's active-branch scope, packaged from frappe.boot.user.defaults
    // (via frappe.defaults.get_user_default, which never calls the server) into
    // the same shape the server returns. Returns null when there's no active
    // branch (i.e. "All Branches"), matching the old code's early-return checks.
    get_session_scope: function() {
        let active_branch = cen_branch_management.get_active_branch();
        if (!active_branch || active_branch === "All Branches") return null;

        return {
            branch: active_branch,
            custom_cen_branch: frappe.defaults.get_user_default("custom_cen_branch"),
            cen_branch_company: frappe.defaults.get_user_default("cen_branch_company"),
            cen_branch_warehouse: frappe.defaults.get_user_default("cen_branch_warehouse"),
            cen_branch_warehouses: frappe.defaults.get_user_default("cen_branch_warehouses"),
            cen_branch_cost_center: frappe.defaults.get_user_default("cen_branch_cost_center"),
            cen_branch_cost_centers: frappe.defaults.get_user_default("cen_branch_cost_centers"),
            cen_branch_selling_price_lists: frappe.defaults.get_user_default("cen_branch_selling_price_lists"),
            cen_branch_buying_price_lists: frappe.defaults.get_user_default("cen_branch_buying_price_lists"),
            cen_branch_default_selling_price_list: frappe.defaults.get_user_default("cen_branch_default_selling_price_list"),
            cen_branch_default_buying_price_list: frappe.defaults.get_user_default("cen_branch_default_buying_price_list")
        };
    },

    // The doc's own branch/custom_cen_branch field, if set, wins over the
    // session's active branch -- this is what lets a document set to "Kochi"
    // scope its own Warehouse/Cost Center/Price List to Kochi even while the
    // session itself is on "All Branches" (or on a different branch).
    resolve_scope_for_form: function(frm) {
        let doc_branch = frm.doc.custom_cen_branch || frm.doc.branch;

        // A document's own branch only overrides the session's active branch when
        // it reflects a deliberate choice: an existing/draft doc that already had
        // it set (loaded from the DB), or a new doc whose branch the user actually
        // edited themselves. A brand-new doc whose branch was only ever auto-filled
        // by us to match the session must keep tracking the session -- otherwise,
        // once auto-filled, switching branches later while the form is still open
        // would have no visible effect (the doc's own value would always "win").
        let doc_branch_is_authoritative = !frm.is_new() || frm._cen_branch_user_set;

        if (doc_branch_is_authoritative && doc_branch && doc_branch !== "All Branches") {
            let cached = cen_branch_management.branch_scope_cache[doc_branch];
            if (cached) return Promise.resolve(cached);

            return frappe.call({
                method: "cen_branch_management.api.switcher.get_branch_scope",
                args: { branch_name: doc_branch }
            }).then(r => {
                let scope = (r && r.message) || null;
                if (scope && scope.branch) {
                    cen_branch_management.branch_scope_cache[doc_branch] = scope;
                }
                return scope;
            }).catch(() => cen_branch_management.get_session_scope());
        }

        return Promise.resolve(cen_branch_management.get_session_scope());
    },

    // Resolves the effective scope for this form and applies it, guarded by a
    // per-form monotonic token so a slower, older resolve (e.g. from onload)
    // can't clobber a newer one (e.g. the user changing the branch field a
    // moment later, before the first request returns).
    apply_branch_scoping: function(frm) {
        frm._cen_scope_token = (frm._cen_scope_token || 0) + 1;
        let token = frm._cen_scope_token;

        cen_branch_management.resolve_scope_for_form(frm).then(scope => {
            if (token !== frm._cen_scope_token) return;
            cen_branch_management.apply_sandbox_queries(frm, scope);
        });
    },

    // Applies the given scope to a form: auto-set (new/draft docs only, never
    // a submitted doc) + link-field query restrictions. `scope` is whichever
    // one resolve_scope_for_form() decided applies -- the doc's own branch, or
    // the session's active branch.
    apply_sandbox_queries: function(frm, scope) {
        if (!scope || !scope.branch) return;

        let active_branch = scope.branch;
        let branch_company = scope.cen_branch_company;
        let branch_selling_pl = scope.cen_branch_selling_price_lists;
        let branch_buying_pl = scope.cen_branch_buying_price_lists;
        let branch_default_selling_pl = scope.cen_branch_default_selling_price_list;
        let branch_default_buying_pl = scope.cen_branch_default_buying_price_list;
        let branch_warehouses = scope.cen_branch_warehouses;
        let branch_cost_centers = scope.cen_branch_cost_centers;

        // Auto-Setters (only for new/draft documents; a submitted doc is never touched)
        if (frm.is_new() || frm.doc.docstatus === 0) {
            if (frm.is_new() && frm.fields_dict.company && branch_company && frm.doc.company !== branch_company) {
                frm.set_value("company", branch_company);
            }
            if (frm.fields_dict.custom_cen_branch && frm.doc.custom_cen_branch !== active_branch) {
                frm._cen_branch_programmatic_set = true;
                frm.set_value("custom_cen_branch", active_branch);
            }
            if (frm.fields_dict.branch && frm.doc.branch !== active_branch) {
                frm._cen_branch_programmatic_set = true;
                frm.set_value("branch", active_branch);
            }

            // Auto-Setter for Price Lists (Overpowers native Frappe/customer/supplier defaults)
            if (frm.is_new() && frm.fields_dict.selling_price_list && branch_default_selling_pl && frm.doc.selling_price_list !== branch_default_selling_pl) {
                frm.set_value("selling_price_list", branch_default_selling_pl);
            }
            if (frm.is_new() && frm.fields_dict.buying_price_list && branch_default_buying_pl && frm.doc.buying_price_list !== branch_default_buying_pl) {
                frm.set_value("buying_price_list", branch_default_buying_pl);
            }

            // Restrict Selling Price Lists (fall back to branch default when disallowed)
            if (frm.fields_dict.selling_price_list && branch_selling_pl) {
                let allowed_selling_pl = branch_selling_pl.split(",");
                if (frm.doc.selling_price_list && !allowed_selling_pl.includes(frm.doc.selling_price_list)) {
                    frm.set_value("selling_price_list", branch_default_selling_pl || null);
                }
            }

            // Restrict Buying Price Lists (fall back to branch default when disallowed)
            if (frm.fields_dict.buying_price_list && branch_buying_pl) {
                let allowed_buying_pl = branch_buying_pl.split(",");
                if (frm.doc.buying_price_list && !allowed_buying_pl.includes(frm.doc.buying_price_list)) {
                    frm.set_value("buying_price_list", branch_default_buying_pl || null);
                }
            }

            // Custom Selling Price List Auto-Clear
            if (frm.fields_dict.custom_selling_price_list && branch_selling_pl) {
                let allowed_selling_pl = branch_selling_pl.split(",");
                if (frm.doc.custom_selling_price_list && !allowed_selling_pl.includes(frm.doc.custom_selling_price_list)) {
                    frm.set_value("custom_selling_price_list", null);
                }
            }
        }

        // Restrict Company
        if (frm.fields_dict.company && branch_company) {
            frm.set_query("company", function() {
                return { filters: { "name": branch_company } };
            });
        }

        // Restrict Branch
        if (frm.fields_dict.branch) {
            frm.set_query("branch", function() {
                return { filters: { "name": active_branch } };
            });
        }
        if (frm.fields_dict.custom_cen_branch) {
            frm.set_query("custom_cen_branch", function() {
                return { filters: { "name": active_branch } };
            });
        }

        // Restrict Selling Price Lists
        if (frm.fields_dict.selling_price_list && branch_selling_pl) {
            let allowed_selling_pl = branch_selling_pl.split(",");
            frm.set_query("selling_price_list", function() {
                return { filters: { "name": ["in", allowed_selling_pl] } };
            });
        }

        // Restrict Buying Price Lists
        if (frm.fields_dict.buying_price_list && branch_buying_pl) {
            let allowed_buying_pl = branch_buying_pl.split(",");
            frm.set_query("buying_price_list", function() {
                return { filters: { "name": ["in", allowed_buying_pl] } };
            });
        }

        // Restrict Parent Warehouse
        if (branch_warehouses && frm.fields_dict.set_warehouse) {
            let allowed_warehouses = branch_warehouses.split(",");
            frm.set_query("set_warehouse", function() {
                return { filters: { "name": ["in", allowed_warehouses] } };
            });
        }

        // Parent Cost Center Override
        if (frm.fields_dict.cost_center && branch_cost_centers) {
            let allowed_cost_centers = branch_cost_centers.split(",");
            frm.set_query("cost_center", function() {
                return { filters: { "name": ["in", allowed_cost_centers] } };
            });
        }

        // Custom Delivery Store (Child Table)
        if (frm.fields_dict.custom_location_details && branch_warehouses) {
            let allowed_warehouses = branch_warehouses.split(",");
            frm.set_query("custom_delivery_store", "custom_location_details", function() {
                return { filters: { "name": ["in", allowed_warehouses] } };
            });
        }

        // Custom Delivery Store (Parent)
        if (frm.fields_dict.custom_delivery_store && branch_warehouses) {
            let allowed_warehouses = branch_warehouses.split(",");
            frm.set_query("custom_delivery_store", function() {
                return { filters: { "name": ["in", allowed_warehouses] } };
            });
        }

        // Rejected Warehouse
        if (frm.fields_dict.rejected_warehouse && branch_warehouses) {
            let allowed_warehouses = branch_warehouses.split(",");
            frm.set_query("rejected_warehouse", function() {
                return { filters: { "name": ["in", allowed_warehouses] } };
            });
        }

        // SAFETY CHECK: Filter for custom_selling_price_list from akbar16_addons app
        // Wraps in an if-condition so it does not crash standard ERPNext sites
        if (frm.fields_dict.custom_selling_price_list && branch_selling_pl) {
            let allowed_selling_pl = branch_selling_pl.split(",");
            frm.set_query("custom_selling_price_list", function() {
                return { filters: { "name": ["in", allowed_selling_pl] } };
            });
        }

        if (frm.fields_dict.items) {
            if (branch_warehouses) {
                let allowed_warehouses = branch_warehouses.split(",");
                frm.set_query("warehouse", "items", function() {
                    return { filters: { "name": ["in", allowed_warehouses] } };
                });
            }
            if (branch_cost_centers) {
                let allowed_cost_centers = branch_cost_centers.split(",");
                frm.set_query("cost_center", "items", function() {
                    return { filters: { "name": ["in", allowed_cost_centers] } };
                });
            }
        }
    },

    // List/Report View filtering, extracted so both the ListView prototype
    // patch below AND the post-switch soft-refresh (branch_switcher.js) can
    // call the exact same logic against an already-instantiated list.
    compute_list_view_branch_filters: function(doctype, existing_filters) {
        if (!cen_branch_management.branch_doctypes.includes(doctype)) {
            return existing_filters;
        }

        let filters = (existing_filters || []).filter(f => !cen_branch_management.MANAGED_LIST_FILTER_FIELDS.includes(f[1]));

        let active_branch = cen_branch_management.get_active_branch();
        if (!active_branch || active_branch === "All Branches") {
            // Active branch is 'All Branches' or null. Any lingering branch
            // filters saved from a previous session have already been stripped above.
            return filters;
        }

        let branch_company = frappe.defaults.get_user_default("cen_branch_company");
        let branch_cost_centers = frappe.defaults.get_user_default("cen_branch_cost_centers");

        let branch_fieldname = null;
        if (frappe.meta.has_field(doctype, "custom_cen_branch")) {
            branch_fieldname = "custom_cen_branch";
        } else if (frappe.meta.has_field(doctype, "branch")) {
            branch_fieldname = "branch";
        }

        if (branch_fieldname) {
            filters.push([doctype, branch_fieldname, "=", active_branch]);
        } else if (doctype === "Payment Entry" && branch_cost_centers && frappe.meta.has_field(doctype, "cost_center")) {
            filters.push([doctype, "cost_center", "in", branch_cost_centers.split(",")]);
        }

        if (branch_company && frappe.meta.has_field(doctype, "company")) {
            filters.push([doctype, "company", "=", branch_company]);
        }

        return filters;
    }

});

cen_branch_management.branch_doctypes.forEach(doctype => {
    frappe.ui.form.on(doctype, {
        onload: function(frm) {
            cen_branch_management.apply_branch_scoping(frm);
        },
        refresh: function(frm) {
            cen_branch_management.apply_branch_scoping(frm);
        },
        customer: function(frm) {
            cen_branch_management.apply_branch_scoping(frm);
        },
        company: function(frm) {
            cen_branch_management.apply_branch_scoping(frm);
        },
        supplier: function(frm) {
            cen_branch_management.apply_branch_scoping(frm);
        },
        branch: function(frm) {
            // Distinguish "we just auto-filled this to match the session" from
            // "the user actually picked this" -- see resolve_scope_for_form().
            // The programmatic case is skipped entirely (not just un-flagged): the
            // outer apply_sandbox_queries call that set this value already has the
            // correct scope in hand, so re-resolving here would only be redundant
            // (and, chained across several fields set in one pass, adds avoidable
            // overlapping async churn for no benefit).
            if (frm._cen_branch_programmatic_set) {
                frm._cen_branch_programmatic_set = false;
                return;
            }
            frm._cen_branch_user_set = true;
            cen_branch_management.apply_branch_scoping(frm);
        },
        custom_cen_branch: function(frm) {
            if (frm._cen_branch_programmatic_set) {
                frm._cen_branch_programmatic_set = false;
                return;
            }
            frm._cen_branch_user_set = true;
            cen_branch_management.apply_branch_scoping(frm);
        }
    });

    // List View Filters (Global Prototype Patch)
    // We patch the ListView prototype because standard scripts like sales_order_list.js
    // lazy-load and completely overwrite frappe.listview_settings, destroying our onload hooks.
    if (frappe.views && frappe.views.ListView && !frappe.views.ListView.prototype._cen_patched) {
        const original_setup_defaults = frappe.views.ListView.prototype.setup_defaults;

        frappe.views.ListView.prototype.setup_defaults = function() {
            let result = original_setup_defaults.call(this);

            let apply_branch_filters = () => {
                this.filters = cen_branch_management.compute_list_view_branch_filters(this.doctype, this.filters);
            };

            if (result && result.then) {
                return result.then(() => {
                    apply_branch_filters();
                });
            } else {
                apply_branch_filters();
                return result;
            }
        };

        frappe.views.ListView.prototype._cen_patched = true;
    }
});

// Child Table Item Interception (Warehouse Override)
// Hook directly into the warehouse field change event on child rows.
// When Frappe's native get_item_details finishes fetching, it uses set_value for the warehouse.
// We intercept this and override it forcefully if it violates the branch's warehouse scope.
// Synchronous only (no network call): fires on every row edit, so it reads whatever scope is
// already cached for the doc's own branch, falling back to the session scope.

const child_doctypes = [
    "Quotation Item",
    "Sales Order Item",
    "Sales Invoice Item",
    "Purchase Order Item",
    "Purchase Invoice Item",
    "Delivery Note Item",
    "Purchase Receipt Item"
];

child_doctypes.forEach(child_doctype => {
    frappe.ui.form.on(child_doctype, {
        warehouse: function(frm, cdt, cdn) {
            let row = frappe.get_doc(cdt, cdn);
            if (!row.warehouse) return;

            let doc_branch = frm.doc.custom_cen_branch || frm.doc.branch;
            let scope = (doc_branch && cen_branch_management.branch_scope_cache[doc_branch]) || cen_branch_management.get_session_scope();
            let branch_warehouses = scope && scope.cen_branch_warehouses;

            if (branch_warehouses) {
                let allowed_warehouses = branch_warehouses.split(",");

                // If ERPNext's native trigger forced a warehouse outside the branch's scope
                if (!allowed_warehouses.includes(row.warehouse)) {
                    // Forcefully overwrite it with the branch's primary warehouse
                    frappe.model.set_value(cdt, cdn, 'warehouse', allowed_warehouses[0]);

                    frappe.show_alert({
                        message: __('Warehouse automatically updated to match your branch.'),
                        indicator: 'blue'
                    });
                }
            }
        }
    });
});
