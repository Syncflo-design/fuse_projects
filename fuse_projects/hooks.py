app_name        = "fuse_projects"
app_title       = "Fuse Projects"
app_publisher   = "Syncflo"
app_description = "Project working for Fuse — ERPNext Projects behind a Fuse switch, tile and workspace."
app_email       = "ops@syncflo.co.za"
app_license     = "MIT"

# The Intacct connection — gateway, credentials and the module switch table — lives in
# fuse_core. Manufacturing is deliberately NOT required: a client can buy Projects on
# its own and never install the stock side at all.
required_apps = ["fuse_core"]

# Both, and a whitelisted fuse_projects.api.setup as well, because after_migrate has been
# seen not to fire on a Frappe Cloud deploy — the code ships and the workspace that goes
# with it does not. Everything in after_install is idempotent, so re-running only closes
# gaps.
after_install = "fuse_projects.install.after_install"
after_migrate = "fuse_projects.install.after_install"

# Whether Intacct owns projects here, for project_locked.js. Worked out on the server so a
# login without access to Intacct Settings is not shown a permission error. See boot.py.
extend_bootinfo = "fuse_projects.boot.extend"

# How this app reaches Fuse Home. Each entry is a dotted path to a callable returning a
# list of dicts: fuse_manufacturing reads the first (it owns the switches, under Active
# Modules in Intacct Settings) and fuse_theme reads the second (it draws the tiles).
#
# Neither of those apps knows this one exists, and both work unchanged without it. That
# is the point — Projects is sold as an option, so it must be installable and removable
# on its own.
#
# A callable rather than the dicts inline: frappe merges hook values from every app, and
# a dotted path is a plain string that cannot be reshaped on the way through.
fuse_modules = ["fuse_projects.registry.get_modules"]
fuse_tiles = ["fuse_projects.registry.get_tiles"]

# The guides this app ships. Merged with every other Fuse app's on the Training page.
fuse_guides = ["fuse_projects.guides.get_guides"]

# Daily. A project is opened, put on hold or closed deliberately, by a person — unlike the
# item master, which moves all day. The job stands down silently when the Intacct connection
# is not switched on, so a site running Projects as an ERPNext-only module does not log a
# failure every night.
scheduler_events = {
	"daily_long": [
		"fuse_projects.sync.scheduled_sync",
	],
}

# The write-back. Both handlers return immediately unless "Post Project Updates" is ticked
# on Intacct Settings, which is OFF by default — so on a site with no connection, and on a
# demo, nothing here fires and the screens work exactly as they do with one.
#
# The two are deliberately not symmetrical. A task push failing warns and leaves the local
# save standing; a timesheet failing raises and takes the submit with it. Stock rules apply
# to time, which is billed — not to a progress marker.
doc_events = {
	# Projects are opened in Intacct on a connected site — a project invented here has no
	# PROJECTID, so nothing booked against it could ever reach Intacct. Refused only where
	# the site is actually connected AND the lock is on, so an ERPNext-only site (and a
	# demo) creates projects exactly as stock ERPNext does.
	"Project": {
		"before_insert": "fuse_projects.postings.block_project_creation",
	},
	# Tasks are deliberately NOT locked the way Projects are. An Intacct task is
	# project-specific — the work breakdown for one job, not a catalogue — so a foreman
	# finding something unplanned on site is authoring exactly the kind of record Intacct
	# expects. It is created there, gets its TASKID back, and is tracked and completed like
	# any other from that moment.
	"Task": {
		"after_insert": "fuse_projects.postings.on_task_insert",
		"on_update": "fuse_projects.postings.on_task_update",
	},
	"Timesheet": {
		"on_submit": "fuse_projects.postings.on_timesheet_submit",
	},
}

# Client scripts shipped with the app rather than typed into the site, so they survive a
# rebuild. Both point at the same file: it defines the form behaviour and the list
# behaviour, and keeping them together means the two cannot drift.
doctype_js = {"Project": "public/js/project_locked.js"}
doctype_list_js = {"Project": "public/js/project_locked.js"}
