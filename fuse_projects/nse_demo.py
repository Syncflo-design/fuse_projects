"""The NSE Energy demo profile: one 5 MW PV plant, ready to award.

Demo setup, not product. Run once on the Fuse demo site, from the BOQ list (menu: Load NSE
Demo), after the outgoing profile has been backed up. It is idempotent — a second run finds
what the first made and adds only what is missing.

What it does:
  * names the Intacct accounts certificates and valuations post to (leadertread-DEV's
    Retainage Payable / Receivable, COGS Services and Revenue - Other);
  * switches off the manufacturing tiles, so Fuse Home reads as a contractor's;
  * opens the subcontractor, the two material suppliers and the EPC client in Intacct —
    vendors and customers are Intacct's, so they are created there and mirrored here;
  * adds two purchasable items (modules, inverters) for the purchase orders;
  * prices the BOQ: six sections, fourteen lines, one with a rate build-up.

Nothing is awarded, certified or valued. Those are the demo.
"""

import frappe
from frappe.utils import add_months, nowdate
from fuse_core import gateway
from fuse_core.gateway import val

from fuse_projects import commercial

# leadertread-DEV's chart. All four exist and need no department or location.
ACCOUNTS = {
	"construction_cost_account": "50300",  # COGS Services
	"retention_payable_account": "20191",  # Retainage Payable
	"revenue_account": "40900",  # Revenue - Other
	"retention_receivable_account": "10191",  # Retainage Receivable
	"construction_due_days": 30,
}

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

SUBCONTRACTOR = ("NSE-V-CIVILS", "Karoo Civils (Pty) Ltd")
SUPPLIERS = [
	("NSE-V-MODULES", "Helios PV Supply (Pty) Ltd"),
	("NSE-V-INVERTERS", "Cape Inverter Systems (Pty) Ltd"),
]
CLIENT = ("NSE-C-OVERBERG", "Overberg Solar One (RF) Pty Ltd")

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
	_settings()
	vendor_ids = {
		name: _ensure_party("VENDOR", "Supplier", vendor_id, name)
		for vendor_id, name in [SUBCONTRACTOR, *SUPPLIERS]
	}
	customer_id = _ensure_party("CUSTOMER", "Customer", *CLIENT)
	items = [_ensure_item(code, name) for code, name in ITEMS]
	boq = _ensure_boq(project_key)

	frappe.db.commit()
	summary = (
		f"BOQ <b>{boq}</b> priced for project key <b>{frappe.utils.escape_html(project_key)}</b>.<br>"
		f"In Intacct: {', '.join(f'{name} ({vid})' for name, vid in vendor_ids.items())}; "
		f"client {CLIENT[1]} ({customer_id}).<br>"
		f"Items: {', '.join(items)}. Manufacturing tiles switched off."
	)
	return {"boq": boq, "summary": summary}


def _settings():
	"""Posting accounts, and a contractor's set of tiles."""
	for field, value in ACCOUNTS.items():
		if not frappe.db.get_single_value("Intacct Settings", field):
			frappe.db.set_single_value("Intacct Settings", field, value)

	for key in MODULES_OFF:
		frappe.db.set_value(
			"Fuse Active Module",
			{"parent": "Intacct Settings", "module_key": key},
			"enabled",
			0,
		)
	frappe.clear_document_cache("Intacct Settings", "Intacct Settings")


def _ensure_party(object_name, doctype, preferred_id, name):
	"""An Intacct vendor or customer, opened there if missing and mirrored here.

	Found by name first, so a second run never makes a second one. Created with the ID
	given, or — where Intacct numbers them itself and refuses an ID it did not issue —
	without one, and the number it chose is read back.
	"""
	id_field = "VENDORID" if object_name == "VENDOR" else "CUSTOMERID"
	local_field = "custom_intacct_vendor_id" if doctype == "Supplier" else "custom_intacct_customer_id"
	fields = ["RECORDNO", id_field, "NAME"]

	local = _ensure_local_party(doctype, name)
	created = frappe.db.get_value(doctype, local, "creation")

	row = commercial.find_one(object_name, fields, "NAME", name)
	if row is None:
		keys = commercial.post_first_accepted(
			[
				(f"demo_party:{created}", lambda: [commercial.create_function(object_name, {id_field: preferred_id, "NAME": name})]),
				(f"demo_party_numbered:{created}", lambda: [commercial.create_function(object_name, {"NAME": name})]),
			],
			(doctype, local),
		)
		if keys and keys[0]:
			row = commercial.find_one(object_name, fields, "RECORDNO", keys[0])
		if row is None:
			row = commercial.find_one(object_name, fields, "NAME", name)
		if row is None:
			frappe.throw(f"Intacct accepted {name} but it could not be read back.")

	intacct_id = val(row, id_field)
	frappe.db.set_value(
		doctype,
		local,
		{local_field: intacct_id, "custom_intacct_recordno": val(row, "RECORDNO")},
		update_modified=False,
	)
	return intacct_id


def _ensure_local_party(doctype, name):
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
	group = gateway.settings().get("default_item_group") or "Products"
	if not frappe.db.exists("Item Group", group):
		group = frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
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
	existing = frappe.db.get_value("Fuse BOQ", {"project_key": project_key}, "name")
	if existing:
		return existing

	customer = frappe.db.get_value("Customer", {"customer_name": CLIENT[1]}, "name")
	boq = frappe.new_doc("Fuse BOQ")
	boq.title = "Demo 5 MW PV Plant"
	boq.project_key = project_key
	boq.contract_model = "EPC"
	boq.customer = customer
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

