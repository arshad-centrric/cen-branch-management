import frappe
from frappe import _

def validate_default_branch(doc, method):
    if not doc.get("custom_cen_default_company"):
        return
        
    default_users = [row.user for row in doc.get("custom_cen_branch_users") if row.is_default]
    
    if not default_users:
        return
        
    other_branches = frappe.get_all("Branch", 
        filters={"custom_cen_default_company": doc.custom_cen_default_company, "name": ["!=", doc.name]}, 
        pluck="name"
    )
    
    if other_branches:
        for user in default_users:
            duplicate = frappe.db.exists("Branch User", {
                "parent": ["in", other_branches],
                "user": user,
                "is_default": 1
            })
            
            if duplicate:
                other_branch = frappe.db.get_value("Branch User", duplicate, "parent")
                full_name = frappe.db.get_value("User", user, "full_name") or user
                frappe.throw(_(f"User {full_name} is already set as the default user for branch {other_branch} under company {doc.custom_cen_default_company}."))
