"""The single source of truth for everything the About screen tells the user.

It lived as literals in ``about_menu.py`` before, and literals go stale without
anyone noticing: a build shipped on 2026-08-15 told users its release date was
2026-02-19, having been wrong for nearly six months. The copyright year was the
same trap waiting for January.

``tools/dev/release_bump.py --apply`` maintains the two fields that change on
their own, and the copyright year is derived rather than typed.
"""

__version__ = "1.27.2"

# Stamped by tools/dev/release_bump.py --apply, so it cannot drift again.
__release_date__ = "2026-08-15"

AUTHOR = "Casey Mathews"
COMPANY = "Web Friendly Help LLC"
TAGLINE = "Helping You Tame Your Access Technology"
LICENSE = "MIT"
WEBSITE = "webfriendlyhelp.com"

# The year the release was made, not the year the machine happens to think it
# is: a copy of 1.27.1 opened in 2028 was still released in 2026, and saying
# otherwise would be a small lie told confidently.
COPYRIGHT_YEAR = __release_date__[:4]
