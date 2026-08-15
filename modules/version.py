__version__ = "1.27.1"

# Set by tools/dev/release_bump.py --apply, so the About screen cannot drift.
# It read "Release Date: 2026-02-19" on a 1.27.1 build shipped on 2026-08-15,
# because it was a literal in about_menu.py that nothing ever updated.
__release_date__ = "2026-08-15"
