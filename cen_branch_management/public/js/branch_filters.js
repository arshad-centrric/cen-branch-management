const branch_doctypes = [
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
];

branch_doctypes.forEach(doctype => {
    // 1. Form Filters
    const apply_sandbox_queries = function(frm) {
        let active_branch = frappe.defaults.get_user_default("branch");
        let branch_company = frappe.defaults.get_user_default("cen_branch_company");
        let branch_selling_pl = frappe.defaults.get_user_default("cen_branch_selling_price_lists");
        let branch_buying_pl = frappe.defaults.get_user_default("cen_branch_buying_price_lists");
        let branch_warehouses = frappe.defaults.get_user_default("cen_branch_warehouses");
        let branch_cost_centers = frappe.defaults.get_user_default("cen_branch_cost_centers");

        if (!active_branch || active_branch === "All Branches") return;

        // Auto-Setter for Company (Overpowers native Frappe defaults)
        if (frm.is_new() && frm.fields_dict.company && branch_company && branch_company !== "All Branches") {
            if (frm.doc.company !== branch_company) {
                frm.set_value("company", branch_company);
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
        } // End if items
    };

    frappe.ui.form.on(doctype, {
        onload: function(frm) {
            apply_sandbox_queries(frm);
        },
        refresh: function(frm) {
            let active_branch = frappe.defaults.get_user_default("branch");
            let branch_company = frappe.defaults.get_user_default("cen_branch_company");
            let branch_selling_pl = frappe.defaults.get_user_default("cen_branch_selling_price_lists");
            let branch_buying_pl = frappe.defaults.get_user_default("cen_branch_buying_price_lists");
            
            if (!active_branch || active_branch === "All Branches") return;

            // Auto-Setters (Only for new or draft documents)
            if (frm.is_new() || frm.doc.docstatus === 0) {
                if (frm.is_new() && frm.fields_dict.company && frm.doc.company !== branch_company) {
                    frm.set_value("company", branch_company);
                }
                if (frm.fields_dict.custom_cen_branch && frm.doc.custom_cen_branch !== active_branch) {
                    frm.set_value("custom_cen_branch", active_branch);
                }
                if (frm.fields_dict.branch && frm.doc.branch !== active_branch) {
                    frm.set_value("branch", active_branch);
                }
                
                // Restrict Selling Price Lists Auto-Clear
                if (frm.fields_dict.selling_price_list && branch_selling_pl) {
                    let allowed_selling_pl = branch_selling_pl.split(",");
                    if (frm.doc.selling_price_list && !allowed_selling_pl.includes(frm.doc.selling_price_list)) {
                        frm.set_value("selling_price_list", null);
                    }
                }

                // Restrict Buying Price Lists Auto-Clear
                if (frm.fields_dict.buying_price_list && branch_buying_pl) {
                    let allowed_buying_pl = branch_buying_pl.split(",");
                    if (frm.doc.buying_price_list && !allowed_buying_pl.includes(frm.doc.buying_price_list)) {
                        frm.set_value("buying_price_list", null);
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

            apply_sandbox_queries(frm);
        },
        customer: function(frm) {
            apply_sandbox_queries(frm);
        },
        company: function(frm) {
            apply_sandbox_queries(frm);
        },
        supplier: function(frm) {
            apply_sandbox_queries(frm);
        }
    });

    // 2. List View Filters (Global Prototype Patch)
    // We patch the ListView prototype because standard scripts like sales_order_list.js 
    // lazy-load and completely overwrite frappe.listview_settings, destroying our onload hooks.
    if (frappe.views && frappe.views.ListView && !frappe.views.ListView.prototype._cen_patched) {
        const original_setup_defaults = frappe.views.ListView.prototype.setup_defaults;
        
        frappe.views.ListView.prototype.setup_defaults = function() {
            let result = original_setup_defaults.call(this);
            
            let apply_branch_filters = () => {
                if (branch_doctypes.includes(this.doctype)) {
                    let active_branch = frappe.defaults.get_user_default("branch");
                    if (active_branch && active_branch !== "All Branches") {
                        let branch_company = frappe.defaults.get_user_default("cen_branch_company");
                        let branch_cost_centers = frappe.defaults.get_user_default("cen_branch_cost_centers");

                        let branch_fieldname = null;
                        if (frappe.meta.has_field(this.doctype, "custom_cen_branch")) {
                            branch_fieldname = "custom_cen_branch";
                        } else if (frappe.meta.has_field(this.doctype, "branch")) {
                            branch_fieldname = "branch";
                        }
                        
                        this.filters = this.filters.filter(f => !["branch", "custom_cen_branch", "company", "cost_center"].includes(f[1]));

                        if (branch_fieldname) {
                            this.filters.push([this.doctype, branch_fieldname, "=", active_branch]);
                        } else if (this.doctype === "Payment Entry" && branch_cost_centers && frappe.meta.has_field(this.doctype, "cost_center")) {
                            this.filters.push([this.doctype, "cost_center", "in", branch_cost_centers.split(",")]);
                        }

                        if (branch_company && frappe.meta.has_field(this.doctype, "company")) {
                            this.filters.push([this.doctype, "company", "=", branch_company]);
                        }
                    } else {
                        // Active branch is 'All Branches' or null. Clear any lingering branch filters saved from a previous session.
                        this.filters = this.filters.filter(f => !["branch", "custom_cen_branch", "company", "cost_center"].includes(f[1]));
                    }
                }
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

// 3. Child Table Item Interception (Warehouse Override)
// Hook directly into the warehouse field change event on child rows.
// When Frappe's native get_item_details finishes fetching, it uses set_value for the warehouse.
// We intercept this and override it forcefully if it violates the user's branch warehouse permissions.

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
            let branch_warehouses = frappe.defaults.get_user_default("cen_branch_warehouses");
            
            if (branch_warehouses && row.warehouse) {
                let allowed_warehouses = branch_warehouses.split(",");
                
                // If ERPNext's native trigger forced a warehouse outside the user's branch
                if (!allowed_warehouses.includes(row.warehouse)) {
                    // Forcefully overwrite it with their primary branch warehouse
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
