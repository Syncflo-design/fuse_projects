// The NSE demo loader sits on the BOQ list, for the person setting the demo profile up.
// System Manager only: it writes vendors and a customer into the connected Intacct company.

frappe.listview_settings["Fuse BOQ"] = {
	onload(listview) {
		if (!frappe.user.has_role("System Manager")) return;
		listview.page.add_menu_item(__("Load NSE Demo"), () => {
			frappe.prompt(
				[
					{
						fieldname: "project_key",
						label: __("Intacct Project ID"),
						fieldtype: "Data",
						default: "NSE-DEMO-5MW",
						reqd: 1,
						description: __("Use a fresh key for a rehearsal, e.g. NSE-REH-01."),
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
