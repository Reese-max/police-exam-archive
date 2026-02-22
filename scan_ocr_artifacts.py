#!/usr/bin/env python3
"""
Comprehensive OCR artifact scanner for police exam JSON files.
Scans all exam files for:
1. English words broken by spaces (e.g. "off icer", "in vesti gate")
2. Missing spaces between words (e.g. "AIchat", "ofthe", "theU.S.")
3. Broken/garbled characters or encoding issues

Refined to minimize false positives.
"""

import json
import os
import re
import sys
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path("/home/user/police-exam-archive/考古題庫")
OUTPUT_FILE = Path("/home/user/police-exam-archive/agent1_ocr_report.json")

# Top-level non-exam files to skip
SKIP_FILES = {
    "answer_verification_report.json",
    "download_summary.json",
    "extraction_stats.json",
    "失敗清單.json",
}

# ============================================================
# Helper: Check if text is in English context
# ============================================================
def is_english_context(text, pos, window=40):
    """Check if position is within English text context."""
    start = max(0, pos - window)
    end = min(len(text), pos + window)
    ctx = text[start:end]
    ascii_alpha = sum(1 for c in ctx if c.isascii() and c.isalpha())
    total_chars = sum(1 for c in ctx if c.isalpha())
    if total_chars == 0:
        return False
    return ascii_alpha / total_chars > 0.3

# ============================================================
# 1. BROKEN ENGLISH WORDS (spaces inserted mid-word by OCR)
# ============================================================

# Specific known OCR word-break patterns (high confidence)
SPECIFIC_OCR_BREAKS = [
    # Police/legal terms
    (re.compile(r'\b[Oo]ff\s+icer', re.IGNORECASE), "off icer -> officer"),
    (re.compile(r'\b[Pp]ol\s+ice\b', re.IGNORECASE), "pol ice -> police"),
    (re.compile(r'\bin\s*vesti\s*gat', re.IGNORECASE), "investigate broken"),
    (re.compile(r'\bcon\s+stitu', re.IGNORECASE), "constitu... broken"),
    (re.compile(r'\bgov\s+ern', re.IGNORECASE), "govern... broken"),
    (re.compile(r'\bad\s+minis', re.IGNORECASE), "adminis... broken"),
    (re.compile(r'\ben\s+force', re.IGNORECASE), "enforce broken"),
    (re.compile(r'\bde\s+part\s*ment', re.IGNORECASE), "department broken"),
    (re.compile(r'\bcom\s+mun\s*i', re.IGNORECASE), "communi... broken"),
    (re.compile(r'\bpro\s+tect', re.IGNORECASE), "protect broken"),
    (re.compile(r'\bpre\s+vent', re.IGNORECASE), "prevent broken"),
    (re.compile(r'\bre\s+spons', re.IGNORECASE), "respons... broken"),
    (re.compile(r'\bre\s+port(?!ed|s|ing)\b', re.IGNORECASE), "report broken"),
    (re.compile(r'\bsur\s+veil', re.IGNORECASE), "surveil... broken"),
    (re.compile(r'\bcrim\s+inal', re.IGNORECASE), "criminal broken"),
    (re.compile(r'\bjur\s*is\s*dic', re.IGNORECASE), "jurisdic... broken"),
    (re.compile(r'\bpun\s+ish', re.IGNORECASE), "punish broken"),
    (re.compile(r'\bwar\s+rant', re.IGNORECASE), "warrant broken"),
    (re.compile(r'\bsus\s+pect', re.IGNORECASE), "suspect broken"),
    (re.compile(r'\bar\s+rest', re.IGNORECASE), "arrest broken"),
    (re.compile(r'\bevi\s+dence', re.IGNORECASE), "evidence broken"),
    (re.compile(r'\bwit\s+ness', re.IGNORECASE), "witness broken"),
    (re.compile(r'\bpros\s+ecu', re.IGNORECASE), "prosecu... broken"),
    (re.compile(r'\bde\s+fend', re.IGNORECASE), "defend broken"),
    (re.compile(r'\bse\s+cur\s*ity', re.IGNORECASE), "security broken"),
    (re.compile(r'\bau\s+thor', re.IGNORECASE), "author... broken"),
    (re.compile(r'\breg\s+ulat', re.IGNORECASE), "regulat... broken"),
    (re.compile(r'\bviol\s+at', re.IGNORECASE), "violat... broken"),
    (re.compile(r'\bleg\s+is\s*lat', re.IGNORECASE), "legislat... broken"),
    (re.compile(r'\bcer\s+tif', re.IGNORECASE), "certif... broken"),
    (re.compile(r'\bemer\s+gen', re.IGNORECASE), "emergen... broken"),
    (re.compile(r'\bfor\s+eign', re.IGNORECASE), "foreign broken"),
    (re.compile(r'\bterr\s+or', re.IGNORECASE), "terror... broken"),
    (re.compile(r'\bsmug\s+gl', re.IGNORECASE), "smuggl... broken"),
    (re.compile(r'\bimm\s+igr', re.IGNORECASE), "immigr... broken"),
    (re.compile(r'\bpass\s+port', re.IGNORECASE), "passport broken"),
    (re.compile(r'\bcust\s+oms', re.IGNORECASE), "customs broken"),
    (re.compile(r'\btech\s+nol', re.IGNORECASE), "technol... broken"),
    (re.compile(r'\bdig\s+ital', re.IGNORECASE), "digital broken"),
    (re.compile(r'\belec\s+tron', re.IGNORECASE), "electron... broken"),
    (re.compile(r'\bnet\s+work(?!s?\s+(?:of|with|in|on|at|to|for|and|or|is|are|was|were|has|have|that|which))', re.IGNORECASE), "network broken"),
    (re.compile(r'\bdata\s+base', re.IGNORECASE), "database broken"),
    (re.compile(r'\bsoft\s+ware', re.IGNORECASE), "software broken"),
    (re.compile(r'\bhard\s+ware', re.IGNORECASE), "hardware broken"),
    (re.compile(r'\banal\s+ysis', re.IGNORECASE), "analysis broken"),
    (re.compile(r'\bstat\s+istic', re.IGNORECASE), "statistic broken"),
    (re.compile(r'\bpsy\s+chol', re.IGNORECASE), "psychol... broken"),
    (re.compile(r'\bphil\s+os\s*oph', re.IGNORECASE), "philosoph... broken"),
    (re.compile(r'\benvi\s+ron', re.IGNORECASE), "environ... broken"),
    (re.compile(r'\bpoll\s+ut', re.IGNORECASE), "pollut... broken"),
    (re.compile(r'\bpop\s+ulat', re.IGNORECASE), "populat... broken"),
    (re.compile(r'\becon\s+om', re.IGNORECASE), "econom... broken"),
    (re.compile(r'\bdem\s+ocr', re.IGNORECASE), "democr... broken"),
    (re.compile(r'\bpar\s+lia', re.IGNORECASE), "parlia... broken"),
    (re.compile(r'\buni\s+vers', re.IGNORECASE), "univers... broken"),
    (re.compile(r'\bres\s+taur', re.IGNORECASE), "restaur... broken"),
    (re.compile(r'\bhos\s+pital', re.IGNORECASE), "hospital broken"),
    (re.compile(r'\bcom\s+preh', re.IGNORECASE), "compreh... broken"),
    (re.compile(r'\btrans\s+lat', re.IGNORECASE), "translat... broken"),
    (re.compile(r'\binter\s+view', re.IGNORECASE), "interview broken"),
    (re.compile(r'\bim\s+port\s*ant', re.IGNORECASE), "important broken"),
    (re.compile(r'\bex\s+peri\s*ence', re.IGNORECASE), "experience broken"),
    (re.compile(r'\binfo\s*r\s*ma\s*tion', re.IGNORECASE), "information broken"),
    (re.compile(r'\bor\s+gan\s*iz', re.IGNORECASE), "organiz... broken"),
    (re.compile(r'\bcom\s+mit', re.IGNORECASE), "commit... broken"),
    (re.compile(r'\bap\s+preh', re.IGNORECASE), "appreh... broken"),
    (re.compile(r'\bsafe\s+guard', re.IGNORECASE), "safeguard broken"),
    (re.compile(r'\bcount\s+er\s*feit', re.IGNORECASE), "counterfeit broken"),
    (re.compile(r'\bcy\s+ber', re.IGNORECASE), "cyber... broken"),
    (re.compile(r'\bnon\s+prof', re.IGNORECASE), "nonprof... broken"),
    (re.compile(r'\bprob\s+lem', re.IGNORECASE), "problem broken"),
    (re.compile(r'\bnec\s+ess', re.IGNORECASE), "necess... broken"),
    (re.compile(r'\bposs\s+ib', re.IGNORECASE), "possib... broken"),
    (re.compile(r'\bavail\s+ab', re.IGNORECASE), "availab... broken"),
    (re.compile(r'\bapprop\s+ri', re.IGNORECASE), "appropri... broken"),
    (re.compile(r'\beffec\s+tive', re.IGNORECASE), "effective broken"),
    (re.compile(r'\bsig\s+nif', re.IGNORECASE), "signif... broken"),
    (re.compile(r'\bpart\s+ic\s*ular', re.IGNORECASE), "particular broken"),
    (re.compile(r'\bestab\s+lish', re.IGNORECASE), "establish broken"),
    (re.compile(r'\bdeterm\s+ine', re.IGNORECASE), "determine broken"),
    (re.compile(r'\bmaint\s+ain', re.IGNORECASE), "maintain broken"),
    (re.compile(r'\bprov\s+ide', re.IGNORECASE), "provide broken"),
    (re.compile(r'\breq\s+uire', re.IGNORECASE), "require broken"),
    (re.compile(r'\bcont\s+inue', re.IGNORECASE), "continue broken"),
    (re.compile(r'\bident\s+ify', re.IGNORECASE), "identify broken"),
    (re.compile(r'\brec\s+ogniz', re.IGNORECASE), "recogniz... broken"),
    (re.compile(r'\bimple\s+ment', re.IGNORECASE), "implement broken"),
    (re.compile(r'\bcomm\s+unic', re.IGNORECASE), "communic... broken"),
    (re.compile(r'\brel\s+ation', re.IGNORECASE), "relation... broken"),
    (re.compile(r'\boper\s+ation', re.IGNORECASE), "operation broken"),
    (re.compile(r'\bperf\s+orm', re.IGNORECASE), "perform broken"),
    (re.compile(r'\bman\s+age\s*ment', re.IGNORECASE), "management broken"),
    (re.compile(r'\bres\s+ource', re.IGNORECASE), "resource broken"),
    (re.compile(r'\bprog\s+ram', re.IGNORECASE), "program broken"),
    (re.compile(r'\bstand\s+ard', re.IGNORECASE), "standard broken"),
    (re.compile(r'\bindiv\s+idual', re.IGNORECASE), "individual broken"),
    (re.compile(r'\bpers\s+onn', re.IGNORECASE), "personn... broken"),
    (re.compile(r'\bdomes\s+tic', re.IGNORECASE), "domestic broken"),
    (re.compile(r'\btraf\s+fic', re.IGNORECASE), "traffic broken"),
    (re.compile(r'\bacc\s+ident', re.IGNORECASE), "accident broken"),
    (re.compile(r'\bdan\s+ger', re.IGNORECASE), "danger broken"),
    (re.compile(r'\bassist\s+ance', re.IGNORECASE), "assistance broken"),
    (re.compile(r'\bdoc\s+ument', re.IGNORECASE), "document broken"),
    (re.compile(r'\bveh\s+icle', re.IGNORECASE), "vehicle broken"),
    (re.compile(r'\bweap\s+on', re.IGNORECASE), "weapon broken"),
    (re.compile(r'\bsub\s+stance', re.IGNORECASE), "substance broken"),
    (re.compile(r'\balco\s+hol', re.IGNORECASE), "alcohol broken"),
    (re.compile(r'\bnarc\s+otic', re.IGNORECASE), "narcotic broken"),
    (re.compile(r'\bbord\s+er', re.IGNORECASE), "border broken"),
    (re.compile(r'\binter\s+nation', re.IGNORECASE), "internation... broken"),
    (re.compile(r'\bnat\s+ion\s*al', re.IGNORECASE), "national broken"),
    (re.compile(r'\bab\s+sol\s*ute', re.IGNORECASE), "absolute broken"),
    (re.compile(r'\bimmed\s+iate', re.IGNORECASE), "immediate broken"),
    (re.compile(r'\borig\s+inal', re.IGNORECASE), "original broken"),
    (re.compile(r'\baddit\s+ion', re.IGNORECASE), "addition... broken"),
    (re.compile(r'\bsep\s+arat', re.IGNORECASE), "separat... broken"),
    (re.compile(r'\bamend\s+ment', re.IGNORECASE), "amendment broken"),
    (re.compile(r'\bprov\s+ision', re.IGNORECASE), "provision broken"),
    (re.compile(r'\breas\s+on\s*able', re.IGNORECASE), "reasonable broken"),
    (re.compile(r'\bprob\s+able', re.IGNORECASE), "probable broken"),
    (re.compile(r'\bac\s+curat', re.IGNORECASE), "accurat... broken"),
    (re.compile(r'\bap\s+par\s*ent', re.IGNORECASE), "apparent broken"),
    (re.compile(r'\brehab\s+ilit', re.IGNORECASE), "rehabilit... broken"),
    (re.compile(r'\bincar\s+cer', re.IGNORECASE), "incarcer... broken"),
    (re.compile(r'\bcorrect\s+ion', re.IGNORECASE), "correction broken"),
    (re.compile(r'\bprob\s+ation', re.IGNORECASE), "probation broken"),
    (re.compile(r'\bfor\s+ens', re.IGNORECASE), "forens... broken"),
    (re.compile(r'\bintel\s+lig', re.IGNORECASE), "intellig... broken"),
    (re.compile(r'\bex\s+am\s*in', re.IGNORECASE), "examin... broken"),
    (re.compile(r'\bdescr\s+ip', re.IGNORECASE), "descrip... broken"),
    (re.compile(r'\bexplan\s+ation', re.IGNORECASE), "explanation broken"),
    (re.compile(r'\bserge\s+ant', re.IGNORECASE), "sergeant broken"),
    (re.compile(r'\blieu\s+ten', re.IGNORECASE), "lieuten... broken"),
    (re.compile(r'\bcapt\s+ain', re.IGNORECASE), "captain broken"),
    (re.compile(r'\bcorp\s+oral', re.IGNORECASE), "corporal broken"),
    (re.compile(r'\bsher\s+iff', re.IGNORECASE), "sheriff broken"),
    (re.compile(r'\bdetect\s+ive', re.IGNORECASE), "detective broken"),
    (re.compile(r'\bconvey\s*or\s*belt', re.IGNORECASE), "conveyorbelt broken"),
    # New: additional patterns seen in the data
    (re.compile(r'\bpass\s+enger', re.IGNORECASE), "passenger broken"),
    (re.compile(r'\bsentence\s+s(?=\s*in)', re.IGNORECASE), "sentences broken"),
    (re.compile(r'\bpris\s+on', re.IGNORECASE), "prison broken"),
    (re.compile(r'\bcount\s+ries', re.IGNORECASE), "countries broken"),
    (re.compile(r'\bred\s+ucing', re.IGNORECASE), "reducing broken"),
    (re.compile(r'\bThom\s+pson', re.IGNORECASE), "Thompson broken"),
    (re.compile(r'\bcoord\s+in', re.IGNORECASE), "coordin... broken"),
    (re.compile(r'\bterm\s+in\s*at', re.IGNORECASE), "terminat... broken"),
    (re.compile(r'\bcollegi\s+ate', re.IGNORECASE), "collegiate broken"),
    (re.compile(r'\bfai\s+led', re.IGNORECASE), "failed broken"),
    (re.compile(r'\bscam', re.IGNORECASE), None),  # skip, not broken
]
# Filter out None entries
SPECIFIC_OCR_BREAKS = [(p, d) for p, d in SPECIFIC_OCR_BREAKS if d is not None]

# ============================================================
# General broken word detection via known word dictionary
# ============================================================

# Large set of English words commonly seen in police exam context
KNOWN_WORDS = {
    "officer", "officers", "police", "policing", "patrol", "detective",
    "sergeant", "lieutenant", "captain", "corporal", "sheriff",
    "investigation", "investigate", "investigator", "investigating",
    "enforcement", "enforce", "enforcing", "enforced",
    "criminal", "criminals", "crime", "crimes",
    "arrest", "arrested", "arresting", "arrests",
    "suspect", "suspects", "suspected", "suspicion",
    "evidence", "evident", "evidently",
    "witness", "witnesses", "witnessed",
    "prosecution", "prosecutor", "prosecute", "prosecuted",
    "defendant", "defense", "defensive",
    "jurisdiction", "judicial", "justice",
    "correctional", "correction", "corrections",
    "probation", "parole", "parolee",
    "forensic", "forensics",
    "surveillance", "surveilling",
    "intelligence", "intelligent",
    "security", "secure", "securing", "secured",
    "authority", "authorities", "authorize", "authorized",
    "department", "departments",
    "government", "governor", "governing",
    "administration", "administrative", "administrator",
    "constitution", "constitutional", "constitutionality",
    "legislation", "legislative", "legislature",
    "regulation", "regulatory", "regulate", "regulated",
    "violation", "violate", "violating", "violated",
    "punishment", "punish", "punishing", "punished",
    "rehabilitation", "rehabilitate",
    "incarceration", "incarcerate",
    "community", "communities",
    "professional", "profession",
    "certificate", "certification",
    "examination", "examine", "examining", "examined",
    "following", "followed",
    "statement", "statements",
    "description", "describe", "describing", "described",
    "explanation", "explain", "explaining", "explained",
    "according", "accordance",
    "regarding", "regard",
    "concerning", "concern", "concerned",
    "including", "include", "included", "includes",
    "between", "among", "within", "without", "through", "throughout",
    "because", "however", "therefore", "although", "whether",
    "important", "importance", "importantly",
    "different", "difference", "differently",
    "necessary", "necessarily", "necessity",
    "possible", "possibly", "possibility",
    "available", "availability",
    "appropriate", "appropriately",
    "responsible", "responsibility",
    "effective", "effectively", "effectiveness",
    "significant", "significantly", "significance",
    "particular", "particularly",
    "establish", "established", "establishment",
    "determine", "determined", "determination",
    "consider", "considered", "consideration",
    "maintain", "maintained", "maintenance",
    "provide", "provided", "providing", "provider",
    "require", "required", "requirement", "requirements",
    "continue", "continued", "continuing",
    "develop", "developed", "development", "developing",
    "increase", "increased", "increasing",
    "improve", "improved", "improvement",
    "prevent", "prevented", "prevention", "preventive",
    "protect", "protected", "protection", "protective",
    "identify", "identified", "identification",
    "recognize", "recognized", "recognition",
    "organize", "organized", "organization",
    "implement", "implemented", "implementation",
    "experience", "experienced",
    "information", "inform", "informed",
    "technology", "technical", "technique",
    "procedure", "procedures", "procedural",
    "practice", "practices", "practical",
    "training", "trained", "trainer",
    "education", "educational", "educate",
    "communication", "communicate",
    "relationship", "relative", "relatively",
    "situation", "situational",
    "condition", "conditions", "conditional",
    "operation", "operational", "operate",
    "performance", "perform", "performing",
    "management", "manage", "manager",
    "resource", "resources",
    "service", "services", "serving",
    "program", "programs", "programming",
    "system", "systems", "systematic",
    "process", "processes", "processing",
    "control", "controls", "controlled",
    "problem", "problems", "problematic",
    "standard", "standards", "standardize",
    "individual", "individuals", "individually",
    "personal", "personally", "personnel",
    "physical", "physically",
    "emotional", "emotionally",
    "domestic", "violence",
    "traffic", "accident", "accidents",
    "dangerous", "danger",
    "emergency", "emergencies",
    "response", "respond", "responding", "respondent",
    "assistance", "assist", "assistant",
    "interview", "interviews", "interviewing",
    "report", "reports", "reporting", "reported",
    "record", "records", "recording", "recorded",
    "document", "documents", "documentation",
    "search", "warrant", "warrants",
    "property", "properties",
    "vehicle", "vehicles",
    "weapon", "weapons",
    "substance", "substances",
    "alcohol", "alcoholic",
    "narcotic", "narcotics",
    "smuggling", "smuggle", "smuggler",
    "counterfeit", "counterfeiting",
    "immigration", "immigrant",
    "border", "borders", "boundary",
    "passport", "passports",
    "customs",
    "international", "nationally",
    "national", "nation",
    "foreign", "foreigner", "foreigners",
    "terrorist", "terrorism",
    "cybercrime", "cyber", "cyberbullying",
    "computer", "computers",
    "internet", "network", "networks",
    "database", "databases",
    "software", "hardware",
    "digital", "digitally",
    "electronic", "electronics",
    "analysis", "analyze", "analytical",
    "statistic", "statistics", "statistical",
    "research", "researcher", "researchers",
    "theory", "theories", "theoretical",
    "principle", "principles",
    "strategy", "strategies", "strategic",
    "policy", "policies",
    "objective", "objectives",
    "approach", "approaches",
    "method", "methods", "methodology",
    "measure", "measures", "measurement",
    "assessment", "assess", "assessing",
    "evaluation", "evaluate", "evaluating",
    "amendment", "amend", "amended",
    "provision", "provisions",
    "article", "articles",
    "sentence", "sentences",
    "reasonable", "reasonably",
    "probable", "probably", "probability",
    "absolute", "absolutely",
    "specific", "specifically", "specification",
    "general", "generally", "generalize",
    "complete", "completely", "completion",
    "accurate", "accurately", "accuracy",
    "correct", "correctly",
    "proper", "properly",
    "certain", "certainly", "certainty",
    "obvious", "obviously",
    "apparent", "apparently",
    "immediate", "immediately",
    "current", "currently",
    "recent", "recently",
    "previous", "previously",
    "original", "originally",
    "additional", "additionally",
    "separate", "separately", "separation",
    "together", "another",
    "people", "person", "persons",
    "number", "public",
    "during", "enough",
    "vocabulary", "grammar", "comprehension",
    "paragraph", "passage", "reading",
    "translate", "translation",
    "dialogue", "conversation",
    "restaurant", "hospital",
    "university", "college", "school",
    "president", "minister", "parliament",
    "democracy", "democratic",
    "freedom", "liberty",
    "society", "social", "socially",
    "economy", "economic", "economically",
    "environment", "environmental",
    "population", "pollutant", "pollution",
    "psychology", "psychological",
    "philosophy", "philosophical",
    "passenger", "passengers",
    "dangerous", "endanger", "endangered",
    "countries", "country",
    "conveyorbelt",
    "collegiate",
    "Thompson",
    "coordinated", "coordinator",
    "terminated", "termination",
    "reducing", "reduced",
    "safeguard", "safeguards",
    "apprehend", "apprehended",
    "acquitted",
    "sentence", "sentenced",
    "eligible", "eligibility",
    "proceeded", "proceeding",
    "concerning",
    "colleague", "colleagues",
    "threatened", "threatening",
    "demolished", "demolishment",
}

# Common short English words (to avoid flagging "in the" as "inthe")
COMMON_SHORT_WORDS = set()
with open('/dev/null', 'w') as _:  # just to define the set
    pass
COMMON_SHORT_WORDS = {
    'a', 'i', 'an', 'am', 'as', 'at', 'be', 'by', 'do', 'go', 'he', 'if', 'in',
    'is', 'it', 'me', 'my', 'no', 'of', 'on', 'or', 'so', 'to', 'up', 'us', 'we',
    'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'any', 'can', 'had',
    'her', 'was', 'one', 'our', 'out', 'has', 'his', 'how', 'its', 'let', 'may',
    'new', 'now', 'old', 'see', 'way', 'who', 'did', 'get', 'got', 'him', 'own',
    'say', 'she', 'too', 'use', 'per', 'set', 'put', 'run', 'sit', 'try', 'ask',
    'end', 'far', 'few', 'big', 'bit', 'cut', 'hot', 'lot', 'low', 'yet', 'red',
    'off', 'ill', 'due', 'aid', 'aim', 'ban', 'bar', 'bat', 'bay', 'bed', 'boy',
    'bus', 'buy', 'car', 'day', 'dog', 'ear', 'eat', 'eye', 'fit', 'fly', 'fun',
    'god', 'gun', 'hat', 'hit', 'job', 'key', 'law', 'lay', 'leg', 'lie', 'lip',
    'map', 'man', 'men', 'mix', 'nor', 'oil', 'pay', 'ran', 'raw', 'rid', 'row',
    'sea', 'six', 'son', 'ten', 'top', 'two', 'van', 'war', 'win', 'won', 'yes',
    'non', 'sub', 'via', 'pro', 'con', 'age', 'ago', 'air', 'art', 'act', 'add',
    'arm', 'cup', 'era', 'eve', 'fan', 'fat', 'fee', 'fog', 'for', 'fox', 'fur',
    'gap', 'gas', 'hen', 'hip', 'hug', 'ice', 'ink', 'inn', 'ion', 'ivy', 'jam',
    'jar', 'jaw', 'jet', 'joy', 'kid', 'kit', 'lab', 'lap', 'led', 'log', 'mad',
    'mat', 'mid', 'mob', 'mod', 'mom', 'mud', 'mug', 'net', 'nod', 'nut', 'oak',
    'odd', 'ore', 'owe', 'owl', 'pad', 'pan', 'pat', 'pea', 'pen', 'pet', 'pie',
    'pig', 'pin', 'pit', 'pop', 'pot', 'pub', 'rag', 'ram', 'rat', 'ray', 'rib',
    'rim', 'rip', 'rob', 'rod', 'rot', 'rug', 'rum', 'sad', 'sew', 'shy', 'sin',
    'sip', 'ski', 'sky', 'sly', 'sob', 'sow', 'spy', 'sum', 'sun', 'tab', 'tag',
    'tan', 'tap', 'tar', 'tax', 'tea', 'tie', 'tin', 'tip', 'toe', 'ton', 'toy',
    'tub', 'tug', 'vet', 'vow', 'wax', 'web', 'wet', 'wig', 'wit', 'woe', 'yam',
    'yap', 'zap', 'zen', 'zip', 'zoo',
    'able', 'also', 'area', 'away', 'back', 'been', 'best', 'body', 'book', 'both',
    'call', 'came', 'case', 'city', 'come', 'does', 'done', 'down', 'each', 'even',
    'face', 'fact', 'feel', 'find', 'form', 'from', 'full', 'gave', 'give', 'goes',
    'gone', 'good', 'half', 'hand', 'hard', 'have', 'head', 'help', 'here', 'high',
    'hold', 'home', 'hope', 'idea', 'into', 'just', 'keep', 'kind', 'knew', 'know',
    'land', 'last', 'late', 'left', 'less', 'life', 'like', 'line', 'live', 'long',
    'look', 'made', 'make', 'many', 'more', 'most', 'much', 'must', 'name', 'need',
    'next', 'only', 'open', 'over', 'part', 'plan', 'play', 'real', 'rest', 'room',
    'said', 'same', 'show', 'side', 'some', 'such', 'sure', 'take', 'tell', 'than',
    'that', 'them', 'then', 'they', 'this', 'time', 'turn', 'upon', 'very', 'want',
    'week', 'well', 'went', 'were', 'what', 'when', 'will', 'with', 'word', 'work',
    'year', 'your', 'free', 'true', 'role', 'rule', 'rate', 'rise', 'risk', 'road',
    'safe', 'sale', 'save', 'seek', 'seem', 'self', 'sell', 'send', 'sign', 'sing',
    'site', 'size', 'soft', 'soil', 'sort', 'soul', 'step', 'stop', 'tend', 'term',
    'test', 'text', 'thus', 'tiny', 'tone', 'tool', 'tree', 'trip', 'type', 'unit',
    'vast', 'vote', 'wage', 'wait', 'wake', 'walk', 'wall', 'warn', 'wash', 'wave',
    'wear', 'wide', 'wild', 'wind', 'wine', 'wire', 'wise', 'wish', 'wood', 'yard',
    'zero', 'zone', 'four', 'five', 'once', 'seen', 'took', 'went', 'told', 'used',
    'about', 'after', 'again', 'being', 'below', 'could', 'every', 'first', 'found',
    'given', 'going', 'great', 'group', 'house', 'human', 'large', 'later', 'least',
    'level', 'light', 'might', 'money', 'never', 'night', 'often', 'order', 'other',
    'place', 'plant', 'point', 'power', 'quite', 'right', 'shall', 'since', 'small',
    'south', 'space', 'stand', 'start', 'state', 'still', 'story', 'study', 'their',
    'there', 'these', 'thing', 'think', 'those', 'three', 'today', 'total', 'under',
    'until', 'upper', 'using', 'value', 'water', 'where', 'which', 'while', 'whole',
    'world', 'would', 'write', 'young', 'allow', 'apply', 'avoid', 'based', 'basic',
    'begin', 'bring', 'build', 'carry', 'catch', 'cause', 'check', 'child', 'civil',
    'claim', 'class', 'clear', 'close', 'court', 'cover', 'cross', 'death', 'drive',
    'eight', 'enter', 'equal', 'event', 'exist', 'extra', 'faith', 'field', 'fight',
    'final', 'force', 'front', 'green', 'guess', 'happy', 'heart', 'heavy', 'image',
    'issue', 'judge', 'known', 'labor', 'learn', 'legal', 'limit', 'local', 'logic',
    'major', 'match', 'maybe', 'media', 'metal', 'minor', 'moral', 'motor', 'mouth',
    'movie', 'music', 'occur', 'offer', 'organ', 'owner', 'panel', 'paper', 'party',
    'peace', 'phone', 'photo', 'piece', 'press', 'price', 'prime', 'prior', 'prove',
    'quick', 'radio', 'raise', 'range', 'reach', 'ready', 'refer', 'round', 'rural',
    'scene', 'sense', 'serve', 'seven', 'shape', 'share', 'sharp', 'shoot', 'short',
    'sight', 'sleep', 'smile', 'solid', 'solve', 'speak', 'speed', 'spend', 'sport',
    'staff', 'stage', 'stock', 'store', 'style', 'sugar', 'super', 'sweet', 'table',
    'teach', 'thank', 'theme', 'tired', 'title', 'touch', 'tough', 'track', 'trade',
    'train', 'treat', 'trend', 'trial', 'truck', 'truly', 'trust', 'truth', 'twice',
    'union', 'usual', 'video', 'visit', 'vital', 'voice', 'waste', 'watch', 'white',
    'wrong', 'youth', 'north', 'along', 'moved', 'taken',
}

# General pattern: two lowercase English fragments separated by space(s)
GENERIC_BROKEN_PATTERN = re.compile(r'(?<![a-zA-Z])([a-zA-Z]{2,})\s+([a-zA-Z]{2,})(?![a-zA-Z])')

def check_generic_broken_word(text):
    """Find cases where two fragments separated by space form a known word."""
    issues = []
    for m in GENERIC_BROKEN_PATTERN.finditer(text):
        frag1 = m.group(1)
        frag2 = m.group(2)
        combined = (frag1 + frag2).lower()

        # Check if combined word is in our known words set
        if combined in KNOWN_WORDS:
            # Make sure neither fragment is a complete common word on its own
            # (to avoid "soft ware" being flagged when "soft" and "ware" are standalone)
            f1_lower = frag1.lower()
            f2_lower = frag2.lower()

            # Both fragments being common words is suspicious if combined is also a known word
            # We flag it anyway since the OCR context matters
            # But skip very common 2-word phrases
            if f1_lower in COMMON_SHORT_WORDS and f2_lower in COMMON_SHORT_WORDS:
                # Only flag if combined is DEFINITELY a single word (not a phrase)
                if combined in {"into", "onto", "upon", "another", "together", "within",
                                "without", "throughout", "between", "however", "therefore",
                                "although", "because", "whether"}:
                    continue  # These naturally appear as two words too, skip

            issues.append({
                "type": "broken_word",
                "matched_text": m.group(),
                "reconstructed": combined,
                "position": m.start(),
                "context": text[max(0, m.start()-20):m.end()+20]
            })
    return issues


# ============================================================
# 2. MISSING SPACES (words concatenated)
# ============================================================

# Pattern for English words concatenated without spaces
# Focus on patterns that are clearly OCR errors
MISSING_SPACE_PATTERNS = []

# Preposition/article concatenated: "ofthe", "tothe", "inthe", "forthe", etc.
PREP_ARTICLE_CONCAT = re.compile(
    r'(?<![a-zA-Z])(of|in|to|for|and|on|at|by|from|with|the|than|or|but|as|if|so|no|not|nor|yet|per|via)'
    r'(the|a|an|this|that|these|those|their|them|they|his|her|its|our|your|my|which|what|who|whom|some|any|'
    r'all|each|every|most|many|much|more|such|same|other|both|few|one|two|no|not|its|she|he|we|you|it|will|'
    r'can|may|must|has|had|was|were|are|been|being|have|having|do|does|did|done|get|got|make|made|take|took|'
    r'come|came|give|gave|keep|kept|let|say|said|see|saw|go|went|know|knew|find|put|think|tell|become|show|'
    r'leave|feel|bring|begin|seem|help|turn|start|might|would|could|should|need|want|try|ask|use|work|call|'
    r'please|also|still|just|then|now|here|there|when|how|why|where|while|until|after|before|since|between|'
    r'under|over|through|during|above|below|along|across|around|behind|beside|against|among|within|without|'
    r'include|including|according)(?=[a-zA-Z])',
    re.IGNORECASE
)

# Words concatenated after punctuation: ".The", ",the", ".A"
PUNCT_NO_SPACE = re.compile(r'(?<=[a-zA-Z])[.,;:!?]([A-Z][a-z]+)')

# CamelCase-like concatenation in English text: "NewYork", "toSeoul"
# Only flag when in clearly English context
CAMEL_CONCAT = re.compile(r'(?<=[a-z])([A-Z][a-z]{2,})')

# Word concatenated without space: "giveme", "proceedto", "Internetscam"
# Generic pattern: look for strings of lowercase letters that don't form a valid word
# We'll use a different approach - look for known concatenated patterns
KNOWN_CONCAT_PATTERNS = [
    (re.compile(r'giveme\b', re.IGNORECASE), "giveme -> give me"),
    (re.compile(r'\bproceedto\b', re.IGNORECASE), "proceedto -> proceed to"),
    (re.compile(r'\bInternetscam\b', re.IGNORECASE), "Internetscam -> Internet scam"),
    (re.compile(r'\bconveyorbelt\b', re.IGNORECASE), "conveyorbelt -> conveyor belt"),
    (re.compile(r'\balonein\b', re.IGNORECASE), "alonein -> alone in"),
    (re.compile(r'\bofcyber', re.IGNORECASE), "ofcyber -> of cyber"),
    (re.compile(r'\bacharge\b', re.IGNORECASE), "acharge -> a charge"),
    (re.compile(r'\bsinexces', re.IGNORECASE), "sinexces -> s in exces"),
    (re.compile(r'\bsentencesinexcess', re.IGNORECASE), "sentencesinexcess -> sentences in excess"),
    (re.compile(r'\bexcessof', re.IGNORECASE), "excessof -> excess of"),
    (re.compile(r'\bhefai\b', re.IGNORECASE), "hefai -> he fai(led)"),
    (re.compile(r'\bmakeit\b', re.IGNORECASE), "makeit -> make it"),
]


# ============================================================
# 3. GARBLED/BROKEN CHARACTERS
# ============================================================

GARBLED_PATTERNS = [
    # Replacement character
    (re.compile(r'\ufffd'), "replacement_character"),

    # Null bytes
    (re.compile(r'\x00'), "null_byte"),

    # Control characters (except \n, \r, \t)
    (re.compile(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]'), "control_character"),

    # Private Use Area characters (strong indicator of encoding issues)
    (re.compile(r'[\ue000-\uf8ff]'), "private_use_area_char"),

    # HTML entities that weren't decoded
    (re.compile(r'&(?:amp|lt|gt|quot|nbsp|apos|#\d+|#x[0-9a-fA-F]+);'), "unescaped_html_entity"),

    # CID references (from PDF extraction failures)
    (re.compile(r'\(cid:\d+\)'), "cid_reference"),

    # Mojibake patterns
    (re.compile('[\u00c0-\u00c3][\u0080-\u00bf]'), "mojibake_utf8_as_latin1"),
]

# ============================================================
# 4. Multiple spaces within English text
# ============================================================
MULTI_SPACE_IN_ENGLISH = re.compile(r'([a-zA-Z])\s{2,}([a-zA-Z])')


def extract_text_fields(question):
    """Extract all text fields from a question for scanning."""
    fields = []

    stem = question.get("stem", "")
    if stem:
        fields.append(("stem", stem))

    options = question.get("options", {})
    if isinstance(options, dict):
        for key, value in sorted(options.items()):
            if value:
                fields.append((f"option_{key}", str(value)))

    return fields


def scan_text_for_issues(text, field_name):
    """Scan a text string for OCR artifacts. Returns list of issues."""
    issues = []
    seen_positions = set()  # Avoid duplicate reports at same position

    # 1. Check specific OCR word breaks
    for pattern, description in SPECIFIC_OCR_BREAKS:
        for match in pattern.finditer(text):
            pos_key = (match.start(), match.end())
            if pos_key not in seen_positions:
                seen_positions.add(pos_key)
                issues.append({
                    "type": "broken_word",
                    "field": field_name,
                    "matched_text": match.group(),
                    "description": description,
                    "position": match.start(),
                    "context": text[max(0, match.start()-30):match.end()+30]
                })

    # 2. Generic broken word detection
    for item in check_generic_broken_word(text):
        pos_key = (item["position"], item["position"] + len(item["matched_text"]))
        # Check if this overlaps with any already-found specific issue
        dominated = False
        for sp in seen_positions:
            if item["position"] >= sp[0] and item["position"] + len(item["matched_text"]) <= sp[1]:
                dominated = True
                break
        if not dominated:
            seen_positions.add(pos_key)
            item["field"] = field_name
            issues.append(item)

    # 3. Missing spaces: preposition/article concatenation
    for match in PREP_ARTICLE_CONCAT.finditer(text):
        full_match_start = match.start()
        # Get the full concatenated string
        # The match only captures the preposition - we need to see what follows
        remaining = text[match.end():]
        word_after = re.match(r'[a-zA-Z]+', remaining)
        if word_after:
            full_text = match.group() + word_after.group()
            # Check if the full thing is NOT itself a valid English word
            if full_text.lower() not in COMMON_SHORT_WORDS and full_text.lower() not in KNOWN_WORDS:
                # But the prep + remaining should form valid words separately
                prep = match.group(1)
                rest = match.group(2)
                if word_after:
                    rest = rest + word_after.group()[:20]  # limit
                issues.append({
                    "type": "missing_space",
                    "subtype": "concatenated_words",
                    "field": field_name,
                    "matched_text": text[match.start():match.end() + (word_after.end() if word_after else 0)],
                    "description": f"'{prep}' concatenated with '{rest}'",
                    "position": match.start(),
                    "context": text[max(0, match.start()-20):match.end() + 30]
                })

    # 4. Missing space after punctuation in English context
    for match in PUNCT_NO_SPACE.finditer(text):
        pos = match.start()
        # Only flag in English context
        if is_english_context(text, pos):
            # Skip abbreviations like "Mr.", "Dr.", "U.S."
            before = text[max(0, pos-5):pos+1]
            if re.search(r'\b(?:Mr|Mrs|Ms|Dr|Jr|Sr|St|vs|etc|Inc|Ltd|Corp|dept|govt)\.$', before, re.IGNORECASE):
                continue
            if re.search(r'[A-Z]\.[A-Z]', before):
                continue
            issues.append({
                "type": "missing_space",
                "subtype": "after_punctuation",
                "field": field_name,
                "matched_text": text[pos:match.end()],
                "position": pos,
                "context": text[max(0, pos-20):match.end()+20]
            })

    # 5. CamelCase concatenation in English context
    for match in CAMEL_CONCAT.finditer(text):
        pos = match.start()
        if is_english_context(text, pos):
            # Get the full word before
            word_before_match = re.search(r'([a-z]+)$', text[:pos+1])
            if word_before_match:
                full_before = word_before_match.group(1)
                full_after = match.group(1)
                combined = full_before + full_after
                # Skip known compound words and proper nouns
                if combined.lower() in {'youtube', 'facebook', 'iphone', 'ipad', 'github',
                                         'linkedin', 'javascript', 'typescript', 'newyork',
                                         'mcdonald', 'macbook', 'powerpoint', 'wordpress'}:
                    continue
                # Skip if 'before' is just a single char like variable names
                if len(full_before) < 2:
                    continue
                # Skip things like "kHz", "MHz" (units)
                if re.match(r'^[kMGTn]?[A-Z][a-z]*$', combined):
                    continue
                issues.append({
                    "type": "missing_space",
                    "subtype": "camelcase_concatenation",
                    "field": field_name,
                    "matched_text": full_before + full_after,
                    "description": f"'{full_before}' + '{full_after}' concatenated",
                    "position": word_before_match.start(),
                    "context": text[max(0, word_before_match.start()-15):match.end()+15]
                })

    # 6. Known concatenation patterns
    for pattern, description in KNOWN_CONCAT_PATTERNS:
        for match in pattern.finditer(text):
            issues.append({
                "type": "missing_space",
                "subtype": "known_concatenation",
                "field": field_name,
                "matched_text": match.group(),
                "description": description,
                "position": match.start(),
                "context": text[max(0, match.start()-20):match.end()+20]
            })

    # 7. Garbled/encoding issues
    for pattern, gtype in GARBLED_PATTERNS:
        for match in pattern.finditer(text):
            matched = match.group()
            issues.append({
                "type": "encoding_issue",
                "subtype": gtype,
                "field": field_name,
                "matched_text": repr(matched) if gtype != "cid_reference" else matched,
                "char_code": f"U+{ord(matched[0]):04X}" if len(matched) >= 1 and gtype != "cid_reference" else "",
                "position": match.start(),
                "context": text[max(0, match.start()-20):match.end()+20]
            })

    # 8. Multiple spaces within English text
    for match in MULTI_SPACE_IN_ENGLISH.finditer(text):
        if is_english_context(text, match.start()):
            issues.append({
                "type": "extra_whitespace",
                "field": field_name,
                "matched_text": match.group(),
                "position": match.start(),
                "context": text[max(0, match.start()-30):match.end()+30]
            })

    return issues


def scan_file(filepath):
    """Scan a single JSON file for OCR issues."""
    file_issues = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [{"type": "json_parse_error", "error": str(e)}]
    except Exception as e:
        return [{"type": "file_read_error", "error": str(e)}]

    questions = data.get("questions", [])
    if not isinstance(questions, list):
        return []

    for question in questions:
        if not isinstance(question, dict):
            continue

        q_num = question.get("number", "?")
        q_type = question.get("type", "unknown")

        fields = extract_text_fields(question)

        for field_name, text in fields:
            issues = scan_text_for_issues(text, field_name)
            for issue in issues:
                issue["question_number"] = q_num
                issue["question_type"] = q_type
                file_issues.append(issue)

    return file_issues


def deduplicate_issues(issues):
    """Remove duplicate issues (same type, same position, same text)."""
    seen = set()
    unique = []
    for issue in issues:
        key = (issue.get("type"), issue.get("field"), issue.get("position"), issue.get("matched_text"))
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique


def main():
    print("Starting OCR artifact scan...", file=sys.stderr)

    # Collect all exam JSON files
    exam_files = []
    for root, dirs, files in os.walk(BASE_DIR):
        for fname in files:
            if fname.endswith('.json'):
                fpath = os.path.join(root, fname)
                # Skip top-level metadata files
                if os.path.dirname(fpath) == str(BASE_DIR):
                    continue
                exam_files.append(fpath)

    exam_files.sort()
    print(f"Found {len(exam_files)} exam files to scan.", file=sys.stderr)

    all_results = []
    files_with_issues = 0
    total_issues = 0

    for i, fpath in enumerate(exam_files):
        if (i + 1) % 100 == 0:
            print(f"  Scanning file {i+1}/{len(exam_files)}...", file=sys.stderr)

        rel_path = os.path.relpath(fpath, "/home/user/police-exam-archive")
        issues = scan_file(fpath)
        issues = deduplicate_issues(issues)

        if issues:
            files_with_issues += 1
            total_issues += len(issues)
            all_results.append({
                "file": fpath,
                "relative_path": rel_path,
                "issue_count": len(issues),
                "issues": issues
            })

    # Build summary
    report = {
        "scan_summary": {
            "total_files_scanned": len(exam_files),
            "files_with_issues": files_with_issues,
            "total_issues_found": total_issues,
            "issue_type_breakdown": {}
        },
        "files_with_issues": all_results
    }

    # Count by type
    type_counts = defaultdict(int)
    subtype_counts = defaultdict(int)
    for result in all_results:
        for issue in result["issues"]:
            itype = issue["type"]
            subtype = issue.get("subtype", "")
            type_counts[itype] += 1
            if subtype:
                subtype_counts[f"{itype}/{subtype}"] += 1

    report["scan_summary"]["issue_type_breakdown"] = dict(sorted(type_counts.items(), key=lambda x: -x[1]))
    report["scan_summary"]["issue_subtype_breakdown"] = dict(sorted(subtype_counts.items(), key=lambda x: -x[1]))

    # Write output
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\nScan complete!", file=sys.stderr)
    print(f"  Files scanned: {len(exam_files)}", file=sys.stderr)
    print(f"  Files with issues: {files_with_issues}", file=sys.stderr)
    print(f"  Total issues found: {total_issues}", file=sys.stderr)
    print(f"  Report written to: {OUTPUT_FILE}", file=sys.stderr)

    # Print summary to stdout
    print(json.dumps(report["scan_summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
