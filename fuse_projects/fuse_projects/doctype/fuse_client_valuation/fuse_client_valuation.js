// A valuation to the client. Sections and the percent the last valuation reached come from
// the BOQ; the person valuing moves the percent on, and the value this period follows.

frappe.ui.form.on("Fuse Client Valuation", {
	setup(frm) {
		frm.set_query("boq", () => ({ filters: { status: "Awarded", contract_model: "EPC" } }));
	},

	onload(frm) {
		if (frm.is_new() && frm.doc.boq && !(frm.doc.lines || []).length) frm.trigger("boq");
	},

	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.intacct_key) {
			frm.dashboard.set_headline(
				__("Posted to Intacct as AR invoice {0}.", [frappe.utils.escape_html(frm.doc.intacct_key)])
			);
		}
		if (frm.doc.docstatus === 0 && !frm.is_new() && frappe.user.has_role("System Manager")) {
			frm.add_custom_button(__("Preview Intacct Invoice"), () =>
				frappe.call({
					method: "fuse_projects.commercial.preview_posting",
					args: { doctype: frm.doctype, name: frm.doc.name },
					callback(r) {
						if (r.message) {
							frappe.msgprint({ title: __("What Intacct will receive"), message: `<pre>${frappe.utils.escape_html(r.message)}</pre>`, wide: true });
						}
					},
				})
			);
		}
	},

	boq(frm) {
		if (!frm.doc.boq) return;
		frappe.call({
			method: "fuse_projects.commercial.valuation_lines",
			args: { boq: frm.doc.boq, exclude: frm.is_new() ? null : frm.doc.name },
			callback(r) {
				const data = r.message;
				if (!data) return;
				frm.set_value("project", data.project);
				frm.set_value("customer", data.customer);
				if (!frm.doc.retention_percent) frm.set_value("retention_percent", data.retention_percent);
				frm.set_value("previously_valued", data.previously_valued);
				frm.clear_table("lines");
				data.lines.forEach((line) => frm.add_child("lines", line));
				frm.refresh_field("lines");
				work_out(frm);
			},
		});
	},

	retention_percent: work_out,
});

frappe.ui.form.on("Fuse Valuation Line", {
	percent_complete(frm, cdt, cdn) {
		const line = locals[cdt][cdn];
		line.value_to_date = flt((flt(line.contract_value) * flt(line.percent_complete)) / 100, 2);
		frm.refresh_field("lines");
		work_out(frm);
	},
});

function work_out(frm) {
	const to_date = (frm.doc.lines || []).reduce((sum, line) => sum + flt(line.value_to_date), 0);
	const gross = flt(to_date - flt(frm.doc.previously_valued), 2);
	const retention = flt((gross * flt(frm.doc.retention_percent)) / 100, 2);
	frm.set_value("gross_to_date", flt(to_date, 2));
	frm.set_value("gross_this_valuation", gross);
	frm.set_value("retention_amount", retention);
	frm.set_value("net_due", flt(gross - retention, 2));
}
