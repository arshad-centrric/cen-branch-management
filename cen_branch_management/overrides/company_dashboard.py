def get_data(data=None):
    if data is None:
        data = {}
    
    # Map the custom relationship field so the system knows how to count the branches
    data.setdefault("non_standard_fieldnames", {}).update({
        "Branch": "custom_cen_default_company"
    })
    
    # Inject the Branch metric into the dashboard UI transactions list
    data.setdefault("transactions", []).append({
        "label": "Branch Management",
        "items": ["Branch"]
    })
    
    return data
