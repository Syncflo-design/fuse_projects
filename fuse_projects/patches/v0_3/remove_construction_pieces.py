"""Take out the construction pieces 0.2.x added, now that fuse_construction owns them.

0.2.0 to 0.2.2 shipped a BOQ, subcontract certificates, client valuations and a cost report
inside Fuse Projects for the NSE demo. fuse_construction does all of it properly, so keeping
both would leave a site with two BOQs. Their code is gone; this removes what they left on a
site that had them installed: the doctypes (and their records), the report and the custom
fields. Every delete tolerates a site that never had them.
"""

import frappe

# Parents before the child tables they hold.
DOCTYPES = [
	"Fuse Client Valuation",
	"Fuse Subcontract Certificate",
	"Fuse BOQ",
	"Fuse Valuation Line",
	"Fuse BOQ Item",
]

CUSTOM_FIELDS = {
	"Purchase Order Item": ["custom_boq_task"],
	"Intacct Settings": [
		"construction_section",
		"construction_cost_account",
		"retention_payable_account",
		"construction_due_days",
		"construction_column",
		"revenue_account",
		"retention_receivable_account",
	],
}


def execute():
	frappe.delete_doc("Report", "Project Cost Report", ignore_missing=True, force=True)

	for doctype in DOCTYPES:
		frappe.delete_doc("DocType", doctype, ignore_missing=True, force=True)

	for doctype, fieldnames in CUSTOM_FIELDS.items():
		for fieldname in fieldnames:
			name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname})
			if name:
				frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
