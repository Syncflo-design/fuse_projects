"""Construction commercials: the part of Fuse Projects that talks money with Intacct.

Three movements, each posted to Intacct at the moment it is approved — no file export, no
watched folder, no overnight batch in between:

  * Award. A priced BOQ becomes an Intacct PROJECT with one TASK per BOQ section and the
    BOQ total as its projected cost. The project key is set once, on the BOQ, and never
    re-keyed.
  * Subcontract certificate -> AP bill. Gross to the cost account on the project,
    contra-charges back against the same project, retention to the retention payable account.
  * Client valuation -> AR invoice. Gross to revenue on the project; client retention to the
    retention receivable account rather than invoiced.

Intacct posts first, as everywhere in Fuse: a rejection stops the submit.

Retention is a negative line to a balance-sheet account rather than Intacct retainage.
Retainage is per-company AP/AR configuration; a negative line to a liability posts the same
way in every company. The retention line carries no project, so the project's cost in
Intacct is gross less contra — the number the cost report reconciles to.

leadertread-DEV has no task dimension on AP or AR lines (APBILLITEM has no TASKID, and
ARINVOICEITEM refuses one). So the BOQ section is held by Fuse and the project by Intacct;
the cost report joins the two.

Subcontractors and clients are identified by the Intacct IDs fuse_manufacturing's master
sync writes onto Supplier and Customer. A party Intacct has never heard of stops the
posting; it is never created from here.
"""

import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

import frappe
from frappe.utils import add_days, cint, flt, getdate, now, nowdate
from fuse_core import gateway
from fuse_core.gateway import val

PROJECT_FIELDS = ["RECORDNO", "PROJECTID", "NAME", "PROJECTSTATUS", "CUSTOMERID"]
TASK_FIELDS = ["RECORDNO", "TASKID", "NAME", "PROJECTID"]

# EPC work is built for a client and billed. IPP plant is NSE's own and capitalises at COD.
PROJECT_CATEGORY = {"EPC": "Contract", "IPP": "Capitalized"}

# Intacct Settings fields this module posts with, and what to call each in a message.
ACCOUNTS = {
	"construction_cost_account": "Subcontract Cost Account",
	"retention_payable_account": "Retention Payable Account",
	"revenue_account": "Valuation Revenue Account",
	"retention_receivable_account": "Retention Receivable Account",
}


# ──────────────────────────────────────────────────────────────────────────────
# Shared
# ──────────────────────────────────────────────────────────────────────────────


def _text(parent, tag, value):
	element = ET.SubElement(parent, tag)
	element.text = str(value)
	return element


def _us_date(value):
	"""The generic API reads MM/DD/YYYY whatever the company's locale."""
	return getdate(value).strftime("%m/%d/%Y")


def _legacy_date(parent, tag, value):
	day = getdate(value)
	element = ET.SubElement(parent, tag)
	_text(element, "year", day.year)
	_text(element, "month", f"{day.month:02d}")
	_text(element, "day", f"{day.day:02d}")
	return element


def _money(value):
	return f"{flt(value, 2):.2f}"


def posting_settings():
	"""Intacct Settings, refusing to post until every account is named."""
	cfg = gateway.settings()
	missing = [label for field, label in ACCOUNTS.items() if not cfg.get(field)]
	if missing:
		frappe.throw(
			"Set these under Construction Postings in Intacct Settings first: " + ", ".join(missing),
			title="Accounts not set",
		)
	return cfg


def find_one(object_name, fields, field, value):
	"""The first Intacct record whose `field` equals `value`, or None."""
	rows = gateway.query(
		object_name,
		fields,
		filter_xml=f"<equalto><field>{field}</field><value>{escape(str(value))}</value></equalto>",
		page_size=10,
	)
	return rows[0] if rows else None


def forget_last_message():
	"""Drop the error dialog a rejected attempt queued — the next shape may be accepted."""
	log = getattr(frappe.local, "message_log", None)
	if log:
		log.pop()


def post_first_accepted(attempts, reference):
	"""Post the first of several equivalent shapes Intacct accepts.

	Companies differ in ways the gateway cannot be asked about in advance: whether an ID is
	auto-numbered, whether an object takes the generic or the legacy function. Each attempt
	is the same business document in another shape, under its own control ID.

	Only a REJECTION moves on to the next shape. A timeout or a dropped connection is
	ambiguous — Intacct may have committed — so it is raised at once rather than risking the
	same bill twice in two shapes.

	`attempts` is a list of (purpose, build) where build() returns the function elements.
	"""
	errors = []
	for purpose, build in attempts:
		try:
			return gateway.execute_many(build(), reference=reference, purpose=purpose)
		except Exception as exc:
			message = str(exc)
			if "Intacct rejected the request" not in message:
				raise
			errors.append(message.replace("Intacct rejected the request:", "").strip())
			forget_last_message()

	frappe.throw(
		"Intacct refused this posting:\n\n" + "\n\n".join(errors),
		title="Intacct refused it",
	)


def create_function(object_name, values):
	"""A generic `<create><OBJECT>` function with flat fields, in the order given."""
	function = ET.Element("function")
	record = ET.SubElement(ET.SubElement(function, "create"), object_name)
	for tag, value in values.items():
		if value not in (None, ""):
			_text(record, tag, value)
	return function


def stamped(doc, purpose):
	"""A control-ID purpose unique to this document's life on this site.

	The name alone is not enough on a demo site: restoring a profile's backup winds the
	naming series back, so the next SC-00001 would carry the control ID of one Intacct has
	already taken, and be refused as a replay. The creation time differs; a retry of the
	same document keeps it, so the replay protection stands.
	"""
	return f"{purpose}:{doc.creation}"


def _location(company):
	"""Lines post into the entity the company logs in to."""
	return gateway.entity_for_company(company)


# ──────────────────────────────────────────────────────────────────────────────
# Award: BOQ -> Intacct PROJECT + TASKs + projected cost
# ──────────────────────────────────────────────────────────────────────────────


def build_project_xml(boq, project_id, customer_id):
	"""`<create><PROJECT>`. No project_id where Intacct numbers projects itself."""
	values = {
		"PROJECTID": project_id,
		"NAME": boq.title,
		"PROJECTCATEGORY": PROJECT_CATEGORY[boq.contract_model],
		"PROJECTSTATUS": "In Progress",
		"CUSTOMERID": customer_id,
		"BEGINDATE": _us_date(boq.start_date) if boq.start_date else None,
		"ENDDATE": _us_date(boq.end_date) if boq.end_date else None,
		"BUDGETEDCOST": _money(boq.total_cost),
		"DESCRIPTION": f"Awarded from Fuse {boq.name}",
	}
	if boq.contract_model == "EPC":
		values["CONTRACTAMOUNT"] = _money(boq.contract_value)
		values["BUDGETAMOUNT"] = _money(boq.contract_value)
	return create_function("PROJECT", values)


def build_project_update_xml(recordno, boq):
	"""`<update><PROJECT>` — the budget is replaced, never added to."""
	function = ET.Element("function")
	project = ET.SubElement(ET.SubElement(function, "update"), "PROJECT")
	_text(project, "RECORDNO", recordno)
	_text(project, "BUDGETEDCOST", _money(boq.total_cost))
	if boq.contract_model == "EPC":
		_text(project, "CONTRACTAMOUNT", _money(boq.contract_value))
		_text(project, "BUDGETAMOUNT", _money(boq.contract_value))
	return function


def build_task_xml(project_id, name, description, task_id=None):
	"""`<create><TASK>`. No task_id where Intacct numbers tasks itself."""
	return create_function(
		"TASK",
		{"TASKID": task_id, "PROJECTID": project_id, "NAME": name, "DESCRIPTION": description},
	)


def _intacct_tasks(project_id):
	"""The project's Intacct tasks by name. First of any duplicate name wins."""
	tasks = {}
	for row in gateway.query(
		"TASK",
		TASK_FIELDS,
		filter_xml=f"<equalto><field>PROJECTID</field><value>{escape(project_id)}</value></equalto>",
	):
		tasks.setdefault(val(row, "NAME"), row)
	return tasks


def _mirror_project(boq, row):
	"""The ERPNext Project for an Intacct project — found by PROJECTID, as the sync finds it."""
	from fuse_projects.sync import _company, _unique_project_name

	project_id = val(row, "PROJECTID")
	existing = frappe.db.get_value("Project", {"custom_intacct_project_id": project_id}, "name")
	doc = frappe.get_doc("Project", existing) if existing else frappe.new_doc("Project")

	doc.project_name = _unique_project_name(boq.title, project_id, existing)
	doc.company = _company()
	doc.custom_intacct_project_id = project_id
	doc.custom_intacct_recordno = val(row, "RECORDNO")
	doc.custom_intacct_project_status = val(row, "PROJECTSTATUS")
	doc.custom_intacct_customer_id = val(row, "CUSTOMERID")
	if boq.customer:
		doc.customer = boq.customer
	doc.expected_start_date = boq.start_date
	doc.expected_end_date = boq.end_date
	doc.estimated_costing = boq.total_cost
	doc.status = "Open"

	# The same door the sync uses. This project came out of Intacct a moment ago.
	doc.flags.from_intacct_sync = True
	doc.flags.ignore_mandatory = True
	doc.save(ignore_permissions=True)
	return doc.name


def _mirror_task(project, company, row, section):
	"""The ERPNext Task for an Intacct task, keyed on (TASKID, PROJECTID) like the sync."""
	task_id = val(row, "TASKID")
	project_id = val(row, "PROJECTID")
	existing = frappe.db.get_value(
		"Task", {"custom_intacct_task_id": task_id, "custom_intacct_project_id": project_id}, "name"
	)
	doc = frappe.get_doc("Task", existing) if existing else frappe.new_doc("Task")

	doc.subject = section["section"]
	doc.project = project
	doc.company = company
	doc.custom_intacct_task_id = task_id
	doc.custom_intacct_project_id = project_id
	doc.custom_intacct_recordno = val(row, "RECORDNO")
	doc.description = section["description"]

	# Stops postings.on_task_insert sending it straight back to Intacct as a new task.
	doc.flags.from_intacct_sync = True
	doc.flags.ignore_mandatory = True
	doc.save(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def award_boq(boq):
	"""Open the job in Intacct from a priced BOQ, then mirror it here.

	Upsert, never duplicate: a project or task Intacct already holds under this key is
	linked rather than created again, so a re-run after a part-failure finishes the job
	instead of doubling it.
	"""
	doc = frappe.get_doc("Fuse BOQ", boq)
	doc.check_permission("write")
	if doc.status == "Awarded":
		frappe.throw(f"{doc.name} is already awarded, to {doc.project}.")

	sections = doc.get_sections()
	if not sections:
		frappe.throw("Price at least one line before awarding.")

	customer_id = None
	if doc.contract_model == "EPC":
		customer_id = frappe.db.get_value("Customer", doc.customer, "custom_intacct_customer_id")
		if not customer_id:
			frappe.throw(
				f"{doc.customer} has no Intacct Customer ID. Clients come from Intacct — "
				"open the customer there and let the sync bring it across."
			)

	reference = ("Fuse BOQ", doc.name)
	project_id = (doc.project_key or "").strip()

	row = find_one("PROJECT", PROJECT_FIELDS, "PROJECTID", project_id)
	if row is None:
		keys = post_first_accepted(
			[
				(stamped(doc, "award_project"), lambda: [build_project_xml(doc, project_id, customer_id)]),
				# Where Intacct numbers projects itself it refuses an ID it did not issue.
				(stamped(doc, "award_project_numbered"), lambda: [build_project_xml(doc, None, customer_id)]),
			],
			reference,
		)
		if keys and keys[0]:
			row = find_one("PROJECT", PROJECT_FIELDS, "RECORDNO", keys[0])
		if row is None:
			row = find_one("PROJECT", PROJECT_FIELDS, "PROJECTID", project_id)
		if row is None:
			frappe.throw("Intacct accepted the project but it could not be read back. Check Intacct before awarding again.")
	else:
		# Timestamped purpose: an update is idempotent, and a fixed control ID would refuse
		# the second award of a key Intacct already holds.
		gateway.execute(
			build_project_update_xml(val(row, "RECORDNO"), doc),
			reference=reference,
			purpose=f"award_budget:{now()}",
		)

	project_id = val(row, "PROJECTID")

	tasks = _intacct_tasks(project_id)
	missing = [section for section in sections if section["section"] not in tasks]
	if missing:
		post_first_accepted(
			[
				(
					stamped(doc, "award_tasks"),
					lambda: [
						build_task_xml(project_id, s["section"], s["description"]) for s in missing
					],
				),
				(
					stamped(doc, "award_tasks_numbered"),
					lambda: [
						build_task_xml(
							project_id, s["section"], s["description"], f"{project_id}-{s['idx']:02d}"
						)
						for s in missing
					],
				),
			],
			reference,
		)
		tasks = _intacct_tasks(project_id)
		absent = [section["section"] for section in sections if section["section"] not in tasks]
		if absent:
			frappe.throw("Intacct did not return these tasks after creating them: " + ", ".join(absent))

	project = _mirror_project(doc, row)
	company = frappe.db.get_value("Project", project, "company")
	task_names = {
		section["section"]: _mirror_task(project, company, tasks[section["section"]], section)
		for section in sections
	}

	for item in doc.items:
		item.task = task_names.get((item.section or "").strip())
	doc.status = "Awarded"
	doc.project = project
	doc.project_key = project_id
	doc.intacct_project_recordno = val(row, "RECORDNO")
	doc.awarded_on = now()
	doc.flags.awarding = True
	doc.save()

	return {"project": project, "project_id": project_id, "tasks": len(task_names)}


# ──────────────────────────────────────────────────────────────────────────────
# Buy: a purchase order against a BOQ section
# ──────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def raise_purchase_order(boq, section, supplier, item_code, qty, rate, schedule_date=None):
	"""A submitted Purchase Order for one BOQ section — the commitment the cost report shows."""
	doc = frappe.get_doc("Fuse BOQ", boq)
	if doc.status != "Awarded":
		frappe.throw("Award the BOQ first — a purchase order is raised against its project.")

	task = next((row.task for row in doc.items if (row.section or "").strip() == section and row.task), None)
	if not task:
		frappe.throw(f"{section} is not a section of {doc.name}.")

	schedule_date = schedule_date or add_days(nowdate(), 14)
	po = frappe.new_doc("Purchase Order")
	po.supplier = supplier
	po.company = frappe.db.get_value("Project", doc.project, "company")
	po.transaction_date = nowdate()
	po.schedule_date = schedule_date
	if po.meta.has_field("project"):
		po.project = doc.project
	po.append(
		"items",
		{
			"item_code": item_code,
			"qty": flt(qty),
			"rate": flt(rate),
			"schedule_date": schedule_date,
			"project": doc.project,
			"custom_boq_task": task,
		},
	)
	po.insert()
	po.submit()
	return po.name


# ──────────────────────────────────────────────────────────────────────────────
# Subcontract certificate -> AP bill
# ──────────────────────────────────────────────────────────────────────────────


def _certificate_lines(cert, project_id, cfg, section):
	lines = [
		{
			"account": cfg.construction_cost_account,
			"amount": flt(cert.gross_value),
			"memo": f"Cert {cert.certificate_no}: {section}, work certified",
			"project": project_id,
		}
	]
	if flt(cert.contra_charges):
		lines.append(
			{
				"account": cfg.construction_cost_account,
				"amount": -flt(cert.contra_charges),
				"memo": f"Contra-charge: {cert.contra_description or section}",
				"project": project_id,
			}
		)
	if flt(cert.retention_amount):
		lines.append(
			{
				"account": cfg.retention_payable_account,
				"amount": -flt(cert.retention_amount),
				"memo": f"Retention {flt(cert.retention_percent):g}% held",
				"project": None,
			}
		)
	return lines


def build_bill_xml(*, vendor_id, posting_date, due_date, bill_no, description, lines, location_id):
	"""Generic `<create><APBILL>`."""
	function = ET.Element("function")
	bill = ET.SubElement(ET.SubElement(function, "create"), "APBILL")
	_text(bill, "VENDORID", vendor_id)
	_text(bill, "WHENCREATED", _us_date(posting_date))
	_text(bill, "WHENDUE", _us_date(due_date))
	_text(bill, "RECORDID", bill_no)
	_text(bill, "DESCRIPTION", description)
	items = ET.SubElement(bill, "APBILLITEMS")
	for line in lines:
		item = ET.SubElement(items, "APBILLITEM")
		_text(item, "ACCOUNTNO", line["account"])
		_text(item, "TRX_AMOUNT", _money(line["amount"]))
		_text(item, "ENTRYDESCRIPTION", line["memo"])
		if location_id:
			_text(item, "LOCATIONID", location_id)
		if line["project"]:
			_text(item, "PROJECTID", line["project"])
	return function


def build_bill_legacy_xml(*, vendor_id, posting_date, due_date, bill_no, description, lines, location_id):
	"""Legacy `<create_bill>`, for a company whose AP refuses the generic shape. Order matters."""
	function = ET.Element("function")
	bill = ET.SubElement(function, "create_bill")
	_text(bill, "vendorid", vendor_id)
	_legacy_date(bill, "datecreated", posting_date)
	_legacy_date(bill, "datedue", due_date)
	_text(bill, "billno", bill_no)
	_text(bill, "description", description)
	items = ET.SubElement(bill, "billitems")
	for line in lines:
		item = ET.SubElement(items, "lineitem")
		_text(item, "glaccountno", line["account"])
		_text(item, "amount", _money(line["amount"]))
		_text(item, "memo", line["memo"])
		if location_id:
			_text(item, "locationid", location_id)
		if line["project"]:
			_text(item, "projectid", line["project"])
	return function


def post_certificate(cert, dry_run=False):
	"""Post one subcontract certificate to Intacct as an AP bill. Intacct first."""
	if cert.get("intacct_key"):
		return cert.intacct_key

	cfg = posting_settings()
	vendor_id = frappe.db.get_value("Supplier", cert.subcontractor, "custom_intacct_vendor_id")
	if not vendor_id:
		frappe.throw(
			f"{cert.subcontractor} has no Intacct vendor ID. Subcontractors come from Intacct — "
			"a certificate for one it has never heard of is parked, not guessed."
		)
	project_id, company = frappe.db.get_value(
		"Project", cert.project, ["custom_intacct_project_id", "company"]
	)
	if not project_id:
		frappe.throw(f"{cert.project} is not an Intacct project.")

	section = frappe.db.get_value("Task", cert.task, "subject")
	shape = {
		"vendor_id": vendor_id,
		"posting_date": cert.posting_date,
		"due_date": add_days(cert.posting_date, cint(cfg.get("construction_due_days")) or 30),
		"bill_no": cert.certificate_no,
		"description": f"Subcontract certificate {cert.certificate_no}, {section}, {cert.period or ''}".strip(" ,"),
		"lines": _certificate_lines(cert, project_id, cfg, section),
		"location_id": _location(company),
	}
	if dry_run:
		return ET.tostring(build_bill_xml(**shape), encoding="unicode")

	keys = post_first_accepted(
		[
			(stamped(cert, "subcontract_bill"), lambda: [build_bill_xml(**shape)]),
			(stamped(cert, "subcontract_bill_legacy"), lambda: [build_bill_legacy_xml(**shape)]),
		],
		(cert.doctype, cert.name),
	)
	cert.db_set({"intacct_key": keys[0], "intacct_posted_on": now()}, update_modified=False)
	return keys[0]


# ──────────────────────────────────────────────────────────────────────────────
# Client valuation -> AR invoice
# ──────────────────────────────────────────────────────────────────────────────


def _valuation_lines(valuation, project_id, cfg):
	lines = [
		{
			"account": cfg.revenue_account,
			"amount": flt(valuation.gross_this_valuation),
			"memo": f"Valuation {valuation.name}, {valuation.period or 'work to date'}",
			"project": project_id,
		}
	]
	if flt(valuation.retention_amount):
		lines.append(
			{
				"account": cfg.retention_receivable_account,
				"amount": -flt(valuation.retention_amount),
				"memo": f"Retention {flt(valuation.retention_percent):g}% held by client",
				"project": None,
			}
		)
	return lines


def build_invoice_xml(*, customer_id, posting_date, due_date, description, lines, location_id):
	"""Generic `<create><ARINVOICE>`. No invoice number — AR numbering is Intacct's."""
	function = ET.Element("function")
	invoice = ET.SubElement(ET.SubElement(function, "create"), "ARINVOICE")
	_text(invoice, "CUSTOMERID", customer_id)
	_text(invoice, "WHENCREATED", _us_date(posting_date))
	_text(invoice, "WHENDUE", _us_date(due_date))
	_text(invoice, "DESCRIPTION", description)
	items = ET.SubElement(invoice, "ARINVOICEITEMS")
	for line in lines:
		item = ET.SubElement(items, "ARINVOICEITEM")
		_text(item, "ACCOUNTNO", line["account"])
		_text(item, "TRX_AMOUNT", _money(line["amount"]))
		_text(item, "ENTRYDESCRIPTION", line["memo"])
		if location_id:
			_text(item, "LOCATIONID", location_id)
		if line["project"]:
			_text(item, "PROJECTID", line["project"])
	return function


def build_invoice_legacy_xml(*, customer_id, posting_date, due_date, description, lines, location_id):
	"""Legacy `<create_invoice>`. Order matters."""
	function = ET.Element("function")
	invoice = ET.SubElement(function, "create_invoice")
	_text(invoice, "customerid", customer_id)
	_legacy_date(invoice, "datecreated", posting_date)
	_legacy_date(invoice, "datedue", due_date)
	_text(invoice, "description", description)
	items = ET.SubElement(invoice, "invoiceitems")
	for line in lines:
		item = ET.SubElement(items, "lineitem")
		_text(item, "glaccountno", line["account"])
		_text(item, "amount", _money(line["amount"]))
		_text(item, "memo", line["memo"])
		if location_id:
			_text(item, "locationid", location_id)
		if line["project"]:
			_text(item, "projectid", line["project"])
	return function


def post_valuation(valuation, dry_run=False):
	"""Post one client valuation to Intacct as an AR invoice. Intacct first."""
	if valuation.get("intacct_key"):
		return valuation.intacct_key

	cfg = posting_settings()
	customer_id = frappe.db.get_value("Customer", valuation.customer, "custom_intacct_customer_id")
	if not customer_id:
		frappe.throw(f"{valuation.customer} has no Intacct Customer ID.")
	project_id, company = frappe.db.get_value(
		"Project", valuation.project, ["custom_intacct_project_id", "company"]
	)
	if not project_id:
		frappe.throw(f"{valuation.project} is not an Intacct project.")

	shape = {
		"customer_id": customer_id,
		"posting_date": valuation.posting_date,
		"due_date": add_days(valuation.posting_date, cint(cfg.get("construction_due_days")) or 30),
		"description": f"Valuation {valuation.name}, {project_id}, {valuation.period or ''}".strip(" ,"),
		"lines": _valuation_lines(valuation, project_id, cfg),
		"location_id": _location(company),
	}
	if dry_run:
		return ET.tostring(build_invoice_xml(**shape), encoding="unicode")

	keys = post_first_accepted(
		[
			(stamped(valuation, "valuation_invoice"), lambda: [build_invoice_xml(**shape)]),
			(stamped(valuation, "valuation_invoice_legacy"), lambda: [build_invoice_legacy_xml(**shape)]),
		],
		(valuation.doctype, valuation.name),
	)
	valuation.db_set({"intacct_key": keys[0], "intacct_posted_on": now()}, update_modified=False)
	return keys[0]


@frappe.whitelist()
def preview_posting(doctype, name):
	"""The XML a certificate or valuation would send, without sending it. System Manager only."""
	frappe.only_for("System Manager")
	doc = frappe.get_doc(doctype, name)
	if doctype == "Fuse Subcontract Certificate":
		return post_certificate(doc, dry_run=True)
	if doctype == "Fuse Client Valuation":
		return post_valuation(doc, dry_run=True)
	frappe.throw(f"Nothing to preview for {doctype}.")


# ──────────────────────────────────────────────────────────────────────────────
# Valuation helpers
# ──────────────────────────────────────────────────────────────────────────────


def previous_valuation(boq, exclude=None):
	"""The last submitted valuation on a BOQ, or None."""
	filters = {"boq": boq, "docstatus": 1}
	if exclude:
		filters["name"] = ("!=", exclude)
	rows = frappe.get_all(
		"Fuse Client Valuation", filters=filters, pluck="name", order_by="posting_date desc, creation desc", limit=1
	)
	return frappe.get_doc("Fuse Client Valuation", rows[0]) if rows else None


def previously_valued(boq, exclude=None):
	filters = {"boq": boq, "docstatus": 1}
	if exclude:
		filters["name"] = ("!=", exclude)
	return flt(sum(frappe.get_all("Fuse Client Valuation", filters=filters, pluck="gross_this_valuation")), 2)


@frappe.whitelist()
def valuation_lines(boq, exclude=None):
	"""One line per BOQ section, carrying the percent the last valuation reached."""
	doc = frappe.get_doc("Fuse BOQ", boq)
	doc.check_permission("read")
	last = previous_valuation(boq, exclude)
	before = {line.section: flt(line.percent_complete) for line in (last.lines if last else [])}

	lines = []
	for section in doc.get_sections():
		percent = before.get(section["section"], 0)
		lines.append(
			{
				"section": section["section"],
				"task": section["task"],
				"contract_value": section["contract"],
				"previous_percent": percent,
				"percent_complete": percent,
				"value_to_date": flt(section["contract"] * percent / 100, 2),
			}
		)
	return {
		"lines": lines,
		"previously_valued": previously_valued(boq, exclude),
		"retention_percent": doc.client_retention_percent,
		"project": doc.project,
		"customer": doc.customer,
	}


# ──────────────────────────────────────────────────────────────────────────────
# What Intacct holds against a project, read live
# ──────────────────────────────────────────────────────────────────────────────


def intacct_project_totals(project_id):
	"""Cost billed (AP) and revenue invoiced (AR) on a project, straight from Intacct."""
	project_filter = f"<equalto><field>PROJECTID</field><value>{escape(project_id)}</value></equalto>"
	cost = sum(
		gateway.number(row, "AMOUNT", 0)
		for row in gateway.query("APBILLITEM", ["RECORDNO", "AMOUNT"], filter_xml=project_filter)
	)
	billed = sum(
		gateway.number(row, "AMOUNT", 0)
		for row in gateway.query("ARINVOICEITEM", ["RECORDNO", "AMOUNT"], filter_xml=project_filter)
	)
	return {"cost": flt(cost, 2), "billed": flt(billed, 2)}
