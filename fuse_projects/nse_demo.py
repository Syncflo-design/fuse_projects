"""The NSE Energy demo profile: one 5 MW PV plant, awarded and ready to run.

Demo setup, not product. Run once on the Fuse demo site, from the BOQ list (menu: Load NSE
Demo), after the outgoing profile has been backed up. It is idempotent — a second run finds
what the first made and adds only what is missing.

Everything stays in Fuse. Nothing is read from or written to Intacct.

What it does:
  * switches off the manufacturing tiles, so Fuse Home reads as a contractor's;
  * adds the subcontractor, the two material suppliers and the EPC client;
  * adds two purchasable items (modules, inverters) for the purchase orders;
  * prices the BOQ — six sections, fourteen lines, one with a rate build-up — and awards it,
    which opens the project with a task per section.

Nothing is bought, certified or valued. Those are the demo.
"""

import frappe
from frappe.utils import add_months, nowdate

from fuse_projects import commercial

# A contractor's Fuse Home: projects, buying, receiving, stores and the phone screens.
MODULES_OFF = (
	"boms",
	"production_plan",
	"planning",
	"works_orders",
	"wip_issue",
	"picking",
	"quality",
	"stock_count",
	"bin_transfer",
)

SUPPLIERS = [
	"Karoo Civils (Pty) Ltd",
	"Helios PV Supply (Pty) Ltd",
	"Cape Inverter Systems (Pty) Ltd",
]
CLIENT = "Overberg Solar One (RF) Pty Ltd"

ITEMS = [
	("NSE-PV-550", "PV module 550 Wp, bifacial"),
	("NSE-INV-100", "String inverter 100 kW"),
]

# (section, cost code, description, qty, unit, rate, build-up or None)
BOQ_LINES = [
	("Civils and earthworks", "CIV-010", "Site clearance and grubbing", 12, "ha", 43000, None),
	("Civils and earthworks", "CIV-020", "Bulk earthworks, cut and fill", 18000, "m3", 115, None),
	("Civils and earthworks", "CIV-030", "Internal gravel access roads", 3200, "m", 680, None),
	("Civils and earthworks", "CIV-040", "Perimeter security fence, 2.4 m clear-view", 1600, "m", 0,
	 {"labour_rate": 210, "plant_rate": 70, "material_rate": 400, "subcontract_rate": 80}),
	("Mounting structures", "MNT-010", "Driven steel piles", 4800, "No", 680, None),
	("Mounting structures", "MNT-020", "Fixed-tilt structures, supply and erect", 5000, "kWp", 1120, None),
	("PV modules", "PVM-010", "PV modules 550 Wp, supply", 9100, "No", 2070, None),
	("PV modules", "PVM-020", "Module installation", 9100, "No", 110, None),
	("Inverters", "INV-010", "String inverters 100 kW, supply", 50, "No", 93600, None),
	("Inverters", "INV-020", "Inverter installation and commissioning", 50, "No", 11700, None),
	("DC and AC cabling", "CAB-010", "DC string cabling", 48000, "m", 34, None),
	("DC and AC cabling", "CAB-020", "AC LV cabling including trenching", 6500, "m", 430, None),
	("MV grid connection", "MV-010", "MV switchgear and transformer stations", 2, "No", 3330000, None),
	("MV grid connection", "MV-020", "MV overhead line to point of connection", 2.5, "km", 1730000, None),
]


@frappe.whitelist()
def load(project_key="NSE-DEMO-5MW"):
	frappe.only_for("System Manager")
	project_key = (project_key or "NSE-DEMO-5MW").strip()

	# The custom fields and workspace this needs, in case after_migrate did not fire on the
	# deploy (it has been seen not to on Frappe Cloud). Idempotent.
	from fuse_projects.install import after_install

	after_install()
	_switch_off_manufacturing()
	for name in SUPPLIERS:
		_ensure_party("Supplier", name)
	_ensure_party("Customer", CLIENT)
	items = [_ensure_item(code, name) for code, name in ITEMS]
	boq = _ensure_boq(project_key)
	if frappe.db.get_value("Fuse BOQ", boq, "status") == "Draft":
		commercial.award_boq(boq)
	project = frappe.db.get_value("Fuse BOQ", boq, "project")

	frappe.db.commit()
	summary = (
		f"BOQ <b>{boq}</b> awarded as project <b>{project}</b>, one task per section.<br>"
		f"Subcontractor and suppliers: {', '.join(SUPPLIERS)}. Client: {CLIENT}.<br>"
		f"Items: {', '.join(items)}. Manufacturing tiles switched off."
	)
	return {"boq": boq, "summary": summary}


def _switch_off_manufacturing():
	for key in MODULES_OFF:
		frappe.db.set_value(
			"Fuse Active Module",
			{"parent": "Intacct Settings", "module_key": key},
			"enabled",
			0,
		)
	frappe.clear_document_cache("Intacct Settings", "Intacct Settings")


def _ensure_party(doctype, name):
	existing = frappe.db.get_value(doctype, {f"{doctype.lower()}_name": name}, "name")
	if existing:
		return existing

	doc = frappe.new_doc(doctype)
	if doctype == "Supplier":
		doc.supplier_name = name
		doc.supplier_group = "Services" if frappe.db.exists("Supplier Group", "Services") else frappe.get_all(
			"Supplier Group", filters={"is_group": 0}, pluck="name", limit=1
		)[0]
	else:
		doc.customer_name = name
		doc.customer_group = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
	doc.insert(ignore_permissions=True)
	return doc.name


def _ensure_item(code, name):
	if frappe.db.exists("Item", code):
		return code
	group = "Products" if frappe.db.exists("Item Group", "Products") else frappe.get_all(
		"Item Group", filters={"is_group": 0}, pluck="name", limit=1
	)[0]
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": name,
			"description": name,
			"item_group": group,
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"is_purchase_item": 1,
			"is_sales_item": 0,
			"include_item_in_manufacturing": 0,
		}
	).insert(ignore_permissions=True)
	return code


def _ensure_boq(project_key):
	existing = frappe.db.get_value("Fuse BOQ", {"project_key": project_key}, "name", order_by="creation desc")
	if existing:
		return existing

	boq = frappe.new_doc("Fuse BOQ")
	boq.title = "Demo 5 MW PV Plant"
	boq.project_key = project_key
	boq.contract_model = "EPC"
	boq.customer = frappe.db.get_value("Customer", {"customer_name": CLIENT}, "name")
	boq.start_date = nowdate()
	boq.end_date = add_months(nowdate(), 9)
	boq.markup_percent = 15
	boq.subcontract_retention_percent = 10
	boq.client_retention_percent = 5
	for section, cost_code, description, qty, uom, rate, build_up in BOQ_LINES:
		row = {
			"section": section,
			"cost_code": cost_code,
			"description": description,
			"qty": qty,
			"uom": uom,
			"rate": rate,
		}
		row.update(build_up or {})
		boq.append("items", row)
	boq.insert(ignore_permissions=True)
	return boq.name
