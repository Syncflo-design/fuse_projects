// Projects are opened in Intacct on a connected site, so the New button should not be
// there to press. The server refuses the insert regardless — this is so nobody meets that
// refusal by accident and thinks the system is broken.
//
// Two conditions, matching postings.block_project_creation: the lock is on AND the site is
// actually connected. A site with no Intacct connection has nowhere else to open a project,
// so nothing is hidden there — which is also why this leaves a demo alone.
//
// The answer comes from the server on frappe.boot (boot.py). Reading Intacct Settings from
// here needs a permission most logins do not have, and Frappe showed the refusal as an
// error on every Project list before any catch could hide it.

function fuse_projects_locked(then) {
	then(!!frappe.boot.fuse_projects_from_intacct);
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
