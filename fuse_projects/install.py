"""The Fuse Projects workspace, and the fields that hold a project's Intacct identity.

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
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from fuse_projects.registry import MODULE_KEY

# Custom fields rather than edits to ERPNext, so they survive an upgrade. They exist for
# one reason: to hold the Intacct identity of a record, so the next sync finds it again
# without guessing from the name — and so a movement can name a project Intacct will
# accept. Re-applied on every migrate, because a field added in a later release is
# otherwise never created on a site that already has the app.
CUSTOM_FIELDS = {
	"Project": [
		{
			"fieldname": "custom_intacct_section",
			"fieldtype": "Section Break",
			"label": "Intacct",
			"insert_after": "project_name",
			"collapsible": 1,
		},
		{
			"fieldname": "custom_intacct_project_id",
			"fieldtype": "Data",
			"label": "Intacct Project ID",
			"insert_after": "custom_intacct_section",
			"read_only": 1,
			"unique": 1,
			"description": "Intacct PROJECTID. What a movement allocated to this project sends.",
		},
		{
			"fieldname": "custom_intacct_recordno",
			"fieldtype": "Data",
			"label": "Intacct RECORDNO",
			"insert_after": "custom_intacct_project_id",
			"read_only": 1,
			"description": "Immutable — survives the project being renamed in Intacct.",
		},
		{
			"fieldname": "custom_intacct_project_status",
			"fieldtype": "Data",
			"label": "Intacct Project Status",
			"insert_after": "custom_intacct_recordno",
			"read_only": 1,
			"description": "Intacct PROJECTSTATUS, verbatim. Client-defined, so it is shown rather than translated into an ERPNext status.",
		},
		{
			"fieldname": "custom_intacct_customer_id",
			"fieldtype": "Data",
			"label": "Intacct Customer ID",
			"insert_after": "custom_intacct_project_status",
			"read_only": 1,
			"description": "Recorded, not linked — customers are not mirrored from Intacct yet.",
		},
		{
			"fieldname": "custom_intacct_parent_id",
			"fieldtype": "Data",
			"label": "Intacct Parent Project",
			"insert_after": "custom_intacct_customer_id",
			"read_only": 1,
			"description": "PARENTID. ERPNext Projects are not a tree, so the hierarchy is recorded here rather than rebuilt.",
		},
	],
	"Task": [
		{
			"fieldname": "custom_intacct_section",
			"fieldtype": "Section Break",
			"label": "Intacct",
			"insert_after": "subject",
			"collapsible": 1,
		},
		{
			"fieldname": "custom_intacct_task_id",
			"fieldtype": "Data",
			"label": "Intacct Task ID",
			"insert_after": "custom_intacct_section",
			"read_only": 1,
			"description": "Intacct TASKID. NOT unique on its own — it repeats across projects, so the pair with the project below is the key.",
		},
		{
			"fieldname": "custom_intacct_project_id",
			"fieldtype": "Data",
			"label": "Intacct Project ID",
			"insert_after": "custom_intacct_task_id",
			"read_only": 1,
		},
		{
			"fieldname": "custom_intacct_recordno",
			"fieldtype": "Data",
			"label": "Intacct RECORDNO",
			"insert_after": "custom_intacct_project_id",
			"read_only": 1,
			"description": "Also what PARENTKEY points at on a child task. The key the progress write-back updates on — TASKID repeats across projects and is not one.",
		},
		{
			"fieldname": "custom_intacct_pushed_on",
			"fieldtype": "Datetime",
			"label": "Progress Sent to Intacct",
			"insert_after": "custom_intacct_recordno",
			"read_only": 1,
		},
	],
	# Time booked in the field. The key's presence is what stops a timesheet being sent
	# twice — the same guard the stock postings use.
	"Timesheet": [
		{
			"fieldname": "custom_intacct_section",
			"fieldtype": "Section Break",
			"label": "Intacct",
			"insert_after": "employee_name",
			"collapsible": 1,
		},
		{
			"fieldname": "custom_intacct_key",
			"fieldtype": "Data",
			"label": "Intacct Key",
			"insert_after": "custom_intacct_section",
			"read_only": 1,
			"allow_on_submit": 1,
			"description": "Key of the Intacct timesheet this created. Its presence blocks a second send.",
		},
		{
			"fieldname": "custom_intacct_posted_on",
			"fieldtype": "Datetime",
			"label": "Posted to Intacct",
			"insert_after": "custom_intacct_key",
			"read_only": 1,
			"allow_on_submit": 1,
		},
	],
	# Employees are NOT mirrored from Intacct, so this is a mapping someone makes once per
	# person. Editable, unlike every other Intacct ID Fuse holds — there is no sync to
	# overwrite it, and time cannot be booked without it.
	"Employee": [
		{
			"fieldname": "custom_intacct_employee_id",
			"fieldtype": "Data",
			"label": "Intacct Employee ID",
			"insert_after": "company",
			"description": "EMPLOYEEID in Intacct. Time booked by this person is refused until it is set — the wrong employee's hours on a project is a billing error, not a typo, so it is never guessed from a name.",
		},
	],
	# Intacct's "what kind of hour is this". A company that does not use time items leaves
	# this empty and nothing is sent.
	"Activity Type": [
		{
			"fieldname": "custom_intacct_item_id",
			"fieldtype": "Data",
			"label": "Intacct Time Item",
			"insert_after": "activity_type",
			"description": "ITEMID of the Intacct time item this activity books against, where the company uses them.",
		},
	],
	"Intacct Settings": [
		{
			"fieldname": "post_project_updates",
			"fieldtype": "Check",
			"label": "Post Project Updates",
			"insert_after": "post_movements",
			"description": "Send task progress and booked time back to Intacct. Off by default: a site mirrors projects long before anyone decides ERPNext should be the thing that moves a task on. The task master stays Intacct's either way — Fuse never creates or deletes one.",
		},
		{
			"fieldname": "projects_from_intacct",
			"fieldtype": "Check",
			"label": "Lock Project Creation in Fuse",
			"default": "1",
			"insert_after": "post_project_updates",
			"description": "On: the New button is hidden on Projects and an insert is refused — the project sync is the only thing that may create one. A project invented here has no PROJECTID, so nothing booked against it could ever reach Intacct.\n\nOnly bites where the connection above is enabled. A site running Projects as an ERPNext-only module creates them as stock ERPNext does, whatever this says.",
		},
	],
}

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
	{
		# The phone screen. On the workspace as well as on Fuse Home, because the person who
		# sets a crew up on it is at a desk, and they need to be able to show someone where
		# it is.
		"label": "Site Work",
		"type": "Page",
		"link_to": "fuse-projects-floor",
		"color": "Green",
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
	{"id": "fuse_pr_s5", "type": "shortcut", "data": {"shortcut_name": "Site Work", "col": 3}},
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

	Never fatal: the switches are a launcher preference, and a missing row costs an admin
	one click. A failed install costs the whole release.
	"""
	from fuse_core import modules

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
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
	workspace = _build()
	switch = _sync_switch()

	frappe.db.commit()
	return {
		"workspace": workspace,
		"route": "fuse-projects",
		"switch": switch,
		"shortcuts": len(SHORTCUTS),
		"links": len([link for link in LINKS if link["type"] == "Link"]),
		"custom_fields": sum(len(fields) for fields in CUSTOM_FIELDS.values()),
	}
