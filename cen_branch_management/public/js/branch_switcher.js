$(document).on('app_ready', function() {
    if (frappe.session.user === "Guest") return;

    // Bumped on every click; a callback whose token no longer matches the
    // latest one was superseded by a newer switch and is dropped silently.
    let switch_token = 0;

    function build_switcher_html(data) {
        let options = "";

        let all_active = ("All Branches" === data.active_branch);
        let all_bg = all_active ? "background-color: var(--control-bg);" : "";
        let all_icon = all_active ? `<svg class="icon icon-sm" style="margin-right: 8px; fill: var(--primary);"><use href="#icon-check"></use></svg>` : `<span style="width: 24px; display: inline-block;"></span>`;
        let all_text = all_active ? "font-weight: 600;" : "font-weight: 400;";
        options += `<li><a class="dropdown-item cen-branch-option" href="#" data-branch="All Branches" style="display: flex; align-items: center; padding: 8px 12px; ${all_bg} ${all_text}">${all_icon}All Branches</a></li>`;
        options += `<li class="divider" style="margin: 4px 0; border-bottom: 1px solid var(--border-color);"></li>`;

        let grouped = data.grouped_branches;

        if (grouped && Object.keys(grouped).length > 0) {
            for (let company in grouped) {
                options += `<li class="dropdown-header text-muted" style="font-size: 11px; text-transform: uppercase; padding: 6px 12px; margin-top: 4px; font-weight: 600;">${company}</li>`;
                grouped[company].forEach(branch => {
                    if (branch !== "All Branches") {
                        let is_active = (branch === data.active_branch);
                        let bg = is_active ? "background-color: var(--control-bg);" : "";
                        let icon = is_active ? `<svg class="icon icon-sm" style="margin-right: 8px; fill: var(--primary);"><use href="#icon-check"></use></svg>` : `<span style="width: 24px; display: inline-block;"></span>`;
                        let text_style = is_active ? "font-weight: 600;" : "font-weight: 400;";
                        options += `<li><a class="dropdown-item cen-branch-option" href="#" data-branch="${branch}" style="display: flex; align-items: center; padding: 8px 12px; ${bg} ${text_style}">${icon}${branch}</a></li>`;
                    }
                });
                options += `<li class="divider" style="margin: 4px 0; border-bottom: 1px solid var(--border-color);"></li>`;
            }
        } else {
            data.branches.forEach(branch => {
                if (branch !== "All Branches") {
                    let is_active = (branch === data.active_branch);
                    let bg = is_active ? "background-color: var(--control-bg);" : "";
                    let icon = is_active ? `<svg class="icon icon-sm" style="margin-right: 8px; fill: var(--primary);"><use href="#icon-check"></use></svg>` : `<span style="width: 24px; display: inline-block;"></span>`;
                    let text_style = is_active ? "font-weight: 600;" : "font-weight: 400;";
                    options += `<li><a class="dropdown-item cen-branch-option" href="#" data-branch="${branch}" style="display: flex; align-items: center; padding: 8px 12px; ${bg} ${text_style}">${icon}${branch}</a></li>`;
                }
            });
        }

        return `
            <div class="cen-branch-switcher-container dropdown" style="margin-right: 10px; display: inline-block;">
                <button type="button" class="btn btn-default btn-sm" data-toggle="dropdown" aria-expanded="false" style="display: flex; align-items: center; gap: 6px; box-shadow: var(--shadow-sm);">
                    <span class="hidden-xs actions-btn-group-label" style="font-weight: 500;">${data.active_branch || 'Select Branch'}</span>
                    <svg class="icon icon-xs"><use href="#icon-select"></use></svg>
                </button>
                <ul class="dropdown-menu dropdown-menu-right" role="menu" style="max-height: 400px; overflow-y: auto; min-width: 260px; padding: 8px 0; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
                    ${options}
                </ul>
            </div>
        `;
    }

    function handle_switch(selected_branch, data) {
        if (!selected_branch || selected_branch === data.active_branch) return;

        let my_token = ++switch_token;

        frappe.call({
            method: "cen_branch_management.api.switcher.set_active_branch",
            args: { branch_name: selected_branch },
            callback: function(res) {
                if (my_token !== switch_token) return; // superseded by a newer switch
                if (res.exc || !res.message) return;

                let scope = res.message.scope;
                let new_active_branch = res.message.active_branch || selected_branch;

                // 1. Patch the client-side defaults snapshot instantly -- no reload needed.
                //    New/open forms and list views read this via frappe.defaults.get_user_default.
                if (scope) {
                    Object.keys(scope).forEach(key => {
                        frappe.defaults.set_user_default_local(key, scope[key]);
                    });
                    if (new_active_branch !== "All Branches") {
                        cen_branch_management.branch_scope_cache[new_active_branch] = scope;
                    }
                }

                // 2. Re-render the switcher itself in place (button label, checkmark).
                data.active_branch = new_active_branch;
                render_switcher(data);

                // 3. Soft-refresh an open List/Report View for a branch doctype
                //    (Report View extends ListView, so this covers both automatically).
                if (window.cur_list && cen_branch_management.branch_doctypes.includes(cur_list.doctype)) {
                    // FilterArea.set() only adds filters (it skips ones that already
                    // exist, but never removes one that's no longer wanted), so the
                    // previous branch's filter has to be explicitly removed first --
                    // otherwise repeated switches stack up multiple "Branch = X" chips
                    // instead of replacing the old one.
                    if (cur_list.filter_area && cur_list.filter_area.remove) {
                        cen_branch_management.MANAGED_LIST_FILTER_FIELDS.forEach(fieldname => {
                            cur_list.filter_area.remove(fieldname);
                        });
                    }

                    cur_list.filters = cen_branch_management.compute_list_view_branch_filters(cur_list.doctype, cur_list.filters);
                    if (cur_list.filter_area && cur_list.filter_area.set) {
                        cur_list.filter_area.set(cur_list.filters);
                    } else {
                        cur_list.refresh();
                    }
                }

                // 4. Soft-refresh an open new/draft Form for a branch doctype.
                //    Submitted docs are left untouched (apply_sandbox_queries already guards this).
                if (window.cur_frm && cen_branch_management.get_form_doctypes().includes(cur_frm.doctype)
                    && (cur_frm.is_new() || cur_frm.doc.docstatus === 0)) {
                    cen_branch_management.apply_branch_scoping(cur_frm);
                }

                frappe.show_alert({
                    message: `Switched to ${new_active_branch}.`,
                    indicator: 'green'
                });
            }
        });
    }

    function render_switcher(data) {
        // Always re-derive from the live client-side source of truth rather than
        // trusting data.active_branch as tracked so far -- that field is only ever
        // updated by a successful switch's own callback, so if the widget is ever
        // (re-)rendered through any other path (e.g. re-injection after an SPA
        // route change), a plain reliance on the tracked copy risks showing a
        // stale branch even though forms/lists are correctly using the current one
        // (frappe.defaults.get_user_default, which this exact call reads).
        data.active_branch = cen_branch_management.get_active_branch() || "All Branches";

        let $page_actions = $('.page-container:visible .page-actions').first();
        if (!$page_actions.length) return false;

        $page_actions.find('.cen-branch-switcher-container').remove();
        let $container = $(build_switcher_html(data)).prependTo($page_actions);

        $container.find('.cen-branch-option').on('click', function(e) {
            e.preventDefault();
            handle_switch($(this).attr('data-branch'), data);
        });

        return true;
    }

    frappe.call({
        method: "cen_branch_management.api.switcher.get_user_branches",
        callback: function(r) {
            if (!(r.message && r.message.branches && r.message.branches.length > 0)) return;

            let data = r.message;

            function tryInjecting() {
                let $page_actions = $('.page-container:visible .page-actions').first();
                if ($page_actions.length && $page_actions.find('.cen-branch-switcher-container').length === 0) {
                    return render_switcher(data);
                }
                return false;
            }

            tryInjecting();

            const observer = new MutationObserver((mutations, obs) => {
                tryInjecting();
            });
            observer.observe(document.body, { childList: true, subtree: true });

            frappe.router.on('change', () => {
                setTimeout(tryInjecting, 100);
            });
        }
    });
});
