$(document).on('app_ready', function() {
    if (frappe.session.user === "Guest") return;

    frappe.call({
        method: "cen_branch_management.api.switcher.get_user_branches",
        callback: function(r) {
            if (r.message && r.message.branches && r.message.branches.length > 0) {
                let options = "";
                
                let all_active = ("All Branches" === r.message.active_branch);
                let all_bg = all_active ? "background-color: var(--control-bg);" : "";
                let all_icon = all_active ? `<svg class="icon icon-sm" style="margin-right: 8px; fill: var(--primary);"><use href="#icon-check"></use></svg>` : `<span style="width: 24px; display: inline-block;"></span>`;
                let all_text = all_active ? "font-weight: 600;" : "font-weight: 400;";
                options += `<li><a class="dropdown-item cen-branch-option" href="#" data-branch="All Branches" style="display: flex; align-items: center; padding: 8px 12px; ${all_bg} ${all_text}">${all_icon}All Branches</a></li>`;
                options += `<li class="divider" style="margin: 4px 0; border-bottom: 1px solid var(--border-color);"></li>`;

                let grouped = r.message.grouped_branches;
                
                if (grouped && Object.keys(grouped).length > 0) {
                    for (let company in grouped) {
                        options += `<li class="dropdown-header text-muted" style="font-size: 11px; text-transform: uppercase; padding: 6px 12px; margin-top: 4px; font-weight: 600;">${company}</li>`;
                        grouped[company].forEach(branch => {
                            if (branch !== "All Branches") {
                                let is_active = (branch === r.message.active_branch);
                                let bg = is_active ? "background-color: var(--control-bg);" : "";
                                let icon = is_active ? `<svg class="icon icon-sm" style="margin-right: 8px; fill: var(--primary);"><use href="#icon-check"></use></svg>` : `<span style="width: 24px; display: inline-block;"></span>`;
                                let text_style = is_active ? "font-weight: 600;" : "font-weight: 400;";
                                options += `<li><a class="dropdown-item cen-branch-option" href="#" data-branch="${branch}" style="display: flex; align-items: center; padding: 8px 12px; ${bg} ${text_style}">${icon}${branch}</a></li>`;
                            }
                        });
                        options += `<li class="divider" style="margin: 4px 0; border-bottom: 1px solid var(--border-color);"></li>`;
                    }
                } else {
                    r.message.branches.forEach(branch => {
                        if (branch !== "All Branches") {
                            let is_active = (branch === r.message.active_branch);
                            let bg = is_active ? "background-color: var(--control-bg);" : "";
                            let icon = is_active ? `<svg class="icon icon-sm" style="margin-right: 8px; fill: var(--primary);"><use href="#icon-check"></use></svg>` : `<span style="width: 24px; display: inline-block;"></span>`;
                            let text_style = is_active ? "font-weight: 600;" : "font-weight: 400;";
                            options += `<li><a class="dropdown-item cen-branch-option" href="#" data-branch="${branch}" style="display: flex; align-items: center; padding: 8px 12px; ${bg} ${text_style}">${icon}${branch}</a></li>`;
                        }
                    });
                }

                let switcher_html = `
                    <div class="cen-branch-switcher-container dropdown" style="margin-right: 10px; display: inline-block;">
                        <button type="button" class="btn btn-default btn-sm" data-toggle="dropdown" aria-expanded="false" style="display: flex; align-items: center; gap: 6px; box-shadow: var(--shadow-sm);">
                            <span class="hidden-xs actions-btn-group-label" style="font-weight: 500;">${r.message.active_branch || 'Select Branch'}</span>
                            <svg class="icon icon-xs"><use href="#icon-select"></use></svg>
                        </button>
                        <ul class="dropdown-menu dropdown-menu-right" role="menu" style="max-height: 400px; overflow-y: auto; min-width: 260px; padding: 8px 0; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
                            ${options}
                        </ul>
                    </div>
                `;

                function tryInjecting() {
                    let $page_actions = $('.page-container:visible .page-actions').first();
                    
                    if ($page_actions.length && $page_actions.find('.cen-branch-switcher-container').length === 0) {
                        $(switcher_html).prependTo($page_actions);

                        $page_actions.find('.cen-branch-option').on('click', function(e) {
                            e.preventDefault();
                            let selected_branch = $(this).attr('data-branch');
                            if (selected_branch && selected_branch !== r.message.active_branch) {
                                frappe.show_alert({
                                    message: `Switching branch to ${selected_branch}.`,
                                    indicator: 'green'
                                });
                                frappe.call({
                                    method: "cen_branch_management.api.switcher.set_active_branch",
                                    args: {
                                        branch_name: selected_branch
                                    },
                                    callback: function(res) {
                                        if (!res.exc) {
                                            let url = new URL(window.location.href);
                                            url.searchParams.delete('branch');
                                            url.searchParams.delete('custom_cen_branch');
                                            url.searchParams.delete('company');
                                            window.location.href = url.toString();
                                        }
                                    }
                                });
                            }
                        });
                        return true;
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
        }
    });
});
