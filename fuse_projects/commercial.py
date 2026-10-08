"""Construction commercials for Fuse Projects: award, buy, certify, value.

Held in Fuse. Nothing here reads from or writes to Intacct.

  * Award. A priced BOQ opens its project with one task per BOQ section, and the BOQ
    becomes the budget the cost report measures against.
  * Buy. A purchase order raised against a BOQ section is the commitment.
  * Certify and value. Subcontract certificates and client valuations carry their own
    retention and contra-charges (see their doctypes); a valuation moves each section's
    percent complete, which is what earned value is measured from.
"""

import frappe
from frappe.utils import add_days, flt, now, nowdate

# ──────────────────────────────────────────────────────────────────────────────
# Award: BOQ -> Project + a Task per section
# ──────────────────────────────────────────────────────────────────────────────


def _make_project(boq):
	"""The ERPNext Project an awarded BOQ is run as."""
	from fuse_projects.sync import _company, _unique_project_name

	doc = frappe.new_doc("Project")
	doc.project_name = _unique_project_name(boq.title, boq.project_key, None)
	doc.company = _company()
	doc.customer = boq.customer
	doc.expected_start_date = boq.start_date
	doc.expected_end_date = boq.end_date
	doc.estimated_costing = boq.total_cost
	doc.status = "Open"
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_task(project, company, section):
	doc = frappe.new_doc("Task")
	doc.subject = section["section"]
	doc.project = project
	doc.company = company
	doc.description = section["description"]
	doc.insert(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def award_boq(boq):
	"""Award a priced BOQ: open its project with one task per section, and lock the price."""
	doc = frappe.get_doc("Fuse BOQ", boq)
	doc.check_permission("write")
	if doc.status == "Awarded":
		frappe.throw(f"{doc.name} is already awarded, to {doc.project}.")

	sections = doc.get_sections()
	if not sections:
		frappe.throw("Price at least one line before awarding.")

	project = _make_project(doc)
	company = frappe.db.get_value("Project", project, "company")
	tasks = {section["section"]: _make_task(project, company, section) for section in sections}

	for item in doc.items:
		item.task = tasks.get(item.section)
	doc.status = "Awarded"
	doc.project = project
	doc.awarded_on = now()
	doc.flags.awarding = True
	doc.save()

	return {"project": project, "tasks": len(tasks)}


# ──────────────────────────────────────────────────────────────────────────────
# Buy: a purchase order against a BOQ section
# ──────────────────────────────────────────────────────────────────────────────


@frappe.whitelist()
def raise_purchase_order(boq, section, supplier, item_code, qty, rate, schedule_date=None):
	"""A submitted Purchase Order for one BOQ section — the commitment the cost report shows."""
	doc = frappe.get_doc("Fuse BOQ", boq)
	if doc.status != "Awarded":
		frappe.throw("Award the BOQ first — a purchase order is raised against its project.")

	task = next((row.task for row in doc.items if row.section == section and row.task), None)
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
# Valuations
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
