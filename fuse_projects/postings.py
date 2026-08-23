"""What Projects sends back to Intacct.

Two writes, and they are deliberately different in kind:

  * **Task progress.** The task MASTER is Intacct's — Fuse never creates, renames or
    deletes a task. All this does is move the marker: status, and observed percent
    complete. An update keyed on RECORDNO, which is why the sync stores it.
  * **Time.** A timesheet entry carrying the project and task, so hours booked in the
    field reach the same project costing the accountant reads.

Neither is definition-driven, so neither appears in the Transactions table on Intacct
Settings. There is nothing for a client to map — Intacct has one TASK object and one
timesheet, whatever the company calls its stock documents.

**Both are gated OFF by default** (`post_project_updates` on Intacct Settings). The XML
shapes here are built from what the gateway reports the objects hold; no write has been
posted to a live company yet. Switching it on is a deliberate act, taken by someone who
is about to watch the first one land.
"""

import xml.etree.ElementTree as ET

import frappe
from fuse_core import gateway

# ERPNext status → Intacct TASKSTATUS. The reverse of sync.TASK_STATUS, minus the ones
# Intacct has no word for.
#
# Overdue and Pending Review are ERPNext's own ideas, and Cancelled has no counterpart on
# an Intacct task at all. A status with no mapping leaves Intacct's marker where it is
# rather than pushing something that means a different thing — the task master is theirs,
# and a wrong status on it is worse than a stale one.
TASK_STATUS_OUT = {
	"Open": "Not Started",
	"Working": "In Progress",
	"Completed": "Completed",
}


def _enabled():
	"""Whether this site posts project updates at all.

	Off by default and checked on every write. A site can mirror projects for months
	before anyone decides ERPNext should be the thing that moves a task on.
	"""
	cfg = gateway.settings()
	return bool(cfg.enabled and cfg.get("post_project_updates"))


def _text(parent, tag, value):
	element = ET.SubElement(parent, tag)
	element.text = str(value)
	return element


# ──────────────────────────────────────────────────────────────────────────────
# Projects are opened in Intacct
# ──────────────────────────────────────────────────────────────────────────────


def block_project_creation(doc, method=None):
	"""Refuse a project started in Fuse where Intacct owns them.

	A project invented here has no PROJECTID, so nothing booked against it can ever reach
	Intacct — the time and the materials land in ERPNext and stop there. Worse, it looks
	identical to a mirrored one in every list.

	Two conditions, both required. The lock has to be on, AND the site has to actually be
	connected: on a site with no Intacct connection there is nowhere else to open a project,
	so refusing here would leave a client unable to create one at all.

	The sync sets `from_intacct_sync`, which is the only way past this.
	"""
	if doc.flags.get("from_intacct_sync"):
		return
	# A mirrored project carries the ID the sync wrote. Belt and braces: if the flag is ever
	# lost in a queued job, this still recognises the sync's own work.
	if doc.get("custom_intacct_project_id"):
		return

	settings = frappe.get_cached_doc("Intacct Settings")
	if not (settings.enabled and settings.get("projects_from_intacct")):
		return

	frappe.throw(
		"Projects are opened in Intacct on this site, so one cannot be created here.\n\n"
		"Open it in Intacct and the next project sync brings it across, with its tasks. An "
		"administrator can change this under Intacct Settings if projects should be kept in "
		"Fuse instead.",
		title="Projects come from Intacct",
	)


# ──────────────────────────────────────────────────────────────────────────────
# Task progress
# ──────────────────────────────────────────────────────────────────────────────


def build_task_update_xml(*, recordno, status=None, percent_complete=None):
	"""An `<update><TASK>` function element.

	Keyed on RECORDNO, not TASKID: TASKID repeats across projects, so it is not a key on
	its own — the same reason the sync stores both.

	Only the fields being changed are sent. An update that names every field would push
	blanks over values a project accountant set in Intacct, which is exactly the kind of
	silent overwrite the mirror exists to avoid.
	"""
	function = ET.Element("function")
	update = ET.SubElement(function, "update")
	task = ET.SubElement(update, "TASK")
	_text(task, "RECORDNO", recordno)

	if status:
		_text(task, "TASKSTATUS", status)
	# Observed, not calculated. PERCENTCOMPLETE is Intacct's own roll-up from time booked
	# against the task; writing to it would fight its own arithmetic. OBSPERCENTCOMPLETE is
	# the field for "the person on site says it is half done".
	if percent_complete is not None:
		_text(task, "OBSPERCENTCOMPLETE", percent_complete)

	return function


def build_task_create_xml(*, project_id, name, status=None, description=None):
	"""A `<create><TASK>` function element.

	No TASKID: Intacct numbers a task within its project (the sample task is `000001` under
	`PRJ-000001`), and inventing one here would either collide or leave a gap in their
	sequence. The number comes back on the read-after-write.

	A task created this way is a real Intacct task from that moment — it costs, it reports,
	and it is the same object a project accountant would have typed. That is the point: an
	unplanned job found on site should not become a private ERPNext note.
	"""
	function = ET.Element("function")
	create = ET.SubElement(function, "create")
	task = ET.SubElement(create, "TASK")

	_text(task, "PROJECTID", project_id)
	_text(task, "NAME", name)
	if status:
		_text(task, "TASKSTATUS", status)
	if description:
		_text(task, "DESCRIPTION", description)

	return function


@frappe.whitelist()
def push_new_task(task, dry_run=False):
	"""Create an ERPNext Task in Intacct, under its mirrored project.

	Read back afterwards for the TASKID Intacct assigned. Without it the task is half
	mirrored: the progress write-back would work (it keys on RECORDNO) but nobody could
	match the row to what they see in Intacct, and the next sync would create a duplicate.
	"""
	doc = frappe.get_doc("Task", task)

	if doc.get("custom_intacct_recordno"):
		return {"posted": False, "reason": "Already in Intacct."}

	project_id = (
		frappe.db.get_value("Project", doc.project, "custom_intacct_project_id")
		if doc.project
		else None
	)
	if not project_id:
		# A task on a project Intacct has never heard of has nowhere to go. Not a fault —
		# it is what every task looks like on a site with no connection.
		return {"posted": False, "reason": "Its project is not mirrored from Intacct."}

	function = build_task_create_xml(
		project_id=project_id,
		name=doc.subject,
		status=TASK_STATUS_OUT.get(doc.status),
		description=doc.get("description"),
	)

	if dry_run:
		return {"posted": False, "dry_run": ET.tostring(function, encoding="unicode")}

	recordno = gateway.execute(function, reference=("Task", doc.name), purpose="task_create")

	task_id = _task_id_for(recordno)
	frappe.db.set_value(
		"Task",
		doc.name,
		{
			"custom_intacct_recordno": recordno,
			"custom_intacct_task_id": task_id,
			"custom_intacct_project_id": project_id,
			"custom_intacct_pushed_on": frappe.utils.now(),
		},
		update_modified=False,
	)
	return {"posted": True, "recordno": recordno, "task_id": task_id, "project_id": project_id}


def _task_id_for(recordno):
	"""The TASKID Intacct assigned, read back after the create.

	Its own call rather than trusting the create's response: the generic `<create>` returns
	the object it made, but which fields come back has varied by object, and the number is
	the one thing a person will use to find this task in Intacct.

	Returns None rather than raising — the task IS created by this point, and failing here
	would leave the caller thinking it was not.
	"""
	try:
		rows = gateway.query(
			"TASK",
			["RECORDNO", "TASKID"],
			filter_xml=f"<equalto><field>RECORDNO</field><value>{recordno}</value></equalto>",
			page_size=1,
		)
	except Exception:
		frappe.log_error(
			title=f"Fuse Projects: created Intacct task {recordno} but could not read its TASKID",
			message=frappe.get_traceback(),
		)
		return None

	return gateway.val(rows[0], "TASKID") if rows else None


def on_task_insert(doc, method=None):
	"""Send a task raised here — on site, usually — to Intacct as a new task.

	Silent when the site does not post project updates, when the task came from the sync,
	or when its project is not mirrored. Warns rather than raises on failure, for the same
	reason as the progress push: someone in the field recording an unplanned job must not
	be stopped by a gateway that is having a bad afternoon. The task stands locally and can
	be pushed again by hand.
	"""
	if doc.flags.get("from_intacct_sync") or doc.get("custom_intacct_recordno"):
		return
	if not _enabled():
		return

	try:
		push_new_task(doc.name)
	except Exception:
		frappe.log_error(
			title=f"Fuse Projects: could not create {doc.name} in Intacct",
			message=frappe.get_traceback(),
		)
		frappe.msgprint(
			"Saved here, but Intacct has not accepted the new task yet. Nothing booked "
			"against it will reach project costing until it does.",
			indicator="orange",
			alert=True,
		)


@frappe.whitelist()
def push_task_status(task, dry_run=False):
	"""Send one ERPNext Task's progress to Intacct.

	Returns what it did rather than raising when there is nothing to do: a task that was
	never mirrored, or whose status has no Intacct equivalent, is not a fault.
	"""
	doc = frappe.get_doc("Task", task)

	recordno = doc.get("custom_intacct_recordno")
	if not recordno:
		return {"posted": False, "reason": "Not a mirrored task — it does not exist in Intacct."}

	status = TASK_STATUS_OUT.get(doc.status)
	progress = doc.get("progress")
	if not status and progress in (None, ""):
		return {"posted": False, "reason": f"Nothing to send for status {doc.status}."}

	function = build_task_update_xml(
		recordno=recordno,
		status=status,
		percent_complete=progress if progress not in (None, "") else None,
	)

	if dry_run:
		return {"posted": False, "dry_run": ET.tostring(function, encoding="unicode")}

	key = gateway.execute(
		function,
		reference=("Task", doc.name),
		purpose="task_status",
	)
	frappe.db.set_value(
		"Task", doc.name, "custom_intacct_pushed_on", frappe.utils.now(), update_modified=False
	)
	return {"posted": True, "key": key, "status": status, "percent_complete": progress}


def on_task_update(doc, method=None):
	"""Push a task's progress when it changes, and only then.

	Silent when the site does not post project updates, when the task is not mirrored, or
	when nothing that Intacct cares about actually moved. A Task is saved for all sorts of
	reasons — a comment, an assignment, a date — and none of them are worth a round trip.

	Deliberately NOT on_submit-style enforcement: Task is not a submittable document, and a
	failed push must not stop someone recording progress in ERPNext. Stock is the opposite
	way round — there, Intacct posts first and a rejection rolls the movement back, because
	two systems disagreeing about stock that has physically moved is the fault the whole
	design exists to prevent. A task marker is not stock.
	"""
	if not doc.get("custom_intacct_recordno"):
		return
	if not _enabled():
		return

	before = doc.get_doc_before_save()
	if before is not None and before.status == doc.status and before.get("progress") == doc.get("progress"):
		return

	try:
		push_task_status(doc.name)
	except Exception:
		frappe.log_error(
			title=f"Fuse Projects: could not send {doc.name} to Intacct",
			message=frappe.get_traceback(),
		)
		frappe.msgprint(
			"Saved here, but Intacct did not accept the progress update. It will be sent "
			"again the next time this task changes.",
			indicator="orange",
			alert=True,
		)


# ──────────────────────────────────────────────────────────────────────────────
# Time
# ──────────────────────────────────────────────────────────────────────────────


def build_timesheet_xml(*, employee_id, begin_date, entries, description=None):
	"""A `<create_timesheet>` function element.

	One timesheet per ERPNext Timesheet, with one entry per time log. Intacct groups
	entries under an employee and a period; ERPNext groups them under a document that
	already has both, so the shapes line up without inventing a grouping.
	"""
	function = ET.Element("function")
	timesheet = ET.SubElement(function, "create_timesheet")

	_text(timesheet, "employeeid", employee_id)
	_text(timesheet, "begindate", begin_date)
	if description:
		_text(timesheet, "description", description)

	items = ET.SubElement(timesheet, "timesheetentries")
	for entry in entries:
		line = ET.SubElement(items, "timesheetentry")
		_text(line, "entrydate", entry["entry_date"])
		_text(line, "qty", entry["hours"])
		if entry.get("project_id"):
			_text(line, "projectid", entry["project_id"])
		if entry.get("task_id"):
			_text(line, "taskid", entry["task_id"])
		# The time item — Intacct's "what kind of hour is this". Sent only where the site
		# has mapped one onto the Activity Type; a company that does not use time items has
		# nothing to send and should not have a blank one invented for it.
		if entry.get("item_id"):
			_text(line, "itemid", entry["item_id"])
		if entry.get("notes"):
			_text(line, "notes", entry["notes"])

	return function


def _timesheet_entries(doc):
	"""One Intacct entry per ERPNext time log, refusing anything Intacct cannot place.

	A log with no project is refused rather than sent bare. Time that reaches Intacct
	attached to nothing is worse than time that stayed in ERPNext: it lands in the books
	and has to be found and unpicked by hand.
	"""
	entries, problems = [], []

	for row in doc.time_logs or []:
		project_id = (
			frappe.db.get_value("Project", row.project, "custom_intacct_project_id")
			if row.project
			else None
		)
		if not project_id:
			problems.append(f"Row {row.idx}: no Intacct project — time cannot be booked against nothing.")
			continue

		task_id = (
			frappe.db.get_value("Task", row.task, "custom_intacct_task_id") if row.task else None
		)
		item_id = (
			frappe.db.get_value("Activity Type", row.activity_type, "custom_intacct_item_id")
			if row.activity_type
			else None
		)

		entries.append(
			{
				"entry_date": frappe.utils.getdate(row.from_time).isoformat(),
				"hours": row.hours,
				"project_id": project_id,
				"task_id": task_id,
				"item_id": item_id,
				"notes": row.description,
			}
		)

	return entries, problems


@frappe.whitelist()
def post_timesheet(timesheet, dry_run=False):
	"""Send one submitted ERPNext Timesheet to Intacct."""
	doc = frappe.get_doc("Timesheet", timesheet)

	if doc.get("custom_intacct_key"):
		frappe.throw(f"{doc.name} has already been sent to Intacct as {doc.custom_intacct_key}.")

	employee_id = (
		frappe.db.get_value("Employee", doc.employee, "custom_intacct_employee_id")
		if doc.employee
		else None
	)
	if not employee_id:
		# Employees are not mirrored from Intacct, so this is a mapping someone has to make
		# once per person. Refused rather than guessed from a name — the wrong employee's
		# time on a project is a billing error, not a typo.
		frappe.throw(
			f"{doc.employee or 'This timesheet'} has no Intacct Employee ID, so the time "
			"cannot be booked. Set it on the Employee record."
		)

	entries, problems = _timesheet_entries(doc)
	if problems:
		frappe.throw(f"{doc.name} cannot be sent to Intacct:\n\n" + "\n".join(problems))
	if not entries:
		return {"posted": False, "reason": "No time logs to send."}

	function = build_timesheet_xml(
		employee_id=employee_id,
		begin_date=min(entry["entry_date"] for entry in entries),
		entries=entries,
		description=f"Fuse {doc.name}",
	)

	if dry_run:
		return {"posted": False, "entries": len(entries), "dry_run": ET.tostring(function, encoding="unicode")}

	key = gateway.execute(
		function,
		reference=("Timesheet", doc.name),
		purpose="timesheet",
	)
	doc.db_set("custom_intacct_key", key, update_modified=False)
	doc.db_set("custom_intacct_posted_on", frappe.utils.now(), update_modified=False)
	return {"posted": True, "key": key, "entries": len(entries)}


def on_timesheet_submit(doc, method=None):
	"""Send the time when the timesheet is submitted.

	Raises, unlike the task push. A timesheet is a submitted document with a definite
	moment of record, and hours that ERPNext believes are booked while Intacct has never
	seen them is the same divergence the stock rules exist to prevent — small, and
	invisible until someone bills against it.
	"""
	if not _enabled():
		return
	post_timesheet(doc.name)
