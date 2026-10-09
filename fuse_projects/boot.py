"""The Project lock, worked out on the server and handed to the desk at boot.

project_locked.js hides the New button where Intacct owns projects. It used to read Intacct
Settings from the browser, and a login without read permission on that doctype — a
construction presenter, a site foreman — was shown "No permission for Intacct Settings" on
every Project list. Read here instead: the answer is a yes/no every user may know, and only
reading the settings record itself needs the permission.

Nothing in here may raise: a boot hook that fails stops the whole desk from loading.
"""

import frappe


def extend(bootinfo):
	try:
		settings = frappe.get_cached_doc("Intacct Settings")
		# The same two conditions as postings.block_project_creation, which refuses the insert.
		bootinfo.fuse_projects_from_intacct = bool(settings.enabled and settings.get("projects_from_intacct"))
	except Exception:
		# No settings yet: nothing is locked, as on any site without Intacct.
		bootinfo.fuse_projects_from_intacct = False
