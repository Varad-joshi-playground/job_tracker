"""
Title relevancy matching + experience + sponsorship + location filters.

Title matching uses domain+role logic rather than exact strings, so it catches
phrasing variations companies use ("AI Platform Engineer", "Engineer, Machine
Learning", "Sr. Data Scientist", etc.) across every ATS uniformly.
"""

import re

# ── Title relevancy matching ──────────────────────────────────────────────────

# Domain keywords (the field)
_DOMAIN = [
    r"\bai\b", r"\ba\.i\.\b", r"artificial intelligence",
    r"\bml\b", r"machine learning", r"\bmle\b",
    r"\bllm\b", r"large language model",
    r"generative ai", r"gen ai", r"genai",
    r"deep learning", r"\bnlp\b", r"computer vision",
    r"data scien", r"data engineer", r"data analy",
    r"analytics",
]

# Role keywords (the function)
_ROLE = [
    r"engineer", r"developer", r"scientist", r"analyst",
    r"architect", r"specialist", r"researcher",
    r"\bsde\b", r"software develop",
]

# Standalone strong matches (don't need domain+role combo)
_STANDALONE = [
    r"machine learning engineer", r"data scientist", r"data engineer",
    r"data analyst", r"analytics engineer", r"ml engineer", r"ai engineer",
    r"software engineer", r"software development engineer",
    r"systems engineer", r"forward deployed engineer",
    r"solutions engineer", r"mlops",
]

# Hard exclusions (override everything). Management roles excluded per config.
_EXCLUDE = [
    r"intern\b", r"internship", r"\bco-?op\b",
    r"\bmanager\b", r"manager,", r"director", r"\bvp\b", r"vice president",
    r"\bhead of\b", r"\bchief\b",
    r"sales", r"marketing", r"recruit", r"account executive",
    r"\bdesigner\b", r"\bux\b", r"\bui/ux\b",
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
_US_KEYWORDS = [
    "united states", "usa", "u.s.", "u.s.a", " us ", "us-", "-us",
    "remote us", "remote - us", "remote (us", "us remote", "remote, us",
]
_US_CITIES = {
    "new york","san francisco","los angeles","seattle","austin","boston",
    "chicago","denver","atlanta","dallas","houston","miami","san diego",
    "san jose","mountain view","palo alto","menlo park","sunnyvale","cupertino",
    "bellevue","redmond","cambridge","brooklyn","washington","salt lake city",
    "portland","phoenix","nashville","raleigh","durham","san antonio",
}

# Clearly foreign markers -> drop
_FOREIGN = [
    "london","united kingdom","uk","england","ireland","dublin","bangalore",
    "bengaluru","hyderabad","mumbai","delhi","pune","chennai","gurugram",
    "germany","berlin","munich","france","paris","spain","madrid","barcelona",
    "netherlands","amsterdam","canada","toronto","vancouver","montreal","ontario",
    "australia","sydney","melbourne","singapore","tokyo","japan","china",
    "brazil","mexico","argentina","poland","warsaw","portugal","lisbon",
    "sweden","stockholm","switzerland","zurich","israel","tel aviv",
    "philippines","manila","vietnam","indonesia","thailand","new zealand",
    "south africa","nigeria","kenya","egypt","dubai","uae","saudi",
]


def classify_location(location: str):
    """
    Returns (keep: bool, confidence: str).
    confidence in {"US", "Unverified", "Foreign"}.
      - US        -> clearly US, keep
      - Unverified-> bare 'Remote'/no signal, keep but flag
      - Foreign   -> clearly non-US, drop
    """
    if not location:
        return True, "Unverified"

    loc = location.lower().strip()

    # Strong US signals
    if any(k in loc for k in _US_KEYWORDS):
        return True, "US"
    # tokenized check for state names / cities / abbreviations
    tokens = re.split(r"[,\s/|()\-]+", loc)
    token_set = {t for t in tokens if t}
    if token_set & _US_STATE_ABBR:
        return True, "US"
    if any(state in loc for state in _US_STATES):
        return True, "US"
    if any(city in loc for city in _US_CITIES):
        return True, "US"

    # Clearly foreign -> drop
    if any(f in loc for f in _FOREIGN):
        return False, "Foreign"

    # Bare "remote" or anything else ambiguous -> keep but flag
    return True, "Unverified"


# ── Experience filter ─────────────────────────────────────────────────────────

EXP_THRESHOLD = 6  # drop roles requiring this many+ years (min of any range)

# Degree terms that signal a Master's/advanced-degree experience alternative.
# The user holds a Master's, so when a JD offers a degree-based reduced-experience
# path, we use the requirement tied to the advanced degree.
_MASTER_TERMS = r"(?:master'?s?|m\.?s\.?\b|m\.?eng|advanced degree|graduate degree|phd|ph\.?d|doctorate)"


def extract_min_experience(text: str):
    """
    Returns the minimum years of experience required, Master's-aware.

    If the JD ties any years-requirement to a Master's/advanced degree
    (e.g. "6 years, or 4 years with a Master's"), we use the advanced-degree
    requirement since the user holds a Master's. Otherwise we fall back to the
    first matching years pattern. Vague ranges return their lower bound.
    """
    t = text.lower()

    # --- Master's-aware pass: years-number within ~50 chars of a degree mention ---
    masters_years = []
    for m in re.finditer(r'(\d+)\s*\+?\s*years?', t):
        num = int(m.group(1))
        start, end = m.span()
        window = t[max(0, start - 50):min(len(t), end + 50)]
        if re.search(_MASTER_TERMS, window):
            masters_years.append(num)
    if masters_years:
        return min(masters_years)

    # --- Fallback: original first-match logic ---
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
    """True if role explicitly requires 6+ yrs minimum. Vague ranges (2-10) pass."""
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
    r"not\s+eligible\s+for\s+(?:visa\s+)?sponsor(?:ship)?",
    # NOTE: plain "must be authorized to work" is NOT filtered (user has work auth)
]]


def requires_no_sponsorship(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(p.search(t) for p in _NO_SPONSOR_RE)
