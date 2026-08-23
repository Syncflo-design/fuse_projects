// Projects are opened in Intacct on a connected site, so the New button should not be
// there to press. The server refuses the insert regardless — this is so nobody meets that
// refusal by accident and thinks the system is broken.
//
// Two conditions, matching postings.block_project_creation: the lock is on AND the site is
// actually connected. A site with no Intacct connection has nowhere else to open a project,
// so nothing is hidden there — which is also why this leaves a demo alone.
//
// The settings are read once and cached on frappe.boot, because both the form and the list
// need them and neither should cost a round trip on every render.

function fuse_projects_locked(then) {
	if (frappe.boot.fuse_projects_from_intacct !== undefined) {
		then(frappe.boot.fuse_projects_from_intacct);
		return;
	}
	Promise.all([
		frappe.db.get_single_value("Intacct Settings", "enabled"),
		frappe.db.get_single_value("Intacct Settings", "projects_from_intacct")
	])
		.then(function (values) {
			frappe.boot.fuse_projects_from_intacct = !!(values[0] && values[1]);
			then(frappe.boot.fuse_projects_from_intacct);
		})
		.catch(function () {
			// No settings, or no permission to read them: leave ERPNext as it is rather than
			// hiding a button on a guess.
			frappe.boot.fuse_projects_from_intacct = false;
			then(false);
		});
}

frappe.ui.form.on("Project", {
	onload: function (frm) {
		fuse_projects_locked(function (locked) {
			if (!locked) return;

			// A mirrored project stays fully editable — tasks, timesheets and everything
			// ERPNext adds on top. What goes is the ability to start a new one from here.
			frm.page.clear_primary_action();

			if (frm.is_new()) {
				frappe.msgprint({
					title: __("Projects come from Intacct"),
					message: __(
						"Projects are opened in Intacct on this site and brought across by the " +
						"project sync, with their tasks. Open it in Intacct instead."
					),
					indicator: "orange"
				});
			}
		});
	}
});

// The list view's own Add button. Merged into whatever settings already exist rather than
// assigned over them — replacing frappe.listview_settings wholesale wipes indicators and
// formatters other code has set (CoWork_Helper gotcha, 2026-08-06).
frappe.listview_settings = frappe.listview_settings || {};
var fuse_project_prev_onload = (frappe.listview_settings["Project"] || {}).onload;
frappe.listview_settings["Project"] = Object.assign({}, frappe.listview_settings["Project"], {
	onload: function (listview) {
		if (fuse_project_prev_onload) fuse_project_prev_onload(listview);

		fuse_projects_locked(function (locked) {
			if (!locked) return;
			listview.page.clear_primary_action();
		});
	}
});
