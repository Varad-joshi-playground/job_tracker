"""
Title relevancy matching + all job filters.

Filters applied (all in this module):
  - Title relevancy (domain+role keyword matching, exclusions)
  - US location (allowlist-only, state names/abbr/cities)
  - Experience (6+ years dropped, Master's-aware, vague ranges kept)
  - Sponsorship (explicit no-sponsor language dropped)
  - PhD required (dropped unless Master's alternative exists)
  - Security clearance required (dropped unless optional/obtainable)
"""

import re

# ── Title relevancy matching ──────────────────────────────────────────────────

_DOMAIN = [
    r"\bai\b", r"\ba\.i\.\b", r"artificial intelligence",
    r"\bml\b", r"machine learning", r"\bmle\b",
    r"\bllm\b", r"large language model",
    r"generative ai", r"gen ai", r"genai",
    r"deep learning", r"\bnlp\b", r"computer vision",
    r"data scien", r"data engineer", r"data analy",
    r"analytics",
]

_ROLE = [
    r"engineer", r"developer", r"scientist", r"analyst",
    r"architect", r"specialist", r"researcher",
    r"\bsde\b", r"software develop",
]

_STANDALONE = [
    r"machine learning engineer", r"data scientist", r"data engineer",
    r"data analyst", r"analytics engineer", r"ml engineer", r"ai engineer",
    r"software engineer", r"software development engineer",
    r"systems engineer", r"forward deployed engineer",
    r"solutions engineer", r"mlops",
    r"member\s+of\s+(?:technical|engineering)\s+staff",
]

_EXCLUDE = [
    r"intern\b", r"internship", r"\bco-?op\b",
    r"\bmanager\b", r"manager,", r"director", r"\bvp\b", r"vice president",
    r"\bhead of\b", r"\bchief\b",
    r"sales", r"marketing", r"recruit", r"account executive",
    r"\bdesigner\b", r"\bux\b", r"\bui/ux\b",
    # Domain exclusions
    r"\bembedded\b",
    r"\bsecurity\b",
    r"\brobotics\b",
    # Seniority exclusions
    r"\blead\b",
    r"\bprincipal\b",
    r"\bstaff\b",
]

_DOMAIN_RE     = [re.compile(p) for p in _DOMAIN]
_ROLE_RE       = [re.compile(p) for p in _ROLE]
_STANDALONE_RE = [re.compile(p) for p in _STANDALONE]
_EXCLUDE_RE    = [re.compile(p) for p in _EXCLUDE]


def title_matches(title: str) -> bool:
    """True if the title is relevant to target AI/ML/data/SWE IC roles."""
    if not title:
        return False
    t = title.lower()

    # Keep overrides — checked before exclusions
    # "Member of Technical Staff" / "Member of Engineering Staff" always kept
    if re.search(r'member\s+of\s+(?:technical|engineering)\s+staff', t):
        return True

    if any(p.search(t) for p in _EXCLUDE_RE):
        return False
    if any(p.search(t) for p in _STANDALONE_RE):
        return True
    has_domain = any(p.search(t) for p in _DOMAIN_RE)
    has_role   = any(p.search(t) for p in _ROLE_RE)
    return has_domain and has_role


# ── Location / US filtering ───────────────────────────────────────────────────

_US_STATES = {
    "alabama","alaska","arizona","arkansas","california","colorado","connecticut",
    "delaware","florida","georgia","hawaii","idaho","illinois","indiana","iowa",
    "kansas","kentucky","louisiana","maine","maryland","massachusetts","michigan",
    "minnesota","mississippi","missouri","montana","nebraska","nevada",
    "new hampshire","new jersey","new mexico","new york","north carolina",
    "north dakota","ohio","oklahoma","oregon","pennsylvania","rhode island",
    "south carolina","south dakota","tennessee","texas","utah","vermont",
    "virginia","washington","west virginia","wisconsin","wyoming",
}

_US_STATE_ABBR = {
    "al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il","in","ia",
    "ks","ky","la","me","md","ma","mi","mn","ms","mo","mt","ne","nv","nh","nj",
    "nm","ny","nc","nd","oh","ok","or","pa","ri","sc","sd","tn","tx","ut","vt",
    "va","wa","wv","wi","wy","dc",
}

_US_POSITIVE = [
    "united states", "usa", "u.s.a", "u.s.",
    "remote us", "remote - us", "remote (us", "us remote", "remote, us",
    "us-remote", "remote/us", "remote | us",
]

_US_CITIES = {
    # Bay Area
    "san francisco", "silicon valley", "bay area",
    "san jose", "santa clara", "sunnyvale", "cupertino", "mountain view",
    "palo alto", "menlo park", "redwood city", "san mateo", "foster city",
    "burlingame", "fremont", "oakland", "berkeley", "emeryville",
    # Seattle metro
    "seattle", "bellevue", "redmond", "kirkland", "bothell", "renton",
    # New York metro
    "new york", "new york city", "manhattan", "brooklyn", "queens",
    "jersey city", "hoboken",
    # Boston metro
    "boston", "cambridge", "waltham", "somerville", "newton", "woburn",
    # Los Angeles metro
    "los angeles", "santa monica", "venice", "culver city",
    "west hollywood", "el segundo", "playa vista", "irvine", "san diego",
    # Texas
    "austin", "round rock", "dallas", "fort worth", "houston", "plano",
    "san antonio", "el paso",
    # Midwest
    "chicago", "evanston", "minneapolis", "st paul", "eden prairie",
    "pittsburgh", "philadelphia", "baltimore",
    "columbus", "cleveland", "cincinnati", "detroit", "ann arbor",
    "kansas city", "st louis", "st. louis", "indianapolis",
    "omaha", "madison", "milwaukee",
    # DC metro
    "washington", "washington dc", "washington d.c", "arlington", "mclean",
    "bethesda", "reston", "herndon", "tysons",
    # Southeast
    "atlanta", "alpharetta", "buckhead",
    "miami", "fort lauderdale", "boca raton",
    "raleigh", "durham", "chapel hill", "research triangle",
    "charlotte", "nashville", "memphis",
    "orlando", "tampa", "jacksonville",
    "richmond", "virginia beach", "norfolk",
    "new orleans", "louisville",
    "oklahoma city", "tulsa",
    # Mountain / Southwest
    "denver", "boulder", "fort collins",
    "phoenix", "scottsdale", "tempe", "chandler",
    "salt lake city", "provo", "lehi",
    "las vegas", "henderson",
    "albuquerque", "tucson",
    # Pacific Northwest
    "portland", "beaverton", "hillsboro",
    "boise", "spokane",
    # California (non-Bay Area)
    "sacramento", "san bernardino", "riverside", "fresno",
    # Northeast
    "hartford", "stamford", "princeton", "parsippany",
    # Other notable
    "hawthorne", "torrance",
    "fargo", "sioux falls",
    "anchorage", "honolulu",
}

_BARE_REMOTE = re.compile(
    r'^(?:remote|work\s+from\s+home|wfh|distributed|anywhere|fully\s+remote|'
    r'remote[\s\-]?first|remote[\s\-]?ok|remote[\s\-]?friendly)$'
)

_MULTI_LOCATION = re.compile(
    r'^(?:\d+|multiple|various|several|many)\s+(?:locations?|offices?|sites?)$'
)


def classify_location(location: str):
    """
    Allowlist-only approach — no foreign blocklist needed.
      - (True,  "US")         -> confirmed US signal, keep
      - (True,  "Unverified") -> bare Remote / no info / multi-location, keep but flag
      - (False, "Foreign")    -> no US signal found, drop
    """
    if not location or not location.strip():
        return True, "Unverified"

    loc = location.lower().strip()

    # Strong US keyword signals
    if any(k in loc for k in _US_POSITIVE):
        return True, "US"

    # Full state names
    if any(state in loc for state in _US_STATES):
        return True, "US"

    # Known US cities
    if any(city in loc for city in _US_CITIES):
        return True, "US"

    # State abbreviations as tokens (e.g. "Austin, TX")
    tokens = set(re.split(r"[,\s/|()\-]+", loc))
    tokens.discard("")
    if tokens & _US_STATE_ABBR:
        return True, "US"

    # State abbreviation as the entire location string (e.g. just "TX")
    if loc.upper() in _US_STATE_ABBR:
        return True, "US"

    # Bare remote — ambiguous, keep but flag
    if _BARE_REMOTE.match(loc):
        return True, "Unverified"

    # Multi-location summary — ambiguous, keep but flag
    if _MULTI_LOCATION.match(loc):
        return True, "Unverified"

    # Everything else — drop
    return False, "Foreign"


# ── Experience filter ─────────────────────────────────────────────────────────

EXP_THRESHOLD = 6

_MASTER_TERMS = r"(?:master'?s?|m\.?s\.?\b|m\.?eng|advanced degree|graduate degree|phd|ph\.?d|doctorate)"


def extract_min_experience(text: str):
    """
    Returns minimum years required, Master's-aware.
    When a JD offers a degree-based reduced-experience path (e.g. "6 years,
    or 4 with a Master's"), uses the advanced-degree requirement since the
    user holds a Master's. Vague ranges return their lower bound.
    """
    t = text.lower()

    # Master's-aware pass: years-number within ~50 chars of a degree mention
    masters_years = []
    for m in re.finditer(r'(\d+)\s*\+?\s*years?', t):
        num = int(m.group(1))
        start, end = m.span()
        window = t[max(0, start - 50):min(len(t), end + 50)]
        if re.search(_MASTER_TERMS, window):
            masters_years.append(num)
    if masters_years:
        return min(masters_years)

    # Fallback: first-match logic
    patterns = [
        r'(\d+)\s*(?:to|-|–|—)\s*(\d+)\s*\+?\s*years?'
        r'(?:\s+of\s+(?:relevant\s+|professional\s+|related\s+|work\s+|industry\s+)?experience)?',
        r'(\d+)\s*\+\s*years?'
        r'(?:\s+of\s+(?:relevant\s+|professional\s+|related\s+|work\s+|industry\s+)?experience)?',
        r'(?:at\s+least|minimum\s+of?|at\s+minimum)\s+(\d+)\s*\+?\s*years?',
        r'(\d+)\s+years?\s+of\s+(?:relevant\s+|professional\s+|related\s+|work\s+|industry\s+)?experience',
        r'(\d+)\s+years?\s+(?:relevant\s+|professional\s+|related\s+|work\s+|industry\s+)?experience',
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            return int(m.group(1))
    return None


def is_overqualified(text: str) -> bool:
    """True if role requires 6+ years minimum. Vague ranges (2-10 yrs) pass."""
    m = extract_min_experience(text)
    return m is not None and m >= EXP_THRESHOLD


# ── Sponsorship filter ────────────────────────────────────────────────────────

_NO_SPONSOR_RE = [re.compile(p) for p in [
    r"will\s+not\s+(?:provide\s+)?(?:visa\s+)?sponsor(?:ship)?",
    r"does\s+not\s+(?:provide\s+)?(?:visa\s+)?sponsor(?:ship)?",
    r"cannot\s+(?:provide\s+)?(?:support\s+)?(?:visa\s+)?sponsor(?:ship)?",
    r"unable\s+to\s+(?:provide\s+)?(?:visa\s+)?sponsor(?:ship)?",
    r"not\s+(?:able\s+to\s+)?(?:provide\s+)?(?:visa\s+)?sponsor(?:ship)?",
    r"sponsorship\s+(?:is\s+)?not\s+(?:available|provided|offered|supported)",
    r"no\s+(?:visa\s+)?sponsorship\s+(?:is\s+)?(?:available|provided|offered)",
    r"authorized?\s+to\s+work\s+(?:in\s+the\s+)?(?:us|united\s+states)\s+without\s+(?:current\s+or\s+future\s+)?(?:visa\s+)?sponsor(?:ship)?",
    r"work\s+authorization\s+(?:that\s+)?(?:does\s+not|will\s+not)\s+require\s+(?:visa\s+)?sponsor(?:ship)?",
    r"without\s+(?:requiring\s+)?(?:current\s+or\s+future\s+)?(?:company\s+)?(?:visa\s+)?sponsor(?:ship)?",
    r"us\s+citizen(?:s)?\s+(?:and\s+|or\s+)?(?:green\s+card\s+holders?\s+)?only",
    r"no\s+(?:h[- ]?1b|opt|cpt|tn|e[- ]?3)\s+sponsor(?:ship)?",
    # Broadened: catches "not eligible for [work visa] sponsorship"
    r"not\s+eligible\s+for\s+(?:\w+\s+){0,3}sponsor(?:ship)?",
    # Catches "this role/position does not offer/provide sponsorship"
    r"(?:role|position|job|opportunity)\s+(?:is\s+)?(?:does\s+)?not\s+(?:offer|provide|include|support|eligible\s+for)\s+(?:\w+\s+){0,2}sponsor(?:ship)?",
    # NOTE: plain "must be authorized to work" is NOT filtered (user has work auth)
]]


def requires_no_sponsorship(text: str) -> bool:
    """True if the text explicitly states visa sponsorship is not available."""
    if not text:
        return False
    t = text.lower()
    return any(p.search(t) for p in _NO_SPONSOR_RE)


# ── PhD filter ────────────────────────────────────────────────────────────────

_PHD_REQUIRED_RE = [re.compile(p) for p in [
    r'(?:requires?|required|must\s+have|need)\s+(?:a\s+)?(?:ph\.?d|doctorate)',
    r'(?:ph\.?d|doctorate)\s+(?:is\s+)?(?:required|mandatory|necessary|needed)',
    r'ph\.?d\.?\s+in\s+[\w\s]+(?:is\s+)?(?:required|mandatory|necessary)',
    r'(?:^|[.;,]\s*)ph\.?d\.?\s+(?:degree\s+)?(?:is\s+)?required',
    r'a\s+ph\.?d\.?(?:\s+degree)?\s+(?:is\s+)?(?:required|mandatory|necessary|needed)',
    r'mandatory[\s:]+(?:\w+\s+)?ph\.?d',
]]

_PHD_KEEP_RE = [re.compile(p) for p in [
    r'ph\.?d\.?\s+(?:is\s+)?(?:preferred|a\s+plus|a\s+bonus|not\s+required|optional|desirable)',
    r"(?:master'?s?|m\.?s\.?|bachelor'?s?)\s+(?:or|and/or)\s+ph\.?d",
    r'ph\.?d\.?\s+or\s+(?:equivalent|master|m\.s)',
    r'no\s+ph\.?d',
    r'ph\.?d\.?\s+(?:is\s+)?not\s+required',
]]


def requires_phd(text: str) -> bool:
    """
    True if PhD is explicitly required with no Master's alternative.
    False if PhD is preferred/optional or a Master's path exists.
    """
    if not text:
        return False
    t = text.lower()
    if any(p.search(t) for p in _PHD_KEEP_RE):
        return False
    return any(p.search(t) for p in _PHD_REQUIRED_RE)


# ── Security clearance filter ─────────────────────────────────────────────────

_CLEARANCE_KEEP_RE = [re.compile(p) for p in [
    r'no\s+(?:security\s+)?clearance\s+(?:is\s+)?required',
    r'clearance\s+(?:is\s+)?(?:not\s+required|a\s+plus|preferred|optional)',
    r'ability\s+to\s+obtain\s+(?:a\s+)?(?:security\s+)?clearance',
    r'will\s+(?:help\s+)?(?:you\s+)?(?:obtain|sponsor|get)\s+(?:a\s+)?clearance',
]]

_CLEARANCE_RE = [re.compile(p) for p in [
    r'top\s*secret(?:\s*/\s*sci)?(?:\s+clearance)?',
    r'ts(?:/sci)?\s+clearance',
    r'security\s+clearance\s+(?:is\s+)?required',
    r'active\s+(?:security\s+)?clearance\s+required',
    r'must\s+(?:hold|have|possess)\s+(?:an?\s+)?(?:active\s+)?(?:security\s+)?clearance',
    r'secret\s+clearance\s+required',
    r'dod\s+(?:secret|top\s+secret)\s+clearance',
    r'(?:public\s+trust|secret|top\s+secret)\s+security\s+clearance',
    r'clearance\s+(?:level\s+)?(?:required|mandatory|needed|must\s+have)',
    r'u\.?s\.?\s+(?:government\s+)?security\s+clearance',
]]


def requires_clearance(text: str) -> bool:
    """
    True if an active security clearance is required.
    False if clearance is optional, preferred, or obtainable after hire.
    """
    if not text:
        return False
    t = text.lower()
    if any(p.search(t) for p in _CLEARANCE_KEEP_RE):
        return False
    return any(p.search(t) for p in _CLEARANCE_RE)
