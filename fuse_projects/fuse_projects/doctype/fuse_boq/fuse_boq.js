// A priced bill of quantities, and the actions that follow its award.

const BUILD_UP = ["labour_rate", "plant_rate", "material_rate", "subcontract_rate"];

frappe.ui.form.on("Fuse BOQ", {
	refresh(frm) {
		const awarded = frm.doc.status === "Awarded";
		frm.set_df_property("items", "read_only", awarded ? 1 : 0);
		["title", "project_key", "contract_model", "customer", "markup_percent"].forEach((field) =>
			frm.set_df_property(field, "read_only", awarded ? 1 : 0)
		);

		if (frm.is_new()) return;

		if (!awarded) {
			frm.add_custom_button(__("Award to Intacct"), () => award(frm)).addClass("btn-primary");
			return;
		}

		const create = __("Create");
		frm.add_custom_button(__("Purchase Order"), () => raise_purchase_order(frm), create);
		frm.add_custom_button(
			__("Subcontract Certificate"),
			() => frappe.new_doc("Fuse Subcontract Certificate", { boq: frm.doc.name }),
			create
		);
		if (frm.doc.contract_model === "EPC") {
			frm.add_custom_button(
				__("Client Valuation"),
				() => frappe.new_doc("Fuse Client Valuation", { boq: frm.doc.name }),
				create
			);
		}
		frm.add_custom_button(__("Cost Report"), () =>
			frappe.set_route("query-report", "Project Cost Report", { project: frm.doc.project })
		).addClass("btn-primary");
	},

	markup_percent(frm) {
		total(frm);
	},
});

frappe.ui.form.on("Fuse BOQ Item", {
	qty: price_row,
	rate: price_row,
	labour_rate: price_row,
	plant_rate: price_row,
	material_rate: price_row,
	subcontract_rate: price_row,
	items_remove: total,
});

function price_row(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const built = BUILD_UP.reduce((sum, field) => sum + flt(row[field]), 0);
	if (built) row.rate = built;
	row.amount = flt(flt(row.qty) * flt(row.rate), 2);
	frm.refresh_field("items");
	total(frm);
}

function total(frm) {
	const cost = (frm.doc.items || []).reduce((sum, row) => sum + flt(row.amount), 0);
	frm.set_value("total_cost", flt(cost, 2));
	frm.set_value("contract_value", flt(cost * (1 + flt(frm.doc.markup_percent) / 100), 2));
}

function award(frm) {
	// Award what is saved, never a half-edited form.
	if (frm.is_dirty()) {
		frm.save().then(() => award(frm));
		return;
	}
	const sections = [...new Set((frm.doc.items || []).map((row) => row.section).filter(Boolean))];
	frappe.confirm(
		__(
			"Open <b>{0}</b> in Intacct as project <b>{1}</b>, with {2} tasks and a projected cost of {3}?",
			[
				frappe.utils.escape_html(frm.doc.title),
				frappe.utils.escape_html(frm.doc.project_key),
				sections.length,
				format_currency(frm.doc.total_cost),
			]
		),
		() =>
			frappe.call({
				method: "fuse_projects.commercial.award_boq",
				args: { boq: frm.doc.name },
				freeze: true,
				freeze_message: __("Opening the project in Intacct..."),
				callback(r) {
					if (!r.message) return;
					frappe.show_alert({
						message: __("Project {0} is open in Intacct with {1} tasks.", [
							r.message.project_id,
							r.message.tasks,
						]),
						indicator: "green",
					});
					frm.reload_doc();
				},
			})
	);
}

function raise_purchase_order(frm) {
	const sections = [...new Set((frm.doc.items || []).map((row) => row.section).filter(Boolean))];
	const dialog = new frappe.ui.Dialog({
		title: __("Purchase Order for {0}", [frm.doc.title]),
		fields: [
			{ fieldname: "section", label: __("BOQ Section"), fieldtype: "Select", options: sections.join("\n"), reqd: 1 },
			{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier", reqd: 1 },
			{
				fieldname: "item_code",
				label: __("Item"),
				fieldtype: "Link",
				options: "Item",
				reqd: 1,
				get_query: () => ({ filters: { is_purchase_item: 1, disabled: 0 } }),
			},
			{ fieldname: "column_break_po", fieldtype: "Column Break" },
			{ fieldname: "qty", label: __("Qty"), fieldtype: "Float", reqd: 1 },
			{ fieldname: "rate", label: __("Rate"), fieldtype: "Currency", reqd: 1 },
			{
				fieldname: "schedule_date",
				label: __("Required By"),
				fieldtype: "Date",
				default: frappe.datetime.add_days(frappe.datetime.get_today(), 14),
			},
		],
		primary_action_label: __("Raise and Submit"),
		primary_action(values) {
			frappe.call({
				method: "fuse_projects.commercial.raise_purchase_order",
				args: Object.assign({ boq: frm.doc.name }, values),
				freeze: true,
				callback(r) {
					if (!r.message) return;
					dialog.hide();
					frappe.show_alert({ message: __("{0} raised against {1}", [r.message, values.section]), indicator: "green" });
				},
			});
		},
	});
	dialog.show();
}
