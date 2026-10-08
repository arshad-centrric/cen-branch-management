app_name = "cen_branch_management"
app_title = "Cen Branch Management"
app_publisher = "Centrric Innovations Private Limited"
app_description = "Centralized multi-branch management and configuration module for mapping companies, accounting dimensions, warehouses, and naming series."
app_email = "support@centrric.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "cen_branch_management",
# 		"logo": "/assets/cen_branch_management/logo.png",
# 		"title": "Cen Branch Management",
# 		"route": "/cen_branch_management",
# 		"has_permission": "cen_branch_management.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/cen_branch_management/css/cen_branch_management.css"
# app_include_js = "/assets/cen_branch_management/js/cen_branch_management.js"
app_include_js = ["/assets/cen_branch_management/js/branch_filters.js", "/assets/cen_branch_management/js/branch_switcher.js"]

# include js, css files in header of web template
# web_include_css = "/assets/cen_branch_management/css/cen_branch_management.css"
# web_include_js = "/assets/cen_branch_management/js/cen_branch_management.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "cen_branch_management/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
doctype_js = {"Branch" : "public/js/branch_custom.js", "User": "public/js/user_custom.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "cen_branch_management/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "cen_branch_management.utils.jinja_methods",
# 	"filters": "cen_branch_management.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "cen_branch_management.install.before_install"
# after_install = "cen_branch_management.install.after_install"

after_migrate = "cen_branch_management.setup.after_migrate"

# Uninstallation
# ------------

# before_uninstall = "cen_branch_management.uninstall.before_uninstall"
# after_uninstall = "cen_branch_management.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "cen_branch_management.utils.before_app_install"
# after_app_install = "cen_branch_management.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "cen_branch_management.utils.before_app_uninstall"
# after_app_uninstall = "cen_branch_management.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "cen_branch_management.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "cen_branch_management.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Branch": {
        "validate": [
            "cen_branch_management.overrides.branch_validation.validate_default_branch",
            "cen_branch_management.overrides.branch_validation.validate_default_warehouse_and_cost_center",
            "cen_branch_management.overrides.branch_validation.validate_allowed_item_groups",
            "cen_branch_management.overrides.branch_address.validate_branch_address",
        ],
        "on_update": [
            "cen_branch_management.api.permissions.sync_permissions_on_update",
            "cen_branch_management.overrides.branch_address.sync_branch_address",
            "cen_branch_management.overrides.user_default_branch.sync_default_branch_on_branch_update",
        ],
        "on_trash": [
            "cen_branch_management.overrides.branch_address.release_branch_addresses",
            "cen_branch_management.overrides.user_default_branch.clear_default_branch_on_branch_trash",
        ]
    },
    "Address": {
        "validate": "cen_branch_management.overrides.branch_address.validate_address_branch"
    },
    "User": {
        "validate": "cen_branch_management.overrides.user_default_branch.validate_user_default_branch",
        "on_update": "cen_branch_management.api.permissions.sync_permissions_on_user_update"
    }
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"cen_branch_management.tasks.all"
# 	],
# 	"daily": [
# 		"cen_branch_management.tasks.daily"
# 	],
# 	"hourly": [
# 		"cen_branch_management.tasks.hourly"
# 	],
# 	"weekly": [
# 		"cen_branch_management.tasks.weekly"
# 	],
# 	"monthly": [
# 		"cen_branch_management.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "cen_branch_management.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "cen_branch_management.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "cen_branch_management.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
override_doctype_dashboards = {
    "Company": "cen_branch_management.overrides.company_dashboard.get_data"
}

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["cen_branch_management.utils.before_request"]
# after_request = ["cen_branch_management.utils.after_request"]

# Job Events
# ----------
# before_job = ["cen_branch_management.utils.before_job"]
# after_job = ["cen_branch_management.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"cen_branch_management.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

after_migrate = "cen_branch_management.setup.after_migrate"
on_login = "cen_branch_management.api.switcher.initialize_session_branch"
