"""Intacct PROJECT and TASK → ERPNext Project and Task.

A one-way mirror, like every other master in Fuse. Intacct is the golden source: a
project is opened in Intacct, and ERPNext learns about it. Nothing here writes back.

Why mirror at all, rather than let people type projects into ERPNext: a movement can only
be allocated to a project Intacct will accept, and the only list of those that is ever
right is Intacct's own. A locally invented project code posts once and is rejected.

The gateway belongs to fuse_core, which this app requires. Manufacturing is NOT required:
a client can buy Projects on its own, sync it from Intacct, and never install the stock
side at all.
"""

import frappe
from fuse_core import gateway, rules
from fuse_core.gateway import val

# What we read. RECORDNO first because it is the immutable key, and the only thing that
# survives someone renaming a project in Intacct.
PROJECT_FIELDS = [
	"RECORDNO",
	"PROJECTID",
	"NAME",
	"DESCRIPTION",
	"STATUS",
	"PROJECTSTATUS",
	"PROJECTTYPE",
	"CUSTOMERID",
	"PARENTID",
	"BEGINDATE",
	"ENDDATE",
	"WHENMODIFIED",
]

TASK_FIELDS = [
	"RECORDNO",
	"TASKID",
	"NAME",
	"DESCRIPTION",
	"PROJECTID",
	"PARENTKEY",
	"TASKSTATUS",
	"WHENMODIFIED",
]

# Intacct's task status to ERPNext's. Only the three Intacct actually sets are mapped;
# anything else lands on Open rather than being guessed into a status that means something
# specific to a planner reading the list.
TASK_STATUS = {
	"not started": "Open",
	"in progress": "Working",
	"completed": "Completed",
}


def _company(company=None):
	"""The ERPNext company mirrored projects are filed under.

	Named explicitly, or inferred when there is only one — which is every Fuse site, since
	one client is one ERPNext instance is one Intacct company. Ambiguity is reported rather
	than resolved by taking the first row alphabetically.
	"""
	if company:
		return company

	companies = frappe.get_all("Company", pluck="name", limit=2)
	if len(companies) == 1:
		return companies[0]

	# Several companies, as on a demo site that runs a construction company beside the
	# manufacturing one. Mirrored projects belong to the one Intacct posts into — the only
	# company carrying an Intacct entity.
	# The field comes with fuse_manufacturing, which this app does not require.
	if frappe.get_meta("Company").has_field("custom_intacct_entity_id"):
		connected = frappe.get_all(
			"Company", filters={"custom_intacct_entity_id": ["is", "set"]}, pluck="name", limit=2
		)
		if len(connected) == 1:
			return connected[0]

	frappe.throw(
		"This site has more than one Company, so the sync cannot tell which one a mirrored "
		"project belongs to. Set the Intacct Entity ID on exactly one, or pass company=... explicitly."
	)


def _changed(doc):
	"""True when an in-memory doc differs from what is stored.

	Saving unconditionally would bump `modified` on every project on every run, turning a
	quiet daily mirror into a wall of noise in every list sorted by last change.
	"""
	if doc.is_new():
		return True

	stored = frappe.db.get_value(doc.doctype, doc.name, "*", as_dict=True) or {}
	skip = (
		"modified",
		"modified_by",
		"creation",
		"owner",
		"idx",
		"_user_tags",
		"_comments",
		"_assign",
		"_liked_by",
		"docstatus",
	)
	for field in doc.meta.get_valid_columns():
		if field in skip:
			continue
		if str(stored.get(field) or "") != str(doc.get(field) or ""):
			return True
	return False


def _unique_project_name(name, project_id, existing):
	"""A project_name ERPNext will accept.

	ERPNext puts a unique index on project_name. Intacct does not — leadertread-DEV has two
	projects both called "Internal Audit", under different PROJECTIDs, and the second one
	failed the whole sync on a duplicate key.

	The Intacct ID is appended only to the one that clashes, so the common case still reads
	as the name a person typed in Intacct. Which of the two gets suffixed depends on read
	order, which is stable (RECORDNO), so it does not move about between runs.
	"""
	taken = frappe.db.get_value("Project", {"project_name": name}, "name")
	if not taken or taken == existing:
		return name
	return f"{name} ({project_id})"


def _project_type(name):
	"""Mirror an Intacct project type, creating it the first time it is seen.

	Configuration follows the same rule as data: it comes from Intacct. Creating the row is
	not inventing anything — the value is Intacct's, and the alternative is dropping it and
	leaving the field blank on every project.
	"""
	name = (name or "").strip()
	if not name:
		return None
	if not frappe.db.exists("Project Type", name):
		frappe.get_doc({"doctype": "Project Type", "project_type": name}).insert(
			ignore_permissions=True
		)
	return name


@frappe.whitelist()
def sync_projects(company=None):
	"""Intacct PROJECT → ERPNext Project."""
	company = _company(company)

	rows = gateway.query("PROJECT", PROJECT_FIELDS, company=company)

	created = updated = 0
	for row in rows:
		project_id = val(row, "PROJECTID")
		if not project_id:
			continue

		existing = frappe.db.get_value("Project", {"custom_intacct_project_id": project_id}, "name")
		if existing:
			doc = frappe.get_doc("Project", existing)
			updated += 1
		else:
			doc = frappe.new_doc("Project")
			created += 1

		doc.project_name = _unique_project_name(val(row, "NAME") or project_id, project_id, existing)
		doc.company = company
		doc.custom_intacct_project_id = project_id
		doc.custom_intacct_recordno = val(row, "RECORDNO")
		doc.custom_intacct_project_status = val(row, "PROJECTSTATUS")
		# Recorded, not linked. Customers are not mirrored from Intacct yet, so linking this
		# to an ERPNext Customer would mean matching on a name — a guess, and the wrong
		# customer on a project is worse than no customer.
		doc.custom_intacct_customer_id = val(row, "CUSTOMERID")
		doc.custom_intacct_parent_id = val(row, "PARENTID")
		doc.project_type = _project_type(val(row, "PROJECTTYPE"))
		doc.expected_start_date = rules.intacct_date(val(row, "BEGINDATE"))
		doc.expected_end_date = rules.intacct_date(val(row, "ENDDATE"))

		# Intacct's STATUS is the record's own — active or inactive — and maps cleanly onto
		# is_active. Its PROJECTSTATUS is a client-defined text ("Tendered", "On site") that
		# no two companies use the same way, so it is recorded beside the project rather than
		# translated into Open / On hold / Completed, which would be Fuse deciding what a
		# client's own word means.
		doc.is_active = "Yes" if (val(row, "STATUS") or "").lower() == "active" else "No"

		if _changed(doc):
			doc.flags.ignore_mandatory = True
			# The one way past postings.block_project_creation. Set even on an update, so a
			# queued sync is never refused by a lock that exists to stop people, not it.
			doc.flags.from_intacct_sync = True
			doc.save(ignore_permissions=True)
		elif existing:
			updated -= 1

	return {"read": len(rows), "created": created, "updated": updated}


@frappe.whitelist()
def sync_tasks(company=None):
	"""Intacct TASK → ERPNext Task, hung off the mirrored project.

	Two passes. Intacct nests tasks by PARENTKEY — a RECORDNO — and a parent can arrive
	after its child in RECORDNO order, so parents are linked once every task exists.
	"""
	company = _company(company)

	rows = gateway.query("TASK", TASK_FIELDS, company=company)

	projects = dict(
		frappe.get_all(
			"Project",
			filters={"custom_intacct_project_id": ("is", "set")},
			fields=["custom_intacct_project_id", "name"],
			limit_page_length=0,
			as_list=True,
		)
	)

	created = updated = 0
	orphans = []
	# Intacct RECORDNO -> ERPNext Task name, for the parent pass.
	by_recordno = {}

	for row in rows:
		task_id = val(row, "TASKID")
		project_id = val(row, "PROJECTID")
		if not task_id or not project_id:
			continue

		project = projects.get(project_id)
		if not project:
			# The project has not been mirrored — usually because sync_projects has not run
			# since it was opened. Reported, not created: a task whose project ERPNext has
			# never heard of would be a second copy of the truth.
			orphans.append(f"{project_id}/{task_id}")
			continue

		# TASKID repeats across projects in Intacct, so the project is part of the key.
		existing = frappe.db.get_value(
			"Task",
			{"custom_intacct_task_id": task_id, "custom_intacct_project_id": project_id},
			"name",
		)
		if existing:
			doc = frappe.get_doc("Task", existing)
			updated += 1
		else:
			doc = frappe.new_doc("Task")
			created += 1

		doc.subject = val(row, "NAME") or task_id
		doc.project = project
		doc.company = company
		doc.custom_intacct_task_id = task_id
		doc.custom_intacct_project_id = project_id
		doc.custom_intacct_recordno = val(row, "RECORDNO")
		doc.status = TASK_STATUS.get((val(row, "TASKSTATUS") or "").strip().lower(), "Open")

		if _changed(doc):
			doc.flags.ignore_mandatory = True
			# Stops postings.on_task_insert sending a mirrored task straight back to Intacct
			# as a new one. Without this the first sync on a connected site would double
			# every task it read.
			doc.flags.from_intacct_sync = True
			doc.save(ignore_permissions=True)
		elif existing:
			updated -= 1

		recordno = val(row, "RECORDNO")
		if recordno:
			by_recordno[recordno] = doc.name

	parented = _link_parents(rows, by_recordno)

	return {
		"read": len(rows),
		"created": created,
		"updated": updated,
		"parented": parented,
		"orphans": orphans,
	}


def _link_parents(rows, by_recordno):
	"""Second pass: hang each task under its parent, now that all of them exist.

	A parent has to be marked as a group or ERPNext refuses the link. That flag is Intacct's
	structure showing through, not a decision made here.
	"""
	parented = 0
	for row in rows:
		child = by_recordno.get(val(row, "RECORDNO"))
		parent = by_recordno.get(val(row, "PARENTKEY"))
		if not child or not parent or child == parent:
			continue
		if frappe.db.get_value("Task", child, "parent_task") == parent:
			continue

		if not frappe.db.get_value("Task", parent, "is_group"):
			frappe.db.set_value("Task", parent, "is_group", 1)
		frappe.db.set_value("Task", child, "parent_task", parent)
		parented += 1

	return parented


def sync_all(company=None):
	"""Projects, then their tasks. Order matters — a task needs its project to exist."""
	return {
		"projects": sync_projects(company=company),
		"tasks": sync_tasks(company=company),
	}


@frappe.whitelist()
def enqueue_sync(company=None):
	"""Queue the project mirror to run in the background. Returns immediately."""
	frappe.only_for("System Manager")
	frappe.enqueue(
		"fuse_projects.sync.sync_all",
		queue="long",
		timeout=1800,
		job_name="fuse-projects-sync",
		company=company,
	)
	return {"queued": "projects"}


def scheduled_sync():
	"""Daily. Projects and tasks are opened and closed deliberately, not by the hour.

	No-ops when the Intacct connection is not switched on, so a site running Projects as an
	ERPNext-only module does not log a failure every night.
	"""
	try:
		cfg = gateway.settings()
	except Exception:
		return

	if not cfg.enabled:
		return

	sync_all()
