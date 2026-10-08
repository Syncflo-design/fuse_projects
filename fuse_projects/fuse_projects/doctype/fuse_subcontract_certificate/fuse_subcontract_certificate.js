// A subcontractor's certificate. The figures are worked out here as they are typed and again
// on the server, which is the one that counts.

frappe.ui.form.on("Fuse Subcontract Certificate", {
	setup(frm) {
		frm.set_query("task", () => ({ filters: { project: frm.doc.project || "" } }));
		frm.set_query("boq", () => ({ filters: { status: "Awarded" } }));
	},

	onload(frm) {
		if (frm.is_new() && frm.doc.boq && !frm.doc.project) frm.trigger("boq");
	},

	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.intacct_key) {
			frm.dashboard.set_headline(
				__("Posted to Intacct as AP bill {0}.", [frappe.utils.escape_html(frm.doc.intacct_key)])
			);
		}
		if (frm.doc.docstatus === 0 && !frm.is_new() && frappe.user.has_role("System Manager")) {
			frm.add_custom_button(__("Preview Intacct Bill"), () => preview(frm));
		}
	},

	boq(frm) {
		if (!frm.doc.boq) return;
		frappe.db
			.get_value("Fuse BOQ", frm.doc.boq, ["project", "subcontract_retention_percent"])
			.then(({ message }) => {
				frm.set_value("project", message.project);
				if (!frm.doc.retention_percent) frm.set_value("retention_percent", message.subcontract_retention_percent);
			});
	},

	gross_value: work_out,
	retention_percent: work_out,
	contra_charges: work_out,
});

function work_out(frm) {
	const retention = flt((flt(frm.doc.gross_value) * flt(frm.doc.retention_percent)) / 100, 2);
	frm.set_value("retention_amount", retention);
	frm.set_value("net_payable", flt(flt(frm.doc.gross_value) - retention - flt(frm.doc.contra_charges), 2));
}

function preview(frm) {
	frappe.call({
		method: "fuse_projects.commercial.preview_posting",
		args: { doctype: frm.doctype, name: frm.doc.name },
		callback(r) {
			if (r.message) {
				frappe.msgprint({ title: __("What Intacct will receive"), message: `<pre>${frappe.utils.escape_html(r.message)}</pre>`, wide: true });
			}
		},
	});
}
