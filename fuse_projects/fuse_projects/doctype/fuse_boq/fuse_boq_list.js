// The NSE demo loader sits on the BOQ list, for the person setting the demo profile up.
// System Manager only. Everything it makes stays in Fuse.

frappe.listview_settings["Fuse BOQ"] = {
	onload(listview) {
		if (!frappe.user.has_role("System Manager")) return;
		listview.page.add_menu_item(__("Load NSE Demo"), () => {
			frappe.prompt(
				[
					{
						fieldname: "project_key",
						label: __("Project Code"),
						fieldtype: "Data",
						default: "NSE-DEMO-5MW",
						reqd: 1,
					},
				],
				(values) =>
					frappe.call({
						method: "fuse_projects.nse_demo.load",
						args: values,
						freeze: true,
						freeze_message: __("Loading the NSE demo..."),
						callback(r) {
							if (!r.message) return;
							frappe.msgprint({
								title: __("NSE demo loaded"),
								indicator: "green",
								message: r.message.summary,
							});
							frappe.set_route("Form", "Fuse BOQ", r.message.boq);
						},
					}),
				__("Load NSE Demo"),
				__("Load")
			);
		});
	},
};
