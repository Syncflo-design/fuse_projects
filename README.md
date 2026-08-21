# Fuse Projects

Project working for Fuse: ERPNext's own Projects module, behind a Fuse switch, tile and
workspace.

Third app in the Fuse set, and separately releasable like the other two —
`fuse_manufacturing` (the Intacct integration) and `fuse_theme` (the look and the home
page). Projects is sold as an option, so it installs and uninstalls on its own.

## What it adds

- **A switch** — *Projects*, in the Active Modules table on Intacct Settings, alongside
  Receiving, Works Orders and the rest. Off takes the tile off Fuse Home.
- **A tile** on Fuse Home, for anyone holding Projects User, Projects Manager, Stock
  Controller or Manufacturing Manager.
- **A workspace**, `fuse-projects` — open projects, live tasks, works orders that carry a
  project, timesheets, and the four ERPNext reports worth having on the page.

## What it does not add

No doctypes, no reports, no fields. Every link points at something ERPNext already ships.
The value is the arrangement: one Fuse-shaped page over Projects, instead of sending a
manufacturer into the full Projects module to find four things.

## How it reaches Fuse Home

Two hooks, read by the other two apps:

| Hook | Read by | For |
|---|---|---|
| `fuse_modules` | `fuse_manufacturing.modules.all_modules` | the switch |
| `fuse_tiles` | `fuse_theme.api._all_tiles` | the tile |

Neither of those apps knows this one exists, and both work unchanged without it. A
contributor that raises is skipped rather than allowed to take the settings page or the
home page down with it.

## Install

Requires Frappe and ERPNext v16. `fuse_manufacturing` and `fuse_theme` are optional: with
neither installed the workspace still builds, there is simply no home page to put a tile
on and no table to hold the switch.

After a Frappe Cloud deploy, `after_migrate` has been seen not to fire. Re-apply the
configuration with `fuse_projects.api.setup` (System Manager only).
