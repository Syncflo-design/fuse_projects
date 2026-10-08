"""Budget, committed, actual and earned value per BOQ section — the Power BI page, in Fuse.

Budget is the awarded BOQ. Committed is purchase orders not yet received. Actual is what
subcontractors have been certified for, less contra-charges, plus goods received. Percent
complete is the task's progress, which a client valuation sets (and the site team can move on
the phone screen), and earned value is budget times that percent.

Everything here is Fuse's own data.
"""

import frappe
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.project:
		return _columns(), []

	boq_name = frappe.db.get_value(
		"Fuse BOQ", {"project": filters.project, "status": "Awarded"}, "name", order_by="creation desc"
	)
	if not boq_name:
		return _columns(), [], "This project has no awarded BOQ."
	boq = frappe.get_doc("Fuse BOQ", boq_name)

	committed, received = _purchase_orders(filters.project)
	certified, retention_held = _certificates(filters.project)
	progress = dict(
		frappe.get_all(
			"Task", filters={"project": filters.project}, fields=["name", "progress"], as_list=True
		)
	)

	rows = []
	for section in boq.get_sections():
		task = section["task"]
		budget = section["cost"]
		actual = flt(certified.get(task, 0) + received.get(task, 0), 2)
		percent = flt(progress.get(task))
		earned = flt(budget * percent / 100, 2)
		rows.append(
			_row(
				section["section"],
				budget,
				committed.get(task, 0),
				actual,
				percent,
				earned,
			)
		)

	total_budget = sum(row["budget"] for row in rows)
	total_earned = sum(row["earned_value"] for row in rows)
	total = _row(
		"Total",
		total_budget,
		sum(row["committed"] for row in rows),
		sum(row["actual"] for row in rows),
		flt(total_earned / total_budget * 100, 2) if total_budget else 0,
		total_earned,
	)
	total["bold"] = 1
	rows.append(total)

	return _columns(), rows, None, _chart(rows[:-1]), _summary(boq, total, retention_held)


def _row(section, budget, committed, actual, percent, earned):
	cpi = flt(earned / actual, 2) if actual else None
	return {
		"section": section,
		"budget": flt(budget, 2),
		"committed": flt(committed, 2),
		"actual": flt(actual, 2),
		"percent_complete": flt(percent, 2),
		"earned_value": flt(earned, 2),
		"cost_variance": flt(earned - actual, 2),
		"cpi": cpi,
		# Budget at the rate the job is actually earning. Budget itself until there is a rate.
		"forecast": flt(budget / cpi, 2) if cpi else flt(budget, 2),
	}


def _purchase_orders(project):
	"""Open (committed) and received (accrued) purchase order value per BOQ section."""
	rows = frappe.db.sql(
		"""
		select poi.custom_boq_task as task,
			sum(case when po.status = 'Closed' then 0
				else greatest(poi.qty - poi.received_qty, 0) * poi.base_rate end) as open_value,
			sum(least(poi.received_qty, poi.qty) * poi.base_rate) as received_value
		from `tabPurchase Order Item` poi
		join `tabPurchase Order` po on po.name = poi.parent
		where po.docstatus = 1 and poi.project = %s and ifnull(poi.custom_boq_task, '') != ''
		group by poi.custom_boq_task
		""",
		project,
		as_dict=True,
	)
	return (
		{row.task: flt(row.open_value) for row in rows},
		{row.task: flt(row.received_value) for row in rows},
	)


def _certificates(project):
	"""Cost certified per section (gross less contra), and retention held."""
	certified, retention = {}, 0.0
	for cert in frappe.get_all(
		"Fuse Subcontract Certificate",
		filters={"project": project, "docstatus": 1},
		fields=["task", "gross_value", "contra_charges", "retention_amount"],
	):
		certified[cert.task] = certified.get(cert.task, 0) + flt(cert.gross_value) - flt(cert.contra_charges)
		retention += flt(cert.retention_amount)
	return certified, retention


def _columns():
	return [
		{"fieldname": "section", "label": "BOQ Section", "fieldtype": "Data", "width": 220},
		{"fieldname": "budget", "label": "Budget", "fieldtype": "Currency", "width": 140},
		{"fieldname": "committed", "label": "Committed", "fieldtype": "Currency", "width": 140},
		{"fieldname": "actual", "label": "Actual", "fieldtype": "Currency", "width": 140},
		{"fieldname": "percent_complete", "label": "% Complete", "fieldtype": "Percent", "width": 100},
		{"fieldname": "earned_value", "label": "Earned Value", "fieldtype": "Currency", "width": 140},
		{"fieldname": "cost_variance", "label": "Cost Variance", "fieldtype": "Currency", "width": 140},
		{"fieldname": "cpi", "label": "CPI", "fieldtype": "Float", "precision": 2, "width": 70},
		{"fieldname": "forecast", "label": "Forecast Final Cost", "fieldtype": "Currency", "width": 150},
	]


def _chart(rows):
	return {
		"data": {
			"labels": [row["section"] for row in rows],
			"datasets": [
				{"name": "Budget", "values": [row["budget"] for row in rows]},
				{"name": "Committed + Actual", "values": [row["committed"] + row["actual"] for row in rows]},
				{"name": "Earned Value", "values": [row["earned_value"] for row in rows]},
			],
		},
		"type": "bar",
		"barOptions": {"spaceRatio": 0.4},
	}


def _summary(boq, total, retention_held):
	valued = flt(
		sum(
			frappe.get_all(
				"Fuse Client Valuation",
				filters={"boq": boq.name, "docstatus": 1},
				pluck="gross_this_valuation",
			)
		),
		2,
	)
	cards = [
		{"label": "Contract Value", "value": boq.contract_value, "datatype": "Currency", "indicator": "Blue"},
		{"label": "Budget", "value": total["budget"], "datatype": "Currency", "indicator": "Blue"},
		{
			"label": "Committed + Actual",
			"value": total["committed"] + total["actual"],
			"datatype": "Currency",
			"indicator": "Red" if total["committed"] + total["actual"] > total["budget"] else "Green",
		},
		{
			"label": "Earned Value",
			"value": total["earned_value"],
			"datatype": "Currency",
			"indicator": "Green" if total["cost_variance"] >= 0 else "Red",
		},
		{"label": "Valued to Client", "value": valued, "datatype": "Currency", "indicator": "Blue"},
		{"label": "Subcontract Retention Held", "value": retention_held, "datatype": "Currency", "indicator": "Grey"},
	]

	return cards
