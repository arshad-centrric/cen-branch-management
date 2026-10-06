// Shared namespace: also used by branch_switcher.js for the soft-refresh after
// a branch switch (no full page reload -- see branch_switcher.js).
window.cen_branch_management = window.cen_branch_management || {};

Object.assign(window.cen_branch_management, {

    // Doctypes whose forms AND list views are branch-scoped.
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

    // Stock doctypes whose forms get the same scoping and branch defaults, but
    // whose list views are left alone (they were never branch-filtered, and
    // doing so would hide existing entries that carry no branch).
    form_only_doctypes: [
        "Stock Entry",
        "Material Request"
    ],

    get_form_doctypes: function() {
        return cen_branch_management.branch_doctypes.concat(cen_branch_management.form_only_doctypes);
    },

    // Header fields that take the branch's default warehouse. A function is
    // given the doc, for doctypes where it depends on the kind of transaction.
    default_warehouse_fields: {
        "Sales Order": ["set_warehouse"],
        "Sales Invoice": ["set_warehouse"],
        "Delivery Note": ["set_warehouse"],
        "Purchase Order": ["set_warehouse"],
        "Purchase Receipt": ["set_warehouse"],
        "Purchase Invoice": ["set_warehouse"],
        "Material Request": ["set_warehouse"],
        // The branch is where stock leaves from or arrives at, depending on the
        // purpose. A transfer only gets its source: the target is another
        // warehouse the user has to choose. Manufacture and the subcontracting
        // purposes take their warehouses from the work/subcontracting order.
        "Stock Entry": function(doc) {
            let fields = [];
            let from_branch = ["Material Issue", "Material Transfer", "Material Transfer for Manufacture",
                "Material Consumption for Manufacture", "Send to Subcontractor", "Repack"];
            let to_branch = ["Material Receipt", "Repack"];

            if (from_branch.includes(doc.purpose)) fields.push("from_warehouse");
            if (to_branch.includes(doc.purpose)) fields.push("to_warehouse");
            return fields;
        }
    },

    // Address fields that hold one of the COMPANY's addresses, per doctype, as
    // defined in the installed ERPNext. Customer and supplier address fields
    // (customer_address, shipping_address_name, supplier_address, and buying's
    // dispatch_address, which is the supplier's) are deliberately not listed.
    company_address_fields: {
        "Quotation": ["company_address"],
        "Sales Order": ["company_address", "dispatch_address_name"],
        "Sales Invoice": ["company_address", "dispatch_address_name"],
        "Delivery Note": ["company_address", "dispatch_address_name"],
        "Purchase Order": ["billing_address", "shipping_address"],
        "Purchase Invoice": ["billing_address", "shipping_address"],
        "Purchase Receipt": ["billing_address", "shipping_address"]
    },

    // Field on Address that says which branch a company address belongs to.
    ADDRESS_BRANCH_FIELD: "custom_cen_address_branch",

    // Narrows the company address fields to the addresses of the document's
    // effective branch. ERPNext's own query stays in charge: ours wraps it and
    // only adds the branch when ERPNext is asking for the company's addresses,
    // so the cases where it deliberately is not (drop-ship, or a buying shipping
    // address for a customer) keep working, and with no branch (All Branches)
    // the result is ERPNext's query untouched.
    //
    // The branch is read when the dropdown opens, from the scope last applied to
    // this document, so nothing has to be re-set when the branch field, the
    // company or the top-bar switcher changes: those all re-apply the scope.
    // The wrap is repeated on every apply because ERPNext may set its query
    // again; a field that is already wrapped is skipped.
    apply_branch_address_queries: function(frm) {
        (cen_branch_management.company_address_fields[frm.doctype] || []).forEach(fieldname => {
            let field = frm.fields_dict[fieldname];
            if (!field || (field.get_query && field.get_query._cen_branch_wrapped)) return;

            let erpnext_query = field.get_query;
            let wrapped = function() {
                let query = erpnext_query ? erpnext_query.apply(this, arguments) : null;
                return cen_branch_management.add_branch_to_address_query(frm, query);
            };
            wrapped._cen_branch_wrapped = true;
            field.get_query = wrapped;
        });
    },

    add_branch_to_address_query: function(frm, query) {
        let scope = cen_branch_management.get_doc_state(frm).scope;
        if (!scope || !scope.branch) return query;

        if (!query) {
            query = {
                query: "frappe.contacts.doctype.address.address.address_query",
                filters: { link_doctype: "Company", link_name: frm.doc.company || "" }
            };
        }

        let filters = query.filters;
        if (!filters || Array.isArray(filters) || filters.link_doctype !== "Company") return query;

        let branch_filters = Object.assign({}, filters);
        branch_filters[cen_branch_management.ADDRESS_BRANCH_FIELD] = scope.branch;
        return Object.assign({}, query, { filters: branch_filters });
    },

    get_default_warehouse_fields: function(doc) {
        let fields = cen_branch_management.default_warehouse_fields[doc.doctype];
        if (typeof fields === "function") fields = fields(doc);
        return fields || [];
    },

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
            cen_branch_default_warehouse: frappe.defaults.get_user_default("cen_branch_default_warehouse"),
            cen_branch_cost_center: frappe.defaults.get_user_default("cen_branch_cost_center"),
            cen_branch_cost_centers: frappe.defaults.get_user_default("cen_branch_cost_centers"),
            cen_branch_default_cost_center: frappe.defaults.get_user_default("cen_branch_default_cost_center"),
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
        // it set (loaded from the DB), or a new doc given a branch other than the
        // session's (see on_doc_branch_changed). A brand-new doc whose branch only
        // ever matched the session must keep tracking the session -- otherwise
        // switching branches later while the form is still open would have no
        // visible effect (the doc's own value would always "win").
        let doc_branch_is_authoritative = !frm.is_new() || cen_branch_management.get_doc_state(frm).branch_user_set;

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

    // Per-document bookkeeping for a form. Frappe keeps one form object per
    // doctype and reuses it for every document opened in it, so anything stored
    // straight on frm would leak from one document into the next.
    get_doc_state: function(frm) {
        if (!frm._cen_doc_state || frm._cen_doc_state.docname !== frm.docname) {
            frm._cen_doc_state = { docname: frm.docname, filled_defaults: {} };
        }
        return frm._cen_doc_state;
    },

    // Change handler for a document's own branch field. Decides whether the doc
    // now carries a deliberate branch of its own (see resolve_scope_for_form).
    //
    // A change event alone does not mean the user picked something: Frappe fires
    // it for every pre-filled link field when a new document opens, and we fire
    // it ourselves when auto-filling. So the value is what counts -- a branch
    // that differs from the session's active one is the doc's own choice; one
    // that matches it is just following the session and must keep doing so.
    on_doc_branch_changed: function(frm, fieldname) {
        // Our own auto-fill: the apply_sandbox_queries call that set it already
        // has the right scope in hand, so there is nothing to re-resolve.
        let state = cen_branch_management.get_doc_state(frm);
        if (state.branch_programmatic_set) {
            state.branch_programmatic_set = false;
            return;
        }

        let value = frm.doc[fieldname];
        state.branch_user_set = Boolean(value) && value !== cen_branch_management.get_active_branch();
        cen_branch_management.apply_branch_scoping(frm);
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
            cen_branch_management.get_doc_state(frm).scope = scope;
            cen_branch_management.apply_sandbox_queries(frm, scope);
            cen_branch_management.apply_branch_defaults(frm, scope);
            cen_branch_management.apply_branch_address_queries(frm);
        });
    },

    // The scope a form is using right now, without a server call: for the
    // per-row handlers below, which fire too often to wait on a request.
    get_cached_scope_for_form: function(frm) {
        let doc_branch = frm.doc.custom_cen_branch || frm.doc.branch;
        return (doc_branch && cen_branch_management.branch_scope_cache[doc_branch]) || cen_branch_management.get_session_scope();
    },

    // Fills the branch's default warehouse and cost center on a new document.
    // Only empty fields are filled, so anything the user (or ERPNext) put there
    // is kept. A value this function filled earlier is tracked and still counts
    // as "ours": it is replaced when the branch is switched while the form is
    // open, and cleared when it stops applying (no active branch, or a Stock
    // Entry purpose that no longer uses that warehouse field).
    apply_branch_defaults: function(frm, scope) {
        if (!frm.is_new()) return;

        scope = scope || {};
        let filled = cen_branch_management.get_doc_state(frm).filled_defaults;
        let wanted = {};

        if (scope.cen_branch_default_warehouse) {
            cen_branch_management.get_default_warehouse_fields(frm.doc).forEach(fieldname => {
                wanted[fieldname] = scope.cen_branch_default_warehouse;
            });
        }
        if (scope.cen_branch_default_cost_center) {
            wanted.cost_center = scope.cen_branch_default_cost_center;
        }

        new Set(Object.keys(filled).concat(Object.keys(wanted))).forEach(fieldname => {
            if (!frm.fields_dict[fieldname]) return;

            let current = frm.doc[fieldname];
            let is_ours = Boolean(current) && current === filled[fieldname];

            if (current && !is_ours) {
                delete filled[fieldname];
                return;
            }

            if (wanted[fieldname]) {
                filled[fieldname] = wanted[fieldname];
                if (current !== wanted[fieldname]) frm.set_value(fieldname, wanted[fieldname]);
            } else {
                delete filled[fieldname];
                if (is_ours) frm.set_value(fieldname, null);
            }
        });

        (frm.doc.items || []).forEach(row => cen_branch_management.fill_item_row_defaults(frm, row, scope));
    },

    // A row that has no item yet gets the branch defaults, so ERPNext's item
    // details logic starts from them once an item is chosen. Rows that already
    // have an item are left exactly as they are.
    fill_item_row_defaults: function(frm, row, scope) {
        if (!scope || !frm.is_new() || row.item_code) return;

        let defaults = {
            warehouse: cen_branch_management.get_default_warehouse_fields(frm.doc).length ? scope.cen_branch_default_warehouse : null,
            cost_center: scope.cen_branch_default_cost_center
        };

        Object.keys(defaults).forEach(fieldname => {
            if (defaults[fieldname] && !row[fieldname] && frappe.meta.has_field(row.doctype, fieldname)) {
                frappe.model.set_value(row.doctype, row.name, fieldname, defaults[fieldname]);
            }
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
                cen_branch_management.get_doc_state(frm).branch_programmatic_set = true;
                frm.set_value("custom_cen_branch", active_branch);
            }
            if (frm.fields_dict.branch && frm.doc.branch !== active_branch) {
                cen_branch_management.get_doc_state(frm).branch_programmatic_set = true;
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

    // Re-applies the branch filters on a list that is already on screen (or was,
    // before the user moved to a form). FilterArea.set() only adds filters -- it
    // never removes one that is no longer wanted -- so the previous branch's
    // filters are removed first. Clearing a standard filter field (e.g. Company)
    // is asynchronous, so the new filters are only set once that has finished;
    // otherwise the late clear wipes the company that was just set.
    refresh_list_branch_filters: function(list) {
        let area = list.filter_area;
        if (!area || !area.remove || !area.set) {
            list.refresh();
            return;
        }

        let standard_fields = (list.page && list.page.fields_dict) || {};
        let cleared = cen_branch_management.MANAGED_LIST_FILTER_FIELDS.map(fieldname => {
            area.remove(fieldname);
            return standard_fields[fieldname] ? standard_fields[fieldname].set_value("") : null;
        });

        Promise.all(cleared).then(() => {
            list.filters = cen_branch_management.compute_list_view_branch_filters(list.doctype, list.filters);
            return area.set(list.filters);
        }).then(() => list.refresh());
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

cen_branch_management.get_form_doctypes().forEach(doctype => {
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
        // Stock Entry: the purpose decides which warehouse field the branch
        // default goes into (see default_warehouse_fields).
        purpose: function(frm) {
            cen_branch_management.apply_branch_scoping(frm);
        },
        stock_entry_type: function(frm) {
            cen_branch_management.apply_branch_scoping(frm);
        },
        branch: function(frm) {
            cen_branch_management.on_doc_branch_changed(frm, "branch");
        },
        custom_cen_branch: function(frm) {
            cen_branch_management.on_doc_branch_changed(frm, "custom_cen_branch");
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
    "Purchase Receipt Item",
    "Material Request Item",
    "Stock Entry Detail"
];

child_doctypes.forEach(child_doctype => {
    frappe.ui.form.on(child_doctype, {
        items_add: function(frm, cdt, cdn) {
            cen_branch_management.fill_item_row_defaults(frm, frappe.get_doc(cdt, cdn), cen_branch_management.get_cached_scope_for_form(frm));
        },
        warehouse: function(frm, cdt, cdn) {
            let row = frappe.get_doc(cdt, cdn);
            if (!row.warehouse) return;

            let scope = cen_branch_management.get_cached_scope_for_form(frm);
            let branch_warehouses = scope && scope.cen_branch_warehouses;

            if (branch_warehouses) {
                let allowed_warehouses = branch_warehouses.split(",");

                // If ERPNext's native trigger forced a warehouse outside the branch's scope
                if (!allowed_warehouses.includes(row.warehouse)) {
                    // Forcefully overwrite it with the branch's default warehouse,
                    // or the first branch warehouse when no default is configured
                    let default_warehouse = scope.cen_branch_default_warehouse;
                    let replacement = allowed_warehouses.includes(default_warehouse) ? default_warehouse : allowed_warehouses[0];
                    frappe.model.set_value(cdt, cdn, 'warehouse', replacement);

                    frappe.show_alert({
                        message: __('Warehouse automatically updated to match your branch.'),
                        indicator: 'blue'
                    });
                }
            }
        }
    });
});
