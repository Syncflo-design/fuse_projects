"""Whitelisted entry points for Fuse Projects."""

import frappe


@frappe.whitelist()
def setup():
	"""Re-apply this app's site configuration — the workspace and the module switch.

	Exists because after_migrate does not reliably fire on a Frappe Cloud deploy, and
	without this, repairing that needs bench access.
	"""
	frappe.only_for("System Manager")

	from fuse_projects.install import after_install

	return after_install()
