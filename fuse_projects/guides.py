"""The user guides this app ships.

Same arrangement as Manufacturing's: guides travel with the app rather than being uploaded
per site, so a fresh instance is never installed without help. The theme merges what every
Fuse app contributes through the `fuse_guides` hook, so Projects can ship its own without
Manufacturing or the theme knowing anything about them.

WRITTEN in `docs/training/*.md`, SERVED from `public/files/training/*.html`. The build tool
lives in the Manufacturing repo, because one build tool for every app beats a copy per repo
drifting apart:

    python <fuse_manufacturing>/fuse_manufacturing/docs/build_guides.py C:/ClaudeCode/fuse_projects/fuse_projects

The HTML is generated. A hand edit to it is lost on the next build.
"""

# Path is relative to /assets/fuse_projects/files/.
GUIDES = [
	{"title": "Projects", "file": "training/01 Projects.html"},
]


def get_guides():
	"""This app's guides, for the theme's `fuse_guides` hook.

	Copies, not the list itself: the theme merges what every app contributes, and a caller
	that edited the result would be editing this module's own registry.
	"""
	return [
		{
			"title": guide["title"],
			"url": f"/assets/fuse_projects/files/{guide['file']}",
			"is_pdf": guide["file"].lower().endswith(".pdf"),
		}
		for guide in GUIDES
	]
