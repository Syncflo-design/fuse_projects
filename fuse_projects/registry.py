"""What this app contributes to Fuse Home: one switch and one tile.

Kept out of install.py deliberately. These are read on every home-page load, by another
app, and that call has no business importing workspace-building code.

Nothing here reinvents ERPNext. The tile opens ERPNext's own Projects module through a
Fuse-shaped workspace; the switch decides whether a client sees it at all.
"""

# Permanent. Renaming it orphans a client's saved setting and silently switches the
# module back on — the same rule as fuse_manufacturing's own module keys.
MODULE_KEY = "projects"

# The workspace SLUG, not ["Workspaces", "Fuse Projects"]. That older form builds
# /desk/Workspaces/Fuse%20Projects, which renders as empty skeletons and throws in
# frappe.views.Workspace.show_page — the same fault fuse_theme hit with Stock Control.
ROUTE = "fuse-projects"


def get_modules():
	"""The switch, for the Active Modules table on Intacct Settings.

	It lands there rather than in a settings doctype of its own because a client should
	find every Fuse switch in one place, and because that table already survives a
	migrate without overwriting what someone chose.
	"""
	return [
		{
			"key": MODULE_KEY,
			"label": "Projects",
			"description": "Run work as projects — tasks, timesheets, and what each job has cost.",
		}
	]


def get_tiles():
	"""The tile, for the Fuse home page.

	Filtered by role only. The tile opens a workspace rather than a document, so there is
	nothing for frappe.has_permission to test — and what a user may actually do once
	inside is still decided by document permissions, which is where it belongs.
	"""
	return [
		{
			"key": MODULE_KEY,
			"label": "Projects",
			"blurb": "Jobs, tasks and what they have cost",
			# Emoji, because its neighbours are emoji and one odd tile out looks like a
			# fault. It moves with them when the grid moves to an icon set.
			"icon": "🗂",
			"route": [ROUTE],
			"roles": [
				"Projects User",
				"Projects Manager",
				"Stock Controller",
				"Manufacturing Manager",
			],
		}
	]
