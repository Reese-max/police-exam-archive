#!/usr/bin/env python3
"""
Comprehensive OCR error fixer for police exam JSON files.
Fixes:
1. Broken English words (spaces inserted inside words by OCR)
2. Concatenated English words (spaces removed between words by OCR)
3. Page header/footer residue in stems
4. Multiple consecutive spaces
5. Five-digit exam code pollution
"""

import json
import os
import re
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

BASE_DIR = Path("/home/user/police-exam-archive/考古題庫")
WORDS_FILE = Path("/home/user/police-exam-archive/tools/english_words.json")
REPORT_FILE = Path("/home/user/police-exam-archive/ocr_fix_report.json")

# ============================================================
# Build English word dictionary
# ============================================================
def build_dictionary():
    """Build comprehensive English word set for validation."""
    words = set()

    # Load from english_words.json
    if WORDS_FILE.exists():
        with open(WORDS_FILE, 'r', encoding='utf-8') as f:
            word_freq = json.load(f)
            words.update(w.lower() for w in word_freq.keys())

    # Common standalone words that are also common suffixes
    # These words, when appearing after a space, are usually NOT part of a broken word
    STANDALONE_SUFFIX_WORDS = {
        "or", "and", "the", "age", "ward", "less", "able", "ice", "ant", "ate",
        "end", "ally", "all", "ear", "eat", "art", "are", "ore", "one", "own",
        "out", "over", "use", "arm", "air", "aid", "arch", "ring", "sing", "king",
        "man", "men", "her", "his", "him", "its", "our", "any", "old", "new",
        "red", "low", "per", "ill", "ion", "lot", "let", "run", "set", "cut",
        "led", "lay", "lie", "log", "net", "nut", "pan", "pen", "pin", "pit",
        "pot", "put", "ram", "ran", "rat", "raw", "ray", "rid", "rim", "rod",
        "rot", "row", "rug", "rum", "sad", "sat", "saw", "say",
    }

    # Common words that are NOT valid as standalone when they appear as suffixes
    NON_STANDALONE_SUFFIXES = {
        "tion", "sion", "ment", "ness", "ence", "ance", "ible", "ous",
        "ive", "ity", "ful", "ling", "ary", "ory", "ery", "ism", "ist",
        "ize", "ise", "dom", "ship", "ster", "eer", "ial", "ual",
        "ics", "ator", "itor", "ence", "ient", "ient", "ure",
        "ment", "ness", "ence", "ance", "tion", "sion",
    }

    return words, STANDALONE_SUFFIX_WORDS, NON_STANDALONE_SUFFIXES


ENGLISH_DICT, STANDALONE_SUFFIXES, NON_STANDALONE_SUFFIXES = build_dictionary()


# ============================================================
# Known broken word fixes (manually verified)
# ============================================================
KNOWN_BROKEN_FIXES = {
    # Verified broken words from scan results
    "vulner able": "vulnerable",
    "depend ence": "dependence",
    "refer ence": "reference",
    "reader ship": "readership",
    "hand ling": "handling",
    "wire less": "wireless",
    "irretriev able": "irretrievable",
    "element ary": "elementary",
    "independ ence": "independence",
    "independ ent": "independent",
    "depend ent": "dependent",
    "differ ence": "difference",
    "differ ent": "different",
    "excel lence": "excellence",
    "excel lent": "excellent",
    "intellig ence": "intelligence",
    "intellig ent": "intelligent",
    "compet ence": "competence",
    "compet ent": "competent",
    "confid ence": "confidence",
    "confid ent": "confident",
    "experi ence": "experience",
    "experi ment": "experiment",
    "influ ence": "influence",
    "influ ent": "influent",
    "evid ence": "evidence",
    "audi ence": "audience",
    "sci ence": "science",
    "sil ence": "silence",
    "viol ence": "violence",
    "pati ence": "patience",
    "resid ence": "residence",
    "pres ence": "presence",
    "abs ence": "absence",
    "sent ence": "sentence",
    "sequ ence": "sequence",
    "frequ ency": "frequency",
    "emerg ency": "emergency",
    "tend ency": "tendency",
    "ag ency": "agency",
    "curr ency": "currency",
    "effici ency": "efficiency",
    "consist ency": "consistency",
    "trans par ency": "transparency",
    "transpar ency": "transparency",
    "preg nancy": "pregnancy",
    "redund ancy": "redundancy",
    "account ability": "accountability",
    "sustain ability": "sustainability",
    "vulner ability": "vulnerability",
    "cap ability": "capability",
    "avail able": "available",
    "suit able": "suitable",
    "comfort able": "comfortable",
    "reason able": "reasonable",
    "consider able": "considerable",
    "remark able": "remarkable",
    "valu able": "valuable",
    "afford able": "affordable",
    "prob able": "probable",
    "accept able": "acceptable",
    "desir able": "desirable",
    "unforgett able": "unforgettable",
    "account able": "accountable",
    "sustain able": "sustainable",
    "renew able": "renewable",
    "flex ible": "flexible",
    "access ible": "accessible",
    "poss ible": "possible",
    "respons ible": "responsible",
    "sens ible": "sensible",
    "terr ible": "terrible",
    "compat ible": "compatible",
    "incred ible": "incredible",
    "vis ible": "visible",
    "invis ible": "invisible",
    "convert ible": "convertible",
    "revers ible": "reversible",
    "govern ment": "government",
    "environ ment": "environment",
    "develop ment": "development",
    "establish ment": "establishment",
    "achieve ment": "achievement",
    "manage ment": "management",
    "treat ment": "treatment",
    "state ment": "statement",
    "require ment": "requirement",
    "employ ment": "employment",
    "depart ment": "department",
    "invest ment": "investment",
    "assess ment": "assessment",
    "amend ment": "amendment",
    "enforce ment": "enforcement",
    "engage ment": "engagement",
    "move ment": "movement",
    "settle ment": "settlement",
    "equip ment": "equipment",
    "retire ment": "retirement",
    "punish ment": "punishment",
    "improve ment": "improvement",
    "announce ment": "announcement",
    "advance ment": "advancement",
    "harass ment": "harassment",
    "embarrass ment": "embarrassment",
    "entertain ment": "entertainment",
    "aware ness": "awareness",
    "willing ness": "willingness",
    "effective ness": "effectiveness",
    "dark ness": "darkness",
    "weak ness": "weakness",
    "ill ness": "illness",
    "fair ness": "fairness",
    "happi ness": "happiness",
    "busi ness": "business",
    "serious ness": "seriousness",
    "conscious ness": "consciousness",
    "useful ness": "usefulness",
    "help less ness": "helplessness",
    "home less ness": "homelessness",
    "care less ness": "carelessness",
    "reck less ness": "recklessness",
    "forgive ness": "forgiveness",
    "danger ous": "dangerous",
    "continu ous": "continuous",
    "obvi ous": "obvious",
    "previ ous": "previous",
    "nerv ous": "nervous",
    "consci ous": "conscious",
    "reli gious": "religious",
    "myster ious": "mysterious",
    "suspici ous": "suspicious",
    "infect ious": "infectious",
    "ambiti ous": "ambitious",
    "presti gious": "prestigious",
    "advanta geous": "advantageous",
    "out rage ous": "outrageous",
    "effect ive": "effective",
    "posit ive": "positive",
    "negat ive": "negative",
    "sensit ive": "sensitive",
    "creat ive": "creative",
    "attract ive": "attractive",
    "product ive": "productive",
    "protect ive": "protective",
    "detect ive": "detective",
    "offens ive": "offensive",
    "defens ive": "defensive",
    "expens ive": "expensive",
    "impress ive": "impressive",
    "aggress ive": "aggressive",
    "excess ive": "excessive",
    "progress ive": "progressive",
    "express ive": "expressive",
    "obsess ive": "obsessive",
    "oppress ive": "oppressive",
    "possess ive": "possessive",
    "success ive": "successive",
    "compuls ive": "compulsive",
    "inclus ive": "inclusive",
    "exclus ive": "exclusive",
    "extens ive": "extensive",
    "intens ive": "intensive",
    "collaborat ive": "collaborative",
    "innovat ive": "innovative",
    "legislat ive": "legislative",
    "commun ity": "community",
    "secur ity": "security",
    "author ity": "authority",
    "major ity": "majority",
    "minor ity": "minority",
    "prior ity": "priority",
    "electric ity": "electricity",
    "ident ity": "identity",
    "public ity": "publicity",
    "complex ity": "complexity",
    "divers ity": "diversity",
    "univer sity": "university",
    "intens ity": "intensity",
    "capac ity": "capacity",
    "specific ity": "specificity",
    "author ize": "authorize",
    "recogn ize": "recognize",
    "organ ize": "organize",
    "minim ize": "minimize",
    "maxim ize": "maximize",
    "optim ize": "optimize",
    "custom ize": "customize",
    "summar ize": "summarize",
    "character ize": "characterize",
    "categor ize": "categorize",
    "neutral ize": "neutralize",
    "final ize": "finalize",
    "symbol ize": "symbolize",
    "normal ize": "normalize",
    "central ize": "centralize",
    "stabil ize": "stabilize",
    "legal ize": "legalize",
    "special ize": "specialize",
    "commercial ize": "commercialize",
    "industrial ize": "industrialize",
    "modern ize": "modernize",
    "professional ize": "professionalize",
    "adver tising": "advertising",
    "manufactur ing": "manufacturing",
    "outsourc ing": "outsourcing",
    "process ing": "processing",
    "publish ing": "publishing",
    "engineer ing": "engineering",
    "monitor ing": "monitoring",
    "counsel ing": "counseling",
    "counsel ling": "counselling",
    "model ling": "modelling",
    "label ling": "labelling",
    "travel ling": "travelling",
    "cancel ling": "cancelling",
    "tun neling": "tunneling",
    "tun nelling": "tunnelling",
    "over whelming": "overwhelming",
    "under lying": "underlying",
    "under standing": "understanding",
    "over looking": "overlooking",
    "over coming": "overcoming",
    "out standing": "outstanding",
    "off icer": "officer",
    "off icers": "officers",
    "off icial": "official",
    "off icially": "officially",
    "off icials": "officials",
    "off ense": "offense",
    "off ensive": "offensive",
    "off ender": "offender",
    "off enders": "offenders",
    "off ering": "offering",
    "off erings": "offerings",
    "pol ice": "police",
    "pol icy": "policy",
    "pol icies": "policies",
    "pol itical": "political",
    "pol itically": "politically",
    "pol itician": "politician",
    "pol itics": "politics",
    "war rant": "warrant",
    "war rants": "warrants",
    "surv ival": "survival",
    "arriv al": "arrival",
    "remov al": "removal",
    "approv al": "approval",
    "disapprov al": "disapproval",
    "propos al": "proposal",
    "dispos al": "disposal",
    "with drawal": "withdrawal",
    "rehears al": "rehearsal",
    "betray al": "betrayal",
    "critic al": "critical",
    "chemic al": "chemical",
    "physic al": "physical",
    "tropic al": "tropical",
    "clinic al": "clinical",
    "music al": "musical",
    "classic al": "classical",
    "logic al": "logical",
    "biologic al": "biological",
    "technologic al": "technological",
    "psychologic al": "psychological",
    "ideologic al": "ideological",
    "sociologic al": "sociological",
    "environment al": "environmental",
    "fundament al": "fundamental",
    "experiment al": "experimental",
    "accident al": "accidental",
    "increment al": "incremental",
    "supplement al": "supplemental",
    "supplement ary": "supplementary",
    "document ary": "documentary",
    "element ary": "elementary",
    "parliament ary": "parliamentary",
    "compliment ary": "complimentary",
    "moment ary": "momentary",
    "custom ary": "customary",
    "revolution ary": "revolutionary",
    "evolution ary": "evolutionary",
    "disciplin ary": "disciplinary",
    "prelimin ary": "preliminary",
    "ordin ary": "ordinary",
    "extraordin ary": "extraordinary",
    "station ary": "stationary",
    "imagin ary": "imaginary",
    "necess ary": "necessary",
    "tempor ary": "temporary",
    "contempor ary": "contemporary",
    "milit ary": "military",
    "solit ary": "solitary",
    "volunt ary": "voluntary",
    "involunt ary": "involuntary",
    "diction ary": "dictionary",
    "mission ary": "missionary",
    "honor ary": "honorary",
    "second ary": "secondary",
    "prim ary": "primary",
    "bound ary": "boundary",
    "ordin ance": "ordinance",
    "perform ance": "performance",
    "toler ance": "tolerance",
    "signific ance": "significance",
    "insur ance": "insurance",
    "appear ance": "appearance",
    "accept ance": "acceptance",
    "resist ance": "resistance",
    "import ance": "importance",
    "assist ance": "assistance",
    "guid ance": "guidance",
    "circum stance": "circumstance",
    "circum stances": "circumstances",
    "investig ation": "investigation",
    "investig ator": "investigator",
    "communic ation": "communication",
    "classific ation": "classification",
    "identific ation": "identification",
    "certific ation": "certification",
    "notific ation": "notification",
    "modific ation": "modification",
    "verific ation": "verification",
    "justific ation": "justification",
    "diversific ation": "diversification",
    "signific ation": "signification",
    "qualific ation": "qualification",
    "organiz ation": "organization",
    "civil ization": "civilization",
    "authoriz ation": "authorization",
    "global ization": "globalization",
    "modern ization": "modernization",
    "custom ization": "customization",
    "optim ization": "optimization",
    "special ization": "specialization",
    "commercial ization": "commercialization",
    "character ization": "characterization",
    "categor ization": "categorization",
    "criminal ization": "criminalization",
    "victim ization": "victimization",
    "ration alization": "rationalization",
    "professional ization": "professionalization",
    "decentral ization": "decentralization",
    "liber alization": "liberalization",
    "general ization": "generalization",
    "hospital ization": "hospitalization",
    "neutral ization": "neutralization",
    "legal ization": "legalization",
    "central ization": "centralization",
    "stabil ization": "stabilization",
    "normal ization": "normalization",
    "priva tization": "privatization",
    "prior itization": "prioritization",
    "real ization": "realization",
    "util ization": "utilization",
    "regul ation": "regulation",
    "popul ation": "population",
    "legisl ation": "legislation",
    "simul ation": "simulation",
    "stimul ation": "stimulation",
    "manipul ation": "manipulation",
    "circul ation": "circulation",
    "accumul ation": "accumulation",
    "formul ation": "formulation",
    "calcul ation": "calculation",
    "articul ation": "articulation",
    "specul ation": "speculation",
    "educ ation": "education",
    "public ation": "publication",
    "communic ations": "communications",
    "applic ation": "application",
    "implic ation": "implication",
    "complic ation": "complication",
    "dedic ation": "dedication",
    "communic ate": "communicate",
    "indic ate": "indicate",
    "practic al": "practical",
    "biomet ric": "biometric",
    "biomet rics": "biometrics",
    "techn ology": "technology",
    "techn ologies": "technologies",
    "techn ological": "technological",
    "psych ology": "psychology",
    "psych ological": "psychological",
    "ideo logy": "ideology",
    "crimin ology": "criminology",
    "socio logy": "sociology",
    "bio logy": "biology",
    "patho logy": "pathology",
    "metho dology": "methodology",
    "Relationalanalysis": "Relational analysis",
    "Functionalanalysis": "Functional analysis",
    "TypeIerror": "Type I error",
    # Round 2: additional broken words found in second scan
    "exist ence": "existence",
    "unthink able": "unthinkable",
    "normal ity": "normality",
    "mental ity": "mentality",
    "predict able": "predictable",
    "commit ment": "commitment",
    "place ment": "placement",
    "individual ity": "individuality",
    "vari able": "variable",
    "reli able": "reliable",
    "understand able": "understandable",
    "Professional ism": "Professionalism",
    "professional ism": "professionalism",
    "Reflect ance": "Reflectance",
    "reflect ance": "reflectance",
    "Ten sion": "Tension",
    "ten sion": "tension",
    "ten ance": "tenance",  # for "main ten ance" -> "maintenance"
    "main tenance": "maintenance",
    "epi tom ize": "epitomize",
    "self less ness": "selflessness",
    "self less": "selfless",
    "sea man ship": "seamanship",
    "sea manship": "seamanship",
    "sports man ship": "sportsmanship",
    "sports manship": "sportsmanship",
    "work man ship": "workmanship",
    "work manship": "workmanship",
    "citizen ship": "citizenship",
    "relation ship": "relationship",
    "member ship": "membership",
    "leader ship": "leadership",
    "partner ship": "partnership",
    "owner ship": "ownership",
    "scholar ship": "scholarship",
    "author ship": "authorship",
    "intern ship": "internship",
    "fellow ship": "fellowship",
    "champion ship": "championship",
    "sponsor ship": "sponsorship",
    "censor ship": "censorship",
    "guardian ship": "guardianship",
    "hard ship": "hardship",
    "worship ship": "worshipship",
    "friend ship": "friendship",
    "steward ship": "stewardship",
    "crafts man ship": "craftsmanship",
    "marks man ship": "marksmanship",
    "micro spectropho tom ery": "microspectrophotometry",
    "spectropho tom ery": "spectrophotometry",
    "Dis per sion": "Dispersion",
    "dis per sion": "dispersion",
    "compart mental ize": "compartmentalize",
    "com part mental ize": "compartmentalize",
    "toburnup ward": "to burn upward",
    "easilyattain able": "easily attainable",
    "withun predict able": "with unpredictable",
    "structuralcoll apse": "structural collapse",
    "andmust": "and must",
    "bymanaging": "by managing",
    # Round 3: final remaining broken words
    "national ity": "nationality",
    "com bus tion": "combustion",
    "base ment": "basement",
    "special ist": "specialist",
    "ex cell ence": "excellence",
    "expert ise": "expertise",
    "Sea ling": "Sealing",
    "sea ling": "sealing",
    "incre mental ism": "incrementalism",
    "effectivet act ics": "effective tactics",
    "shoes ize precise lyto": "shoe size precisely to",
    "toex cell ence": "to excellence",
    "plesofterritorial": "ples of territorial",
    "MixedMethods": "Mixed Methods",
    # Round 5: remaining issues from comprehensive scan
    "man agers": "managers",
    "Trans ship ment": "Transshipment",
    "trans ship ment": "transshipment",
    "Prepared ness": "Preparedness",
    "prepared ness": "preparedness",
    "avoid ance": "avoidance",
    "reflect ive": "reflective",
    "unforgiv able": "unforgivable",
    "depend able": "dependable",
    "practic able": "practicable",
    "pot able": "potable",
    "per miss ible": "permissible",
    "respect ive": "respective",
    "de test able": "detestable",
    "replic able": "replicable",
    "pass ive": "passive",
    "count able": "countable",
    "hospital ity": "hospitality",
    "orpoison ous": "or poisonous",
    "one xcis able": "on excisable",
    "Evadingtaxes": "Evading taxes",
    "aslon gas possible": "as long as possible",
    "yen able building sto and": "tenable building should stop and",
    "are ato another": "area to another",
    "ofa pass ive": "of a passive",
}

# Also add case variations
_extra = {}
for k, v in list(KNOWN_BROKEN_FIXES.items()):
    # Add capitalized version
    cap_k = k[0].upper() + k[1:]
    cap_v = v[0].upper() + v[1:]
    _extra[cap_k] = cap_v
    # Add all-caps version
    _extra[k.upper()] = v.upper()
KNOWN_BROKEN_FIXES.update(_extra)


# ============================================================
# Dynamic broken word detection
# ============================================================
def detect_broken_words(text):
    """Detect broken English words using dictionary validation."""
    fixes = []
    if not isinstance(text, str):
        return fixes

    # Check known patterns first
    for broken, fixed in KNOWN_BROKEN_FIXES.items():
        if broken in text:
            fixes.append((broken, fixed))

    # Dynamic detection: find "word1 word2" where word1+word2 is a valid word
    # but only when it's in an English context
    for m in re.finditer(r'([a-zA-Z]{2,})\s([a-zA-Z]{2,6})\b', text):
        prefix = m.group(1)
        suffix = m.group(2)
        broken = m.group(0)
        combined = prefix + suffix

        # Skip if already handled by known fixes
        if broken in KNOWN_BROKEN_FIXES:
            continue

        # Skip if suffix is a common standalone word
        if suffix.lower() in STANDALONE_SUFFIXES:
            continue

        # Skip very short prefixes that are likely separate words
        if prefix.lower() in {'a', 'an', 'as', 'at', 'be', 'by', 'do', 'go',
                               'he', 'if', 'in', 'is', 'it', 'me', 'my', 'no',
                               'of', 'on', 'or', 'so', 'to', 'up', 'us', 'we',
                               'am', 'an', 'be', 'do', 'go', 'ha', 'hi', 'ho',
                               'id', 'if', 'in', 'is', 'it', 'la', 'lo', 'ma',
                               'me', 'mi', 'mu', 'my', 'no', 'nu', 'of', 'oh',
                               'ok', 'on', 'or', 'ow', 'ox', 'pi', 're', 'so',
                               'to', 'uh', 'um', 'un', 'up', 'us', 'we', 'ye',
                               'the', 'and', 'for', 'are', 'but', 'not', 'you',
                               'all', 'can', 'had', 'has', 'her', 'him', 'his',
                               'how', 'its', 'may', 'new', 'now', 'old', 'our',
                               'out', 'own', 'say', 'she', 'too', 'was', 'who',
                               'any', 'did', 'get', 'got', 'let', 'put', 'ran',
                               'set', 'top', 'try', 'use', 'way', 'yet'}:
            continue

        # Check if combined word is in dictionary but prefix alone is NOT
        if combined.lower() in ENGLISH_DICT:
            if prefix.lower() not in ENGLISH_DICT:
                fixes.append((broken, combined))
            elif suffix.lower() in NON_STANDALONE_SUFFIXES:
                # If suffix is a known non-standalone suffix, it's likely broken
                fixes.append((broken, combined))

    return fixes


# ============================================================
# Concatenated word detection
# ============================================================
KNOWN_CONCAT_FIXES = {
    "Relationalanalysis": "Relational analysis",
    "Functionalanalysis": "Functional analysis",
    "TypeIerror": "Type I error",
    "ContingencyTable": "Contingency Table",
}


def detect_concatenated_words(text):
    """Detect concatenated English words (missing spaces)."""
    fixes = []
    if not isinstance(text, str):
        return fixes

    for concat, fixed in KNOWN_CONCAT_FIXES.items():
        if concat in text:
            fixes.append((concat, fixed))

    return fixes


# ============================================================
# Page residue cleaning
# ============================================================
PAGE_RESIDUE_PATTERNS = [
    (re.compile(r'\s*代號[：:]\s*\d{4,5}(?:[、,]\d{4,5})*\s*'), ' '),
    (re.compile(r'\s*頁次[：:]\s*\d+[/／]\d+\s*'), ' '),
    (re.compile(r'\s*第\s*\d+\s*頁\s*'), ' '),
    (re.compile(r'\s*請接背面\s*'), ' '),
    (re.compile(r'\s*請翻頁\s*'), ' '),
    (re.compile(r'\s*背面尚有試題\s*'), ' '),
]


def fix_page_residue(text):
    """Remove page header/footer residue from text."""
    if not isinstance(text, str):
        return text, 0
    count = 0
    for pat, replacement in PAGE_RESIDUE_PATTERNS:
        new_text = pat.sub(replacement, text)
        if new_text != text:
            count += 1
            text = new_text
    return text.strip(), count


# ============================================================
# Multiple space fixing
# ============================================================
def fix_multiple_spaces(text):
    """Compress multiple consecutive spaces to single space."""
    if not isinstance(text, str):
        return text, 0
    new_text = re.sub(r'[ ]{3,}', ' ', text)
    count = 1 if new_text != text else 0
    return new_text, count


# ============================================================
# Main fix logic
# ============================================================
def fix_text_field(text):
    """Apply all fixes to a single text field. Returns (fixed_text, list_of_changes)."""
    if not isinstance(text, str) or len(text) < 2:
        return text, []

    changes = []
    original = text

    # 1. Fix broken words
    broken_fixes = detect_broken_words(text)
    for broken, fixed in broken_fixes:
        if broken in text:
            text = text.replace(broken, fixed)
            changes.append(("broken_word", broken, fixed))

    # 2. Fix concatenated words
    concat_fixes = detect_concatenated_words(text)
    for concat, fixed in concat_fixes:
        if concat in text:
            text = text.replace(concat, fixed)
            changes.append(("concatenated_word", concat, fixed))

    # 3. Fix multiple spaces
    text, ms_count = fix_multiple_spaces(text)
    if ms_count:
        changes.append(("multiple_spaces", "3+ spaces", "single space"))

    return text, changes


def fix_file(filepath, dry_run=False):
    """Fix all OCR issues in a single JSON file."""
    rel_path = str(filepath.relative_to(BASE_DIR))
    all_changes = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return all_changes, False

    if not isinstance(data, dict):
        return all_changes, False

    modified = False

    # Fix notes
    notes = data.get("notes", [])
    for i, note in enumerate(notes):
        if isinstance(note, str):
            fixed, changes = fix_text_field(note)
            if changes:
                for change in changes:
                    all_changes.append({
                        "file": rel_path,
                        "location": f"notes[{i}]",
                        "type": change[0],
                        "old": change[1],
                        "new": change[2],
                    })
                notes[i] = fixed
                modified = True

    # Fix questions
    questions = data.get("questions", [])
    for q in questions:
        q_num = q.get("number", "?")

        # Fix stem
        stem = q.get("stem", "")
        if isinstance(stem, str):
            fixed, changes = fix_text_field(stem)
            # Also fix page residue in stems
            fixed, pr_count = fix_page_residue(fixed)
            if pr_count:
                changes.append(("page_residue", "header/footer", "removed"))
            if changes:
                for change in changes:
                    all_changes.append({
                        "file": rel_path,
                        "location": f"Q{q_num}.stem",
                        "type": change[0],
                        "old": change[1],
                        "new": change[2],
                    })
                q["stem"] = fixed
                modified = True

        # Fix options
        options = q.get("options", {})
        if isinstance(options, dict):
            for key, val in options.items():
                if isinstance(val, str):
                    fixed, changes = fix_text_field(val)
                    if changes:
                        for change in changes:
                            all_changes.append({
                                "file": rel_path,
                                "location": f"Q{q_num}.option_{key}",
                                "type": change[0],
                                "old": change[1],
                                "new": change[2],
                            })
                        options[key] = fixed
                        modified = True

        # Fix passage
        passage = q.get("passage", "")
        if isinstance(passage, str) and passage:
            fixed, changes = fix_text_field(passage)
            if changes:
                for change in changes:
                    all_changes.append({
                        "file": rel_path,
                        "location": f"Q{q_num}.passage",
                        "type": change[0],
                        "old": change[1],
                        "new": change[2],
                    })
                q["passage"] = fixed
                modified = True

    # Write back if modified
    if modified and not dry_run:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return all_changes, modified


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"{'DRY RUN - ' if dry_run else ''}Comprehensive OCR Fix")
    print(f"Start time: {datetime.now()}")
    print(f"Scanning: {BASE_DIR}")
    print()

    json_files = sorted(BASE_DIR.rglob("*.json"))
    print(f"Found {len(json_files)} JSON files")

    all_changes = []
    files_modified = 0
    files_scanned = 0

    for filepath in json_files:
        files_scanned += 1
        changes, modified = fix_file(filepath, dry_run=dry_run)
        if changes:
            all_changes.extend(changes)
        if modified:
            files_modified += 1

        if files_scanned % 100 == 0:
            print(f"  Processed {files_scanned} files, {len(all_changes)} fixes so far...")

    # Build report
    by_type = defaultdict(int)
    by_file = defaultdict(int)
    for change in all_changes:
        by_type[change["type"]] += 1
        by_file[change["file"]] += 1

    report = {
        "metadata": {
            "fix_time": datetime.now().isoformat(),
            "dry_run": dry_run,
            "files_scanned": files_scanned,
            "files_modified": files_modified,
            "total_fixes": len(all_changes),
        },
        "fixes_by_type": dict(by_type),
        "fixes_by_file": dict(sorted(by_file.items(), key=lambda x: -x[1])),
        "all_changes": all_changes,
    }

    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"{'DRY RUN ' if dry_run else ''}Fix complete!")
    print(f"Files scanned: {files_scanned}")
    print(f"Files modified: {files_modified}")
    print(f"Total fixes applied: {len(all_changes)}")
    print(f"\nFixes by type:")
    for t, count in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}")
    print(f"\nTop 20 files with most fixes:")
    for fpath, count in sorted(by_file.items(), key=lambda x: -x[1])[:20]:
        print(f"  {fpath}: {count}")
    print(f"\nReport saved to: {REPORT_FILE}")


if __name__ == "__main__":
    main()
