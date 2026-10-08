import frappe
from frappe.cache_manager import clear_defaults_cache

from cen_branch_management.overrides.branch_address import ADDRESS_BRANCH_FIELD
from cen_branch_management.overrides.user_default_branch import USER_DEFAULT_BRANCH_FIELD, is_branch_user

# All user-default keys this app owns. Kept as one list so the write path
# (apply/clear) and the read path (get_branch_scope) agree on exactly what
# "a branch's scope" means, and so a switch/clear always fully replaces the
# previous set instead of leaving stale keys behind.
BRANCH_DEFAULT_KEYS = [
    "branch",
    "custom_cen_branch",
    "cen_branch_company",
    "cen_branch_warehouse",
    "cen_branch_warehouses",
    "cen_branch_default_warehouse",
    "cen_branch_cost_center",
    "cen_branch_cost_centers",
    "cen_branch_default_cost_center",
    "cen_branch_default_address",
    "cen_branch_addresses",
    "cen_branch_selling_price_lists",
    "cen_branch_buying_price_lists",
    "cen_branch_default_selling_price_list",
    "cen_branch_default_buying_price_list",
]


def initialize_session_branch(login_manager):
    """on_login hook: decide the branch a user starts in. Their Default Branch
    if it is still valid, otherwise All Branches -- nothing is remembered from
    the previous session.

    Frappe runs on_login before it creates the session, so frappe.session.user
    is not the person logging in yet; the user has to be taken from the login
    manager. Whatever is written here is in place before the browser asks for
    its first page, so that page is already filtered and the switcher already
    shows the branch. A page refresh never comes through here: only a login.

    A problem in here must never keep anyone from logging in.
    """
    user = getattr(login_manager, "user", None)
    if not user or user == "Guest":
        return

    try:
        _set_active_branch(resolve_login_branch(user) or "All Branches", user)
    except Exception:
        frappe.log_error(title="Cen Branch Management: could not set the branch at login")
        # Whatever was raised must not surface as a message on the login page.
        frappe.clear_messages()
        try:
            clear_branch_context(user)
        except Exception:
            pass


def resolve_login_branch(user):
    """The user's Default Branch, if the branch still exists and the user is
    still assigned to it. None means All Branches."""
    branch = frappe.db.get_value("User", user, USER_DEFAULT_BRANCH_FIELD)
    if not branch or not frappe.db.exists("Branch", branch) or not is_branch_user(user, branch):
        return None

    return branch


@frappe.whitelist()
def get_user_branches():
    user_branches = frappe.get_all(
        "Branch User",
        filters={"user": frappe.session.user},
        pluck="parent"
    )

    branch_names = list(user_branches)
    branch_names.insert(0, "All Branches")

    active_branch = frappe.defaults.get_user_default("branch") or "All Branches"

    grouped_branches = {}

    physical_branches = [b for b in branch_names if b != "All Branches"]
    if physical_branches:
        # ignore_permissions: this list is gated by Branch User membership above,
        # not by the "Branch" User Permission created by sync_branch_permissions.
        # Without this, a user assigned to two branches would only see whichever
        # branch their (possibly out-of-date/partially-synced) User Permission
        # happens to restrict them to, silently dropping the other from the menu.
        branch_docs = frappe.get_all(
            "Branch",
            filters={"name": ["in", physical_branches]},
            fields=["name", "custom_cen_default_company"],
            ignore_permissions=True
        )
        for b in branch_docs:
            company = b.custom_cen_default_company or "Unassigned Company"
            if company not in grouped_branches:
                grouped_branches[company] = []
            grouped_branches[company].append(b.name)

    return {
        "branches": branch_names,
        "grouped_branches": grouped_branches,
        "active_branch": active_branch
    }


@frappe.whitelist()
def set_active_branch(branch_name):
    return _set_active_branch(branch_name, frappe.session.user)


def _set_active_branch(branch_name, user):
    """Make a branch (or "All Branches") the user's active one. The switcher
    calls this for the session user; login calls it for the user logging in,
    who has no session yet. Not whitelisted: a client must never pick the user.
    """
    if branch_name == "All Branches":
        scope = clear_branch_context(user)
    else:
        if not frappe.db.exists("Branch User", {"user": user, "parent": branch_name}):
            frappe.throw("You do not have permission to access this branch.")

        scope = apply_branch_context(branch_name, user)

    # The caller (navbar switcher) gets the full scope back so it can patch its
    # own client-side state directly instead of reloading the page to pick up
    # what the server just computed.
    return {"status": "success", "active_branch": branch_name, "scope": scope}


@frappe.whitelist()
def get_branch_scope(branch_name):
    """Read-only: the same scope apply_branch_context() would write as user
    defaults, but without writing anything or touching the session's active
    branch. Used to scope a single document by its OWN branch field, which can
    legitimately differ from (or exist independent of) the session switcher's
    active branch -- e.g. a document explicitly set to a branch while the
    session itself is on "All Branches".

    Deliberately not gated by Branch User membership the way set_active_branch
    is: today, in "All Branches" mode, a document's branch/custom_cen_branch
    field is not query-restricted at all (see branch_filters.js), so a user can
    already set a document to any branch regardless of membership. Rejecting
    that here would just make this endpoint fail for a case the app already
    allows elsewhere, without closing that off anywhere. It still requires
    login (@frappe.whitelist) and standard Branch read permission (frappe.get_doc
    below), matching this app's existing endpoints (e.g. get_user_branches).
    """
    if branch_name == "All Branches":
        return dict.fromkeys(BRANCH_DEFAULT_KEYS)

    branch_doc = frappe.get_doc("Branch", branch_name)
    return _compute_branch_scope(branch_doc)


def clear_branch_context(user=None):
    scope = dict.fromkeys(BRANCH_DEFAULT_KEYS)
    _write_user_defaults(scope, user)
    return scope


def apply_branch_context(branch_name, user=None):
    branch_doc = frappe.get_doc("Branch", branch_name)
    scope = _compute_branch_scope(branch_doc)
    _write_user_defaults(scope, user)
    return scope


def _compute_branch_scope(branch_doc):
    """Pure: derive the full scope dict for a branch. No defaults are written
    and no cache is touched here -- this is the single source of truth for
    "what a branch means", shared by the write path (apply_branch_context) and
    the read-only path (get_branch_scope) so the two can never drift apart.
    """
    scope = dict.fromkeys(BRANCH_DEFAULT_KEYS)

    scope["branch"] = branch_doc.name
    scope["custom_cen_branch"] = branch_doc.name
    scope["cen_branch_company"] = branch_doc.custom_cen_default_company or None

    if branch_doc.custom_cen_warehouse_parent:
        scope["cen_branch_warehouse"] = branch_doc.custom_cen_warehouse_parent
        wh_data = frappe.db.get_value("Warehouse", branch_doc.custom_cen_warehouse_parent, ["lft", "rgt"], as_dict=True)
        if wh_data:
            wh_list = frappe.get_all("Warehouse", filters={"lft": [">=", wh_data.lft], "rgt": ["<=", wh_data.rgt], "is_group": 0}, pluck="name")
            if wh_list:
                scope["cen_branch_warehouses"] = ",".join(wh_list)

    if branch_doc.custom_cen_cost_center_parent:
        scope["cen_branch_cost_center"] = branch_doc.custom_cen_cost_center_parent
        cc_data = frappe.db.get_value("Cost Center", branch_doc.custom_cen_cost_center_parent, ["lft", "rgt"], as_dict=True)
        if cc_data:
            cc_list = frappe.get_all("Cost Center", filters={"lft": [">=", cc_data.lft], "rgt": ["<=", cc_data.rgt], "is_group": 0}, pluck="name")
            if cc_list:
                scope["cen_branch_cost_centers"] = ",".join(cc_list)

    # Auto-fill values for transaction forms. Kept separate from the lists
    # above, which only restrict what can be picked.
    scope["cen_branch_default_warehouse"] = branch_doc.get("custom_cen_default_warehouse") or None
    scope["cen_branch_default_cost_center"] = branch_doc.get("custom_cen_default_cost_center") or None

    # The Branch Address is filled into the company address of new documents;
    # the full list of the branch's addresses tells the form which values to
    # leave alone. Joined by newline: address names can contain commas.
    default_address = branch_doc.get("custom_cen_branch_address") or None
    branch_addresses = frappe.get_all(
        "Address", filters={ADDRESS_BRANCH_FIELD: branch_doc.name, "disabled": 0}, pluck="name", order_by="name"
    )
    if default_address and default_address not in branch_addresses:
        branch_addresses.append(default_address)

    scope["cen_branch_default_address"] = default_address
    scope["cen_branch_addresses"] = "\n".join(branch_addresses) or None

    selling_price_lists = set()
    for row in branch_doc.get("custom_cen_allowed_selling_price_lists", []):
        if row.price_list:
            selling_price_lists.add(row.price_list)
    if branch_doc.custom_cen_default_selling_price_list:
        selling_price_lists.add(branch_doc.custom_cen_default_selling_price_list)
    if selling_price_lists:
        scope["cen_branch_selling_price_lists"] = ",".join(selling_price_lists)
    scope["cen_branch_default_selling_price_list"] = branch_doc.custom_cen_default_selling_price_list or None

    buying_price_lists = set()
    for row in branch_doc.get("custom_cen_allowed_buying_price_lists", []):
        if row.price_list:
            buying_price_lists.add(row.price_list)
    if branch_doc.custom_cen_default_buying_price_list:
        buying_price_lists.add(branch_doc.custom_cen_default_buying_price_list)
    if buying_price_lists:
        scope["cen_branch_buying_price_lists"] = ",".join(buying_price_lists)
    scope["cen_branch_default_buying_price_list"] = branch_doc.custom_cen_default_buying_price_list or None

    return scope


def _write_user_defaults(scope, user=None):
    """Batched replacement for what used to be up to 11 individual
    frappe.defaults.set_user_default()/clear_default() calls.

    Each of those calls independently triggers a FULL user-cache wipe
    (frappe.clear_cache(user=...), a 15-key wipe including the expensive
    "bootinfo" blob -- see frappe/defaults.py _clear_cache() and
    frappe/cache_manager.py clear_user_cache()), so switching branches used to
    mean ~11 full cache wipes plus one more explicit one, before the client
    even reloaded the page. A branch switch only ever changes these defaults --
    nothing else cached under a user (roles, permissions, sidebar, etc.)
    changes -- so this does one delete-then-bulk-insert against DefaultValue
    directly, and only the narrow invalidation that's actually needed:
    - clear_defaults_cache(user): the small cache the *_user_default() read
      path actually uses, so subsequent reads (including get_branch_scope and
      any other request from this user) see the new values immediately.
    - a single hdel of just this user's "bootinfo" cache entry, so a stale
      cached boot blob doesn't linger and show an old branch in a new tab or
      after a hard refresh -- without paying for a full rebuild right now; that
      rebuild is deferred to whenever this user's next full page load happens.
    """
    user = user or frappe.session.user
    now = frappe.utils.now()

    frappe.db.delete("DefaultValue", {"parent": user, "defkey": ["in", list(scope.keys())]})

    rows = []
    for key, value in scope.items():
        if not value:
            continue
        rows.append([
            frappe.generate_hash(length=10),  # name
            now, now,                         # creation, modified
            user, user,                       # owner, modified_by
            0,                                # docstatus
            user,                             # parent
            "system_defaults",                # parentfield
            "__default",                      # parenttype
            0,                                # idx
            key,                              # defkey
            frappe.utils.cstr(value),         # defvalue
        ])

    if rows:
        frappe.db.bulk_insert(
            "DefaultValue",
            fields=[
                "name", "creation", "modified", "owner", "modified_by",
                "docstatus", "parent", "parentfield", "parenttype",
                "idx", "defkey", "defvalue",
            ],
            values=rows,
        )

    clear_defaults_cache(user)
    frappe.cache.hdel("bootinfo", user)
