app_name        = "fuse_projects"
app_title       = "Fuse Projects"
app_publisher   = "Syncflo"
app_description = "Project working for Fuse — ERPNext Projects behind a Fuse switch, tile and workspace."
app_email       = "ops@syncflo.co.za"
app_license     = "MIT"

# Both, and a whitelisted fuse_projects.api.setup as well, because after_migrate has been
# seen not to fire on a Frappe Cloud deploy — the code ships and the workspace that goes
# with it does not. Everything in after_install is idempotent, so re-running only closes
# gaps.
after_install = "fuse_projects.install.after_install"
after_migrate = "fuse_projects.install.after_install"

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
