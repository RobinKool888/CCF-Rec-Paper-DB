import re

WORKSHOP_SUFFIXES = {
    'pd', 'p', 'w', 'nai', 'foci', 'netai', 'optsys', 'spin',
    'fira', 'flexnets', 'taurin', 'visnext', 'net4us', 'ffspin',
}

_MAIN_CONF_RE = re.compile(r'^conf/[a-z0-9]+/\d{4}$')
_MAIN_JOUR_RE = re.compile(r'^journals/[a-z0-9]+/\d{4}')
_WORKSHOP_RE = re.compile(r'^conf/[a-z0-9]+/\d{4}(.+)$')


def normalize_title(title: str) -> str:
    t = title.lower().rstrip('.').strip()
    return re.sub(r'\s+', ' ', t)


def is_main_track(sub_name_abbr: str) -> bool:
    """Return True for canonical conference/journal tracks, False for workshops."""
    if _MAIN_CONF_RE.match(sub_name_abbr):
        return True
    if _MAIN_JOUR_RE.match(sub_name_abbr):
        return True
    m = _WORKSHOP_RE.match(sub_name_abbr)
    if m:
        suffix = m.group(1).lower()
        # If the suffix part is a known workshop token, it's not a main track
        if suffix in WORKSHOP_SUFFIXES:
            return False
        # Any non-empty suffix is a workshop/poster/satellite event
        if suffix:
            return False
    return False
