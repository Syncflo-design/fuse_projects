"""Project screens for a phone — the server side.

The same decision the shop-floor screens were built on (fuse_manufacturing/floor.py):
ERPNext's forms are desk-shaped, and someone on site with one hand free wants a list, a
number and a green button.

Nothing here posts to Intacct directly. Setting a status saves an ordinary Task and
logging time submits an ordinary Timesheet, so `postings.on_task_update` and
`postings.on_timesheet_submit` fire exactly as they do from the desk. One write-back path,
two front doors — which is what stops the phone and the desk drifting apart.
"""

import frappe
from frappe.utils import flt, get_datetime, now_datetime

from fuse_projects.postings import TASK_STATUS_OUT

# What a phone screen can set. ERPNext's other statuses — Pending Review, Overdue,
# Template — are either derived or a desk decision, and none of them mean anything to
# Intacct, so the field cannot set them.
FLOOR_STATUSES = list(TASK_STATUS_OUT)

# A phone shows about this many rows before it becomes scrolling rather than choosing.
LIST_LIMIT = 30


def _guard(doctype, permission="write"):
	"""Refuse anyone who could not do it from the desk either.

	A whitelisted method is callable by any logged-in user, so the screen's own navigation
	is not a permission check. The save would catch it later — this catches it before
	anyone has typed anything.
	"""
	if not frappe.has_permission(doctype, permission):
		frappe.throw(f"You do not have permission to update {doctype.lower()}s.")


@frappe.whitelist()
def context():
	"""What the screen needs to draw itself: the projects with work still open."""
	projects = frappe.get_all(
		"Project",
		filters={"status": "Open", "is_active": "Yes"},
		fields=["name", "project_name", "custom_intacct_project_id"],
		order_by="project_name asc",
		limit_page_length=LIST_LIMIT,
	)
	return {
		"projects": projects,
		"statuses": FLOOR_STATUSES,
		"user": frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user,
		# Whether time logging is offered at all. An Employee record is what carries the
		# Intacct ID, and a user who is not an employee cannot book time — better to hide
		# the button than to fail at the end of the form.
		"employee": frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name"),
		# Whether to say the word "Intacct" on screen at all.
		#
		# On a site with no connection every task would be badged "Not in Intacct", which
		# is a true statement nobody asked for — it makes an unconfigured site look broken,
		# and on a demo it puts the integration front and centre when the point is what
		# Fuse does on its own. Where a connection DOES exist, the badge earns its place:
		# it is the first thing an accountant asks about.
		"intacct": _intacct_connected(),
	}


def _intacct_connected():
	"""Whether this site actually talks to Intacct.

	Reads the settings directly rather than through the gateway, because asking the
	gateway would mean opening a session to answer a question about the user interface.
	"""
	if not frappe.db.exists("DocType", "Intacct Settings"):
		return False
	return bool(frappe.db.get_single_value("Intacct Settings", "enabled"))


@frappe.whitelist()
def tasks(project=None, search=None):
	"""Open tasks, newest first, optionally narrowed to one project or a search."""
	filters = {"status": ("not in", ("Completed", "Cancelled"))}
	if project:
		filters["project"] = project

	or_filters = None
	if search:
		or_filters = {"subject": ("like", f"%{search}%"), "name": ("like", f"%{search}%")}

	return frappe.get_all(
		"Task",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"subject",
			"status",
			"progress",
			"project",
			"custom_intacct_task_id",
			"custom_intacct_recordno",
		],
		order_by="modified desc",
		limit_page_length=LIST_LIMIT,
	)


@frappe.whitelist()
def set_status(task, status, progress=None):
	"""Move a task on, from the field.

	Saved as an ordinary Task so the write-back fires the same way it does from the desk.
	The status is checked against the screen's own list rather than trusted: a whitelisted
	method is a public endpoint, whatever the buttons offer.
	"""
	_guard("Task")

	if status not in FLOOR_STATUSES:
		frappe.throw(f"{status} is not a status this screen can set.")

	doc = frappe.get_doc("Task", task)
	doc.status = status
	if progress not in (None, ""):
		progress = flt(progress)
		if progress < 0 or progress > 100:
			frappe.throw("Percent complete has to be between 0 and 100.")
		doc.progress = progress

	doc.save()
	return {"task": doc.name, "status": doc.status, "progress": doc.progress}


@frappe.whitelist()
def create_task(project, subject, description=None):
	"""Raise a task found on site.

	Inserted as an ordinary Task, so `postings.on_task_insert` creates it in Intacct under
	the same project and hands back its TASKID. From that moment it is tracked and completed
	like any other — there is no second class of task.

	Unplanned work is the normal case out here, not the exception. The alternative is a
	foreman writing it on his hand until he finds a desk.
	"""
	_guard("Task", "create")

	subject = (subject or "").strip()
	if not subject:
		frappe.throw("Give the task a name.")
	if not frappe.db.exists("Project", project):
		frappe.throw(f"{project} is not a project on this site.")

	doc = frappe.new_doc("Task")
	doc.subject = subject
	doc.project = project
	doc.status = "Open"
	doc.description = description
	doc.insert()
	doc.reload()

	return {
		"task": doc.name,
		"subject": doc.subject,
		# What an accountant will ask for. Empty on a site with no connection, which is the
		# honest answer there.
		"intacct_task_id": doc.get("custom_intacct_task_id"),
	}


@frappe.whitelist()
def log_time(task, hours, notes=None, activity_type=None):
	"""Book hours against a task, as a submitted Timesheet.

	Submitted immediately rather than left as a draft: the person on site is recording
	something that has already happened, and a draft would sit there unbooked until
	somebody in an office noticed it.
	"""
	_guard("Timesheet", "create")

	hours = flt(hours)
	if hours <= 0:
		frappe.throw("Enter how many hours were worked.")

	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if not employee:
		frappe.throw("You are not linked to an Employee record, so time cannot be booked for you.")

	task_doc = frappe.get_doc("Task", task)
	if not task_doc.project:
		frappe.throw(f"{task} is not attached to a project, so time cannot be booked against it.")

	# Ended now, started `hours` ago. ERPNext wants a window and the field wants one number;
	# working backwards from now is the honest reading of "I have just done three hours".
	finished = now_datetime()
	started = get_datetime(frappe.utils.add_to_date(finished, hours=-hours))

	doc = frappe.new_doc("Timesheet")
	doc.employee = employee
	doc.company = frappe.db.get_value("Project", task_doc.project, "company")
	doc.append(
		"time_logs",
		{
			"activity_type": activity_type,
			"from_time": started,
			"to_time": finished,
			"hours": hours,
			"project": task_doc.project,
			"task": task_doc.name,
			"description": notes,
		},
	)
	doc.insert()
	doc.submit()

	return {
		"timesheet": doc.name,
		"hours": hours,
		"task": task_doc.name,
		"posted": bool(doc.get("custom_intacct_key")),
	}
