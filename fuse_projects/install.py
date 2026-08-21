"""The Fuse Projects workspace.

Wired to after_install AND after_migrate, and exposed as fuse_projects.api.setup — on
Frappe Cloud after_migrate has been observed not to fire, shipping code without the
configuration that goes with it. Everything here is idempotent.

The workspace is built from this file rather than shipped as a JSON fixture so that a
hand-edit on one client's site cannot quietly persist and make two clients differ.

Every link points at something ERPNext already ships. This app adds no doctypes and no
reports: the value is the arrangement — one Fuse-shaped page over Projects, instead of
sending a manufacturer into ERPNext's full Projects module to find four things.
"""

import json

import frappe

from fuse_projects.registry import MODULE_KEY

WORKSPACE = "Fuse Projects"

SHORTCUTS = [
	{
		# Open only. A manufacturer's finished projects pile up fast, and the count on this
		# shortcut is the number the shop floor actually looks at.
		"label": "Projects",
		"type": "DocType",
		"link_to": "Project",
		"stats_filter": json.dumps({"status": "Open"}),
		"color": "Green",
	},
	{
		"label": "Tasks",
		"type": "DocType",
		"link_to": "Task",
		"stats_filter": json.dumps({"status": ["not in", ["Completed", "Cancelled"]]}),
		"color": "Blue",
	},
	{
		# Work Orders that carry a project, not all of them — the unfiltered list is
		# already one click away on the Fuse home page, and repeating it here would make
		# this page a second Stock Control rather than a project view.
		"label": "Works Orders",
		"type": "DocType",
		"link_to": "Work Order",
		"stats_filter": json.dumps({"project": ["is", "set"]}),
		"color": "Orange",
	},
	{
		"label": "Timesheets",
		"type": "DocType",
		"link_to": "Timesheet",
		"color": "Grey",
	},
]

# Card Break rows open a card; the Link rows after one belong to it.
LINKS = [
	{"type": "Card Break", "label": "Planning"},
	{"type": "Link", "label": "Project", "link_type": "DocType", "link_to": "Project"},
	{"type": "Link", "label": "Task", "link_type": "DocType", "link_to": "Task"},
	{"type": "Link", "label": "Project Template", "link_type": "DocType", "link_to": "Project Template"},
	{"type": "Link", "label": "Project Type", "link_type": "DocType", "link_to": "Project Type"},
	{"type": "Card Break", "label": "Doing"},
	{"type": "Link", "label": "Work Order", "link_type": "DocType", "link_to": "Work Order"},
	{"type": "Link", "label": "Stock Entry", "link_type": "DocType", "link_to": "Stock Entry"},
	{"type": "Link", "label": "Timesheet", "link_type": "DocType", "link_to": "Timesheet"},
	{"type": "Card Break", "label": "Reports"},
	{"type": "Link", "label": "Project Summary", "link_type": "Report", "link_to": "Project Summary",
	 "is_query_report": 1},
	# ERPNext's own, and it is the right report: cost of items purchased for, issued to and
	# delivered against each project. Writing a Fuse version would be a second answer to a
	# question already answered.
	{"type": "Link", "label": "Project wise Stock Tracking", "link_type": "Report",
	 "link_to": "Project wise Stock Tracking", "is_query_report": 1},
	{"type": "Link", "label": "Delayed Tasks Summary", "link_type": "Report",
	 "link_to": "Delayed Tasks Summary", "is_query_report": 1},
	{"type": "Link", "label": "Daily Timesheet Summary", "link_type": "Report",
	 "link_to": "Daily Timesheet Summary", "is_query_report": 1},
]

# Every `shortcut_name` must match a SHORTCUTS label and every `card_name` a Card Break
# label in LINKS, exactly — a block naming something that does not exist renders as an
# empty box.
CONTENT = [
	{"id": "fuse_pr_head", "type": "header",
	 "data": {"text": '<span class="h4"><b>Projects</b></span>', "col": 12}},
	{"id": "fuse_pr_s1", "type": "shortcut", "data": {"shortcut_name": "Projects", "col": 3}},
	{"id": "fuse_pr_s2", "type": "shortcut", "data": {"shortcut_name": "Tasks", "col": 3}},
	{"id": "fuse_pr_s3", "type": "shortcut", "data": {"shortcut_name": "Works Orders", "col": 3}},
	{"id": "fuse_pr_s4", "type": "shortcut", "data": {"shortcut_name": "Timesheets", "col": 3}},
	{"id": "fuse_pr_c1", "type": "card", "data": {"card_name": "Planning", "col": 4}},
	{"id": "fuse_pr_c2", "type": "card", "data": {"card_name": "Doing", "col": 4}},
	{"id": "fuse_pr_c3", "type": "card", "data": {"card_name": "Reports", "col": 4}},
]


def _build():
	"""Create or refresh the workspace, from this file every time."""
	if frappe.db.exists("Workspace", WORKSPACE):
		doc = frappe.get_doc("Workspace", WORKSPACE)
		doc.shortcuts = []
		doc.links = []
		# Roles too. A leftover role restriction is not hidden gracefully — the desk's
		# show_page gets undefined and throws, taking the sidebar down with it. Fuse
		# workspaces are unrestricted on purpose: what a user may DO is decided by
		# document permissions, and hiding the page as well only looks broken.
		doc.roles = []
	else:
		doc = frappe.new_doc("Workspace")
		doc.name = WORKSPACE

	doc.label = WORKSPACE
	doc.title = "Projects"
	# Projects and erpnext, NOT this app's own module. A workspace is only in a user's
	# allowed list if they have access to its module, and a non-admin has no documents in
	# Fuse Projects — so the route falls through to a Page lookup and answers "Page
	# fuse-projects does not exist". It works for Administrator, who bypasses all of it,
	# which is exactly how fuse_theme's Stock Control workspace reached a client demo
	# broken on 2026-08-19.
	doc.module = "Projects"
	doc.app = "erpnext"
	doc.icon = "project"
	doc.public = 1
	doc.is_hidden = 0
	doc.content = json.dumps(CONTENT)
	# After Fuse (0) and Stock Control (1), both owned by fuse_theme.
	doc.sequence_id = 2

	for shortcut in SHORTCUTS:
		doc.append("shortcuts", dict(shortcut))
	for link in LINKS:
		doc.append("links", dict(link))

	doc.flags.ignore_permissions = True
	doc.flags.ignore_links = True
	doc.save(ignore_permissions=True)
	return doc.name


def _sync_switch():
	"""Get the Projects switch into Active Modules without waiting for the next migrate.

	fuse_manufacturing rebuilds that table on every migrate and would pick this app up on
	its own. Calling it here means the switch is there the moment this app is installed,
	which is the difference between a client seeing the tile and being told to wait for a
	deploy.

	Silent when the integration app is absent: Projects must install on a site that has
	no Intacct integration at all, and on such a site there is no table to seed.
	"""
	try:
		from fuse_manufacturing import modules
	except ImportError:
		return None

	try:
		modules.sync_modules()
	except Exception:
		# Seeding a settings table must never be the reason an install fails — the same
		# reasoning as sync_modules' own. A missing row costs an admin one click.
		frappe.log_error(
			title="Fuse Projects: could not seed the Projects switch", message=frappe.get_traceback()
		)
		return None

	return MODULE_KEY


def after_install():
	"""Put this app's configuration in step with this version of it."""
	workspace = _build()
	switch = _sync_switch()

	frappe.db.commit()
	return {
		"workspace": workspace,
		"route": "fuse-projects",
		"switch": switch,
		"shortcuts": len(SHORTCUTS),
		"links": len([link for link in LINKS if link["type"] == "Link"]),
	}
