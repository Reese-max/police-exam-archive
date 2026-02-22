#!/usr/bin/env python3
"""
Comprehensive OCR artifact scanner for police exam JSON files.
Scans all exam files for:
1. English words broken by spaces (e.g. "off icer", "in vesti gate")
2. Missing spaces between words (e.g. "giveme", "ofthe", "toSeoul")
3. Broken/garbled characters or encoding issues (CID references, private use chars)

Refined v3: Minimizes false positives with careful filtering.
"""

import json
import os
import re
import sys
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path("/home/user/police-exam-archive/考古題庫")
OUTPUT_FILE = Path("/home/user/police-exam-archive/agent1_ocr_report.json")

# ============================================================
# Helper
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
# COMMON ENGLISH WORDS (to filter false positives)
# ============================================================
# Words starting with common prepositions that are NOT concatenation errors
# e.g. "information" starts with "in" but is a single word
VALID_ENGLISH_WORDS = set()

# Load a comprehensive set - words that start with preposition-like prefixes
# but are legitimate single words
PREFIX_WORDS = {
    # in- words
    "inability", "inaccurate", "inaccuracy", "inactive", "inadequate", "inappropriate",
    "inaugural", "incapable", "incarcerate", "incarceration", "incentive", "inception",
    "incident", "incidental", "incidentally", "incite", "inclination", "incline", "include",
    "included", "includes", "including", "inclusive", "income", "incoming", "incompatible",
    "incomplete", "inconsistent", "inconvenience", "incorporate", "incorporated", "incorrect",
    "increase", "increased", "increasing", "increasingly", "incredible", "incredibly",
    "incumbent", "incur", "indebted", "indeed", "indefinite", "indefinitely", "independence",
    "independent", "independently", "index", "indicate", "indicated", "indicates", "indicating",
    "indication", "indicator", "indicators", "indict", "indicted", "indictment", "indigenous",
    "indirect", "indirectly", "individual", "individually", "individuals", "indoor", "indoors",
    "induce", "induced", "induction", "indulge", "industrial", "industrialized", "industry",
    "industries", "ineffective", "inefficiency", "inefficient", "inequality", "inevitable",
    "inevitably", "infamous", "infant", "infantry", "infect", "infected", "infection",
    "infectious", "infer", "inference", "inferior", "infinite", "infinitely", "infinity",
    "inflation", "inflict", "influence", "influenced", "influences", "influential", "influx",
    "inform", "informal", "informally", "information", "informative", "informed", "informer",
    "informing", "infrastructure", "infrequent", "infringe", "infringement", "ingenious",
    "ingredient", "ingredients", "inhabit", "inhabitant", "inhabitants", "inherent",
    "inherently", "inherit", "inherited", "inhibit", "inhibited", "inhibition", "initial",
    "initially", "initiate", "initiated", "initiating", "initiative", "inject", "injected",
    "injection", "injure", "injured", "injuries", "injury", "injustice", "inland", "inmate",
    "inmates", "inn", "innate", "inner", "innocence", "innocent", "innocently", "innovation",
    "innovative", "innumerable", "inoculate", "inoculated", "inorganic", "input", "inquire",
    "inquiry", "insane", "insanity", "inscribe", "inscription", "insect", "insecure",
    "insecurity", "insert", "inserted", "insertion", "inside", "insider", "insight",
    "insightful", "insignificant", "insist", "insisted", "insistence", "insistent", "inspect",
    "inspection", "inspector", "inspiration", "inspire", "inspired", "inspiring", "install",
    "installation", "installed", "installment", "instance", "instances", "instant",
    "instantaneous", "instantly", "instead", "instinct", "instinctive", "instinctively",
    "institute", "instituted", "institution", "institutional", "institutionalize", "instruct",
    "instruction", "instructions", "instructor", "instrument", "instrumental", "instruments",
    "insufficient", "insult", "insulting", "insurance", "insure", "insured", "insurgent",
    "intact", "intake", "integral", "integrate", "integrated", "integration", "integrity",
    "intellect", "intellectual", "intelligence", "intelligent", "intend", "intended",
    "intense", "intensely", "intensify", "intensity", "intensive", "intent", "intention",
    "intentional", "intentionally", "interact", "interaction", "interactive", "intercept",
    "interchange", "interconnected", "intercourse", "interest", "interested", "interesting",
    "interests", "interfere", "interference", "interim", "interior", "intermediate",
    "internal", "internally", "international", "internationally", "internet", "interpret",
    "interpretation", "interpreter", "interrogate", "interrogation", "interrupt", "interruption",
    "intersection", "interval", "intervene", "intervention", "interview", "interviewed",
    "interviewer", "interviewing", "interviews", "intimate", "intimately", "intimidate",
    "intimidation", "into", "intoxicate", "intoxicated", "intoxication", "intricate",
    "intrigue", "intriguing", "intrinsic", "introduce", "introduced", "introducing",
    "introduction", "introductory", "intrude", "intruder", "intrusion", "intuition",
    "intuitive", "invade", "invader", "invasion", "invent", "invented", "invention",
    "inventor", "inventory", "invest", "invested", "investigate", "investigated",
    "investigating", "investigation", "investigative", "investigator", "investigators",
    "investment", "investor", "investors", "invisible", "invitation", "invite", "invited",
    "involve", "involved", "involvement", "involves", "involving", "inward", "inwards",
    # to- words
    "today", "together", "token", "told", "tolerance", "tolerant", "tolerate", "toll",
    "tomorrow", "tone", "tongue", "tonight", "tool", "tools", "tooth", "top", "topic",
    "topics", "torch", "torn", "tornado", "torture", "tortured", "total", "totally",
    "touch", "touched", "touching", "tough", "tour", "tourism", "tourist", "tournament",
    "toward", "towards", "tower", "town", "toxic", "toy", "toys",
    # for- words
    "forbid", "forbidden", "force", "forced", "forces", "forceful", "forecast", "forehead",
    "foreign", "foreigner", "foreigners", "forest", "forestry", "forever", "forfeit",
    "forge", "forged", "forget", "forgive", "forgiveness", "forgotten", "fork", "form",
    "formal", "formally", "format", "formation", "former", "formerly", "formula",
    "formulate", "formulated", "formulation", "fort", "forth", "forthcoming", "fortune",
    "fortunate", "fortunately", "forty", "forum", "forward", "fossil", "foster",
    "fostered", "found", "foundation", "founded", "founder", "fountain", "four", "fourteen",
    "fourth", "fox",
    # or- words
    "oracle", "oral", "orally", "orange", "orbit", "orchard", "orchestra", "ordeal",
    "order", "ordered", "orderly", "orders", "ordinance", "ordinarily", "ordinary",
    "organ", "organic", "organism", "organization", "organizational", "organize",
    "organized", "orientation", "origin", "original", "originally", "originate",
    "originated", "ornament", "orphan", "orthodox",
    # the- words
    "theater", "theatre", "theatrical", "theft", "theme", "themselves", "then", "thence",
    "theology", "theoretical", "theoretically", "theory", "therapist", "therapy", "there",
    "thereafter", "thereby", "therefore", "thermal", "thermometer", "thereof", "these",
    "thesis", "they",
    # and- words (none common)
    # with- words
    "withdraw", "withdrawal", "withdrawn", "wither", "withhold", "within", "without",
    "withstand",
    # on- words
    "once", "ongoing", "online", "only", "onset", "onto",
    # by- words
    "bypass", "byproduct", "bystander",
    # as- words
    "ascend", "ascent", "aside", "aspire", "assault", "assemble", "assembly", "assert",
    "assertion", "assess", "assessed", "assessing", "assessment", "asset", "assets",
    "assign", "assigned", "assignment", "assist", "assistance", "assistant", "associate",
    "associated", "association", "assume", "assumed", "assuming", "assumption", "assurance",
    "assure", "assured",
    # at- words
    "athlete", "athletic", "atmosphere", "atom", "atomic", "atrocity", "attach",
    "attached", "attachment", "attack", "attacked", "attacker", "attain", "attained",
    "attempt", "attempted", "attempting", "attend", "attendance", "attendant", "attended",
    "attending", "attention", "attic", "attitude", "attorney", "attract", "attracted",
    "attraction", "attractive", "attribute", "attributed",
    # no/not- words
    "noble", "nobody", "nod", "noise", "nominal", "nominate", "nominated", "nomination",
    "none", "nonetheless", "nonsense", "noodle", "noon", "norm", "normal", "normally",
    "north", "northern", "nose", "notably", "notation", "note", "noted", "notes",
    "nothing", "notice", "noticed", "notification", "notify", "notion", "notorious",
    "noun", "novel", "novelty", "november", "novice", "now", "nowadays", "nowhere",
    # per- words
    "perceive", "perceived", "percent", "percentage", "perception", "perfect", "perfectly",
    "perform", "performance", "performed", "performer", "performing", "perfume", "perhaps",
    "peril", "perilous", "period", "periodic", "periodically", "peripheral", "permanent",
    "permanently", "permission", "permit", "permitted", "perpetual", "perpetuate",
    "persecute", "persecution", "persist", "persistent", "person", "personal", "personality",
    "personally", "personnel", "persons", "perspective", "persuade", "persuasion",
    "persuasive", "pertain", "pertaining", "pertinent", "pervade", "pervasive",
    # so- words
    "soak", "soap", "soar", "sob", "sober", "soccer", "social", "socially", "society",
    "sociology", "socket", "sodium", "sofa", "soft", "soften", "software", "soil",
    "solar", "soldier", "sole", "solely", "solemn", "solicitor", "solid", "solidarity",
    "solitary", "solo", "solution", "solve", "solved", "solving", "some", "somebody",
    "someday", "somehow", "someone", "something", "sometimes", "somewhat", "somewhere",
    "son", "song", "soon", "sophisticated", "sorry", "sort", "soul", "sound", "source",
    "sources", "south", "southeast", "southern", "southwest", "sovereign", "sovereignty",
    # but- words
    "butter", "butterfly", "button", "butcher",
    # sub- words
    "subcommittee", "subconscious", "subdivide", "subdivision", "subject", "subjected",
    "subjective", "submission", "submit", "submitted", "subordinate", "subscribe",
    "subscription", "subsequent", "subsequently", "substance", "substances", "substantial",
    "substantially", "substantiate", "substitute", "substitution", "subtle", "subtlety",
    "subtract", "suburb", "suburban", "succeed", "succeeded", "succeeding", "success",
    "successful", "successfully", "successive", "successor", "succumb", "such", "sudden",
    "suddenly", "sue", "sued", "suffer", "suffered", "suffering", "sufficient",
    "sufficiently", "sugar", "suggest", "suggested", "suggesting", "suggestion",
    "suggestions", "suicide", "suit", "suitable", "suite", "sum", "summary", "summer",
    "summit", "summon", "sun", "sunlight", "sunshine", "super", "superb", "superficial",
    "superintendent", "superior", "supervise", "supervised", "supervision", "supervisor",
    "supper", "supplement", "supplementary", "supplier", "supply", "support", "supported",
    "supporter", "supporting", "suppose", "supposed", "supposedly", "suppress", "suppression",
    "supreme", "sure", "surely", "surface", "surge", "surgeon", "surgery", "surplus",
    "surprise", "surprised", "surprising", "surprisingly", "surrender", "surround",
    "surrounded", "surrounding", "surroundings", "surveillance", "survey", "surveyed",
    "survival", "survive", "survived", "survivor", "suspect", "suspected", "suspects",
    "suspend", "suspended", "suspense", "suspension", "suspicion", "suspicious", "sustain",
    "sustainable", "sustained", "swallow", "swamp", "swap", "swear", "sweat", "sweep",
    "sweet", "swell", "swept", "swift", "swim", "swimming", "swing", "switch", "swollen",
    "sword", "swore", "sworn", "symbol", "symbolic", "symbolize", "sympathetic", "sympathy",
    "symptom", "syndrome", "syntax", "synthesis", "synthetic", "system", "systematic",
    "systematically", "systems",
    # via- words
    "viable", "vibrant", "vice", "vicinity", "victim", "victimize", "victims", "victory",
    "video",
    # from- words (none that start with "from" besides itself)
}

# ============================================================
# 1. BROKEN ENGLISH WORDS (spaces inserted mid-word by OCR)
# ============================================================

# Specific known OCR word-break patterns
# ALL patterns REQUIRE at least one \s+ (mandatory space)
SPECIFIC_OCR_BREAKS = [
    (re.compile(r'\b[Oo]ff\s+icer', re.IGNORECASE), "off icer -> officer"),
    (re.compile(r'\b[Pp]ol\s+ice\b'), "pol ice -> police"),
    (re.compile(r'\bin\s+vesti\s*gat', re.IGNORECASE), "in vestigat -> investigat"),
    (re.compile(r'\binvesti\s+gat', re.IGNORECASE), "investi gat -> investigat"),
    (re.compile(r'\bcon\s+stitu', re.IGNORECASE), "con stitu -> constitu"),
    (re.compile(r'\bgov\s+ern', re.IGNORECASE), "gov ern -> govern"),
    (re.compile(r'\bad\s+minis', re.IGNORECASE), "ad minis -> adminis"),
    (re.compile(r'\ben\s+force\b', re.IGNORECASE), "en force -> enforce"),
    (re.compile(r'\bde\s+part\s*ment', re.IGNORECASE), "de part ment -> department"),
    (re.compile(r'\bcom\s+mun', re.IGNORECASE), "com mun -> commun"),
    (re.compile(r'\bpro\s+tect', re.IGNORECASE), "pro tect -> protect"),
    (re.compile(r'\bpre\s+vent', re.IGNORECASE), "pre vent -> prevent"),
    (re.compile(r'\bre\s+spons', re.IGNORECASE), "re spons -> respons"),
    (re.compile(r'\bre\s+port\b', re.IGNORECASE), "re port -> report"),
    (re.compile(r'\bsur\s+veil', re.IGNORECASE), "sur veil -> surveil"),
    (re.compile(r'\bcrim\s+inal', re.IGNORECASE), "crim inal -> criminal"),
    (re.compile(r'\bjur\s+is\s*dic', re.IGNORECASE), "jur isdic -> jurisdic"),
    (re.compile(r'\bpun\s+ish', re.IGNORECASE), "pun ish -> punish"),
    (re.compile(r'\bwar\s+rant', re.IGNORECASE), "war rant -> warrant"),
    (re.compile(r'\bsus\s+pect', re.IGNORECASE), "sus pect -> suspect"),
    (re.compile(r'\bar\s+rest\b', re.IGNORECASE), "ar rest -> arrest"),
    (re.compile(r'\bevi\s+dence', re.IGNORECASE), "evi dence -> evidence"),
    (re.compile(r'\bwit\s+ness', re.IGNORECASE), "wit ness -> witness"),
    (re.compile(r'\bpros\s+ecu', re.IGNORECASE), "pros ecu -> prosecu"),
    (re.compile(r'\bde\s+fend', re.IGNORECASE), "de fend -> defend"),
    (re.compile(r'\bse\s+cur', re.IGNORECASE), "se cur -> secur"),
    (re.compile(r'\bau\s+thor', re.IGNORECASE), "au thor -> author"),
    (re.compile(r'\breg\s+ulat', re.IGNORECASE), "reg ulat -> regulat"),
    (re.compile(r'\bviol\s+at', re.IGNORECASE), "viol at -> violat"),
    (re.compile(r'\bleg\s+is', re.IGNORECASE), "leg is -> legis"),
    (re.compile(r'\bcer\s+tif', re.IGNORECASE), "cer tif -> certif"),
    (re.compile(r'\bemer\s+gen', re.IGNORECASE), "emer gen -> emergen"),
    (re.compile(r'\bfor\s+eign', re.IGNORECASE), "for eign -> foreign"),
    (re.compile(r'\bterr\s+or', re.IGNORECASE), "terr or -> terror"),
    (re.compile(r'\bsmug\s+gl', re.IGNORECASE), "smug gl -> smuggl"),
    (re.compile(r'\bimm\s+igr', re.IGNORECASE), "imm igr -> immigr"),
    (re.compile(r'\bpass\s+port', re.IGNORECASE), "pass port -> passport"),
    (re.compile(r'\bcust\s+oms', re.IGNORECASE), "cust oms -> customs"),
    (re.compile(r'\btech\s+nol', re.IGNORECASE), "tech nol -> technol"),
    (re.compile(r'\bdig\s+ital', re.IGNORECASE), "dig ital -> digital"),
    (re.compile(r'\belec\s+tron', re.IGNORECASE), "elec tron -> electron"),
    (re.compile(r'\bdata\s+base', re.IGNORECASE), "data base -> database"),
    (re.compile(r'\bsoft\s+ware', re.IGNORECASE), "soft ware -> software"),
    (re.compile(r'\bhard\s+ware', re.IGNORECASE), "hard ware -> hardware"),
    (re.compile(r'\banal\s+ysis', re.IGNORECASE), "anal ysis -> analysis"),
    (re.compile(r'\bstat\s+istic', re.IGNORECASE), "stat istic -> statistic"),
    (re.compile(r'\bpsy\s+chol', re.IGNORECASE), "psy chol -> psychol"),
    (re.compile(r'\bphil\s+os', re.IGNORECASE), "phil os -> philos"),
    (re.compile(r'\benvi\s+ron', re.IGNORECASE), "envi ron -> environ"),
    (re.compile(r'\bpoll\s+ut', re.IGNORECASE), "poll ut -> pollut"),
    (re.compile(r'\bpop\s+ulat', re.IGNORECASE), "pop ulat -> populat"),
    (re.compile(r'\becon\s+om', re.IGNORECASE), "econ om -> econom"),
    (re.compile(r'\bdem\s+ocr', re.IGNORECASE), "dem ocr -> democr"),
    (re.compile(r'\bpar\s+lia', re.IGNORECASE), "par lia -> parlia"),
    (re.compile(r'\buni\s+vers', re.IGNORECASE), "uni vers -> univers"),
    (re.compile(r'\bres\s+taur', re.IGNORECASE), "res taur -> restaur"),
    (re.compile(r'\bhos\s+pital', re.IGNORECASE), "hos pital -> hospital"),
    (re.compile(r'\bcom\s+preh', re.IGNORECASE), "com preh -> compreh"),
    (re.compile(r'\btrans\s+lat', re.IGNORECASE), "trans lat -> translat"),
    (re.compile(r'\binter\s+view', re.IGNORECASE), "inter view -> interview"),
    (re.compile(r'\bim\s+port\s*ant', re.IGNORECASE), "im portant -> important"),
    (re.compile(r'\bex\s+peri', re.IGNORECASE), "ex peri -> experi"),
    (re.compile(r'\binfo\s+r\s*ma', re.IGNORECASE), "info rma -> informa"),
    (re.compile(r'\binfor\s+ma', re.IGNORECASE), "infor ma -> informa"),
    (re.compile(r'\bcom\s+mit', re.IGNORECASE), "com mit -> commit"),
    (re.compile(r'\bap\s+preh', re.IGNORECASE), "ap preh -> appreh"),
    (re.compile(r'\bsafe\s+guard', re.IGNORECASE), "safe guard -> safeguard"),
    (re.compile(r'\bcount\s+er\s*feit', re.IGNORECASE), "counter feit -> counterfeit"),
    (re.compile(r'\bcy\s+ber', re.IGNORECASE), "cy ber -> cyber"),
    (re.compile(r'\bprob\s+lem', re.IGNORECASE), "prob lem -> problem"),
    (re.compile(r'\bnec\s+ess', re.IGNORECASE), "nec ess -> necess"),
    (re.compile(r'\bposs\s+ib', re.IGNORECASE), "poss ib -> possib"),
    (re.compile(r'\bavail\s+ab', re.IGNORECASE), "avail ab -> availab"),
    (re.compile(r'\beffec\s+tive', re.IGNORECASE), "effec tive -> effective"),
    (re.compile(r'\bsig\s+nif', re.IGNORECASE), "sig nif -> signif"),
    (re.compile(r'\bpart\s+icular', re.IGNORECASE), "part icular -> particular"),
    (re.compile(r'\bestab\s+lish', re.IGNORECASE), "estab lish -> establish"),
    (re.compile(r'\bmaint\s+ain', re.IGNORECASE), "maint ain -> maintain"),
    (re.compile(r'\bprov\s+ide', re.IGNORECASE), "prov ide -> provide"),
    (re.compile(r'\breq\s+uire', re.IGNORECASE), "req uire -> require"),
    (re.compile(r'\bcont\s+inue', re.IGNORECASE), "cont inue -> continue"),
    (re.compile(r'\bident\s+ify', re.IGNORECASE), "ident ify -> identify"),
    (re.compile(r'\brec\s+ogniz', re.IGNORECASE), "rec ogniz -> recogniz"),
    (re.compile(r'\bimple\s+ment', re.IGNORECASE), "imple ment -> implement"),
    (re.compile(r'\bcomm\s+unic', re.IGNORECASE), "comm unic -> communic"),
    (re.compile(r'\brel\s+ation', re.IGNORECASE), "rel ation -> relation"),
    (re.compile(r'\boper\s+ation', re.IGNORECASE), "oper ation -> operation"),
    (re.compile(r'\bperf\s+orm', re.IGNORECASE), "perf orm -> perform"),
    (re.compile(r'\bman\s+age\s*ment', re.IGNORECASE), "man agement -> management"),
    (re.compile(r'\bres\s+ource', re.IGNORECASE), "res ource -> resource"),
    (re.compile(r'\bprog\s+ram', re.IGNORECASE), "prog ram -> program"),
    (re.compile(r'\bstand\s+ard', re.IGNORECASE), "stand ard -> standard"),
    (re.compile(r'\bindiv\s+idual', re.IGNORECASE), "indiv idual -> individual"),
    (re.compile(r'\bpers\s+onn', re.IGNORECASE), "pers onn -> personn"),
    (re.compile(r'\bdomes\s+tic', re.IGNORECASE), "domes tic -> domestic"),
    (re.compile(r'\btraf\s+fic', re.IGNORECASE), "traf fic -> traffic"),
    (re.compile(r'\bacc\s+ident', re.IGNORECASE), "acc ident -> accident"),
    (re.compile(r'\bdan\s+ger', re.IGNORECASE), "dan ger -> danger"),
    (re.compile(r'\bassist\s+ance', re.IGNORECASE), "assist ance -> assistance"),
    (re.compile(r'\bdoc\s+ument', re.IGNORECASE), "doc ument -> document"),
    (re.compile(r'\bveh\s+icle', re.IGNORECASE), "veh icle -> vehicle"),
    (re.compile(r'\bweap\s+on', re.IGNORECASE), "weap on -> weapon"),
    (re.compile(r'\bsub\s+stance', re.IGNORECASE), "sub stance -> substance"),
    (re.compile(r'\balco\s+hol', re.IGNORECASE), "alco hol -> alcohol"),
    (re.compile(r'\bnarc\s+otic', re.IGNORECASE), "narc otic -> narcotic"),
    (re.compile(r'\binter\s+nation', re.IGNORECASE), "inter nation -> internation"),
    (re.compile(r'\bnat\s+ional', re.IGNORECASE), "nat ional -> national"),
    (re.compile(r'\bimmed\s+iate', re.IGNORECASE), "immed iate -> immediate"),
    (re.compile(r'\borig\s+inal', re.IGNORECASE), "orig inal -> original"),
    (re.compile(r'\baddit\s+ion', re.IGNORECASE), "addit ion -> addition"),
    (re.compile(r'\bsep\s+arat', re.IGNORECASE), "sep arat -> separat"),
    (re.compile(r'\bamend\s+ment', re.IGNORECASE), "amend ment -> amendment"),
    (re.compile(r'\bprov\s+ision', re.IGNORECASE), "prov ision -> provision"),
    (re.compile(r'\breas\s+on\s*able', re.IGNORECASE), "reas onable -> reasonable"),
    (re.compile(r'\bprob\s+able', re.IGNORECASE), "prob able -> probable"),
    (re.compile(r'\bac\s+curat', re.IGNORECASE), "ac curat -> accurat"),
    (re.compile(r'\bap\s+par\s*ent', re.IGNORECASE), "ap parent -> apparent"),
    (re.compile(r'\brehab\s+ilit', re.IGNORECASE), "rehab ilit -> rehabilit"),
    (re.compile(r'\bincar\s+cer', re.IGNORECASE), "incar cer -> incarcer"),
    (re.compile(r'\bcorrect\s+ion', re.IGNORECASE), "correct ion -> correction"),
    (re.compile(r'\bprob\s+ation', re.IGNORECASE), "prob ation -> probation"),
    (re.compile(r'\bfor\s+ens', re.IGNORECASE), "for ens -> forens"),
    (re.compile(r'\bintel\s+lig', re.IGNORECASE), "intel lig -> intellig"),
    (re.compile(r'\bdescr\s+ip', re.IGNORECASE), "descr ip -> descrip"),
    (re.compile(r'\bexplan\s+ation', re.IGNORECASE), "explan ation -> explanation"),
    (re.compile(r'\bserge\s+ant', re.IGNORECASE), "serge ant -> sergeant"),
    (re.compile(r'\blieu\s+ten', re.IGNORECASE), "lieu ten -> lieuten"),
    (re.compile(r'\bcapt\s+ain', re.IGNORECASE), "capt ain -> captain"),
    (re.compile(r'\bcorp\s+oral', re.IGNORECASE), "corp oral -> corporal"),
    (re.compile(r'\bsher\s+iff', re.IGNORECASE), "sher iff -> sheriff"),
    (re.compile(r'\bdetect\s+ive', re.IGNORECASE), "detect ive -> detective"),
    (re.compile(r'\bpass\s+enger', re.IGNORECASE), "pass enger -> passenger"),
    (re.compile(r'\bpris\s+on', re.IGNORECASE), "pris on -> prison"),
    (re.compile(r'\bcount\s+ries', re.IGNORECASE), "count ries -> countries"),
    (re.compile(r'\bred\s+ucing', re.IGNORECASE), "red ucing -> reducing"),
    (re.compile(r'\bThom\s+pson', re.IGNORECASE), "Thom pson -> Thompson"),
    (re.compile(r'\bcoord\s+in', re.IGNORECASE), "coord in -> coordin"),
    (re.compile(r'\bterm\s+in\s*at', re.IGNORECASE), "term inat -> terminat"),
    (re.compile(r'\bcollegi\s+ate', re.IGNORECASE), "collegi ate -> collegiate"),
    (re.compile(r'\bfai\s+led', re.IGNORECASE), "fai led -> failed"),
    (re.compile(r'\bman\s+ip\s*ulat', re.IGNORECASE), "man ipulat -> manipulat"),
    (re.compile(r'\blike\s+li\s*hood', re.IGNORECASE), "like lihood -> likelihood"),
    (re.compile(r'\bproject\s+ed', re.IGNORECASE), "project ed -> projected"),
    (re.compile(r'\bcreate\s+d\b', re.IGNORECASE), "create d -> created"),
    (re.compile(r'\bov\s+er\s*look', re.IGNORECASE), "ov erlook -> overlook"),
    (re.compile(r'\bcontrol\s+led', re.IGNORECASE), "control led -> controlled"),
    (re.compile(r'\bReport\s+ing', re.IGNORECASE), "Report ing -> Reporting"),
    (re.compile(r'\bin\s+correct', re.IGNORECASE), "in correct -> incorrect"),
    (re.compile(r'\bcon\s+vey\s*or', re.IGNORECASE), "con veyor -> conveyor"),
    (re.compile(r'\blab\s+orat', re.IGNORECASE), "lab orat -> laborat"),
    (re.compile(r'\bsent\s+ence', re.IGNORECASE), "sent ence -> sentence"),
    (re.compile(r'\belig\s+ib', re.IGNORECASE), "elig ib -> eligib"),
    (re.compile(r'\bac\s+quitt', re.IGNORECASE), "ac quitt -> acquitt"),
    (re.compile(r'\bsimul\s+tan', re.IGNORECASE), "simul tan -> simultan"),
    (re.compile(r'\bexces\s+s\b', re.IGNORECASE), "exces s -> excess"),
    (re.compile(r'\bcoun\s+sel', re.IGNORECASE), "coun sel -> counsel"),
    (re.compile(r'\bneigh\s+bor', re.IGNORECASE), "neigh bor -> neighbor"),
    (re.compile(r'\brecog\s+ni', re.IGNORECASE), "recog ni -> recogni"),
    (re.compile(r'\bbench\s+press', re.IGNORECASE), None),  # this is legitimately two words
]
SPECIFIC_OCR_BREAKS = [(p, d) for p, d in SPECIFIC_OCR_BREAKS if d is not None]

# ============================================================
# Generic broken word: two fragments with space that form a known word
# ============================================================
KNOWN_WORDS = set(w.lower() for w in PREFIX_WORDS)
# Add more from the specific patterns
for word in [
    "officer", "officers", "police", "database", "databases", "software", "hardware",
    "passport", "passports", "network", "networks", "customs", "digital", "analysis",
    "statistics", "statistical", "psychology", "psychological", "philosophy",
    "environment", "environmental", "pollution", "population", "economy", "economic",
    "parliament", "university", "restaurant", "hospital", "comprehension", "translation",
    "passenger", "passengers", "prison", "prisoner", "prisoners", "countries", "country",
    "reducing", "reduced", "coordinated", "terminated", "collegiate", "failed",
    "controlled", "reporting", "incorrect", "conveyor", "laboratory", "sentence",
    "sentenced", "sentences", "eligible", "eligibility", "acquitted", "simultaneous",
    "excess", "counsel", "neighbor", "neighborhood",
    "standard", "standards", "individual", "individuals", "personnel", "domestic",
    "traffic", "accident", "accidents", "danger", "dangerous", "assistance",
    "document", "documents", "documentation", "vehicle", "vehicles", "weapon", "weapons",
    "substance", "alcohol", "narcotic", "narcotics", "international", "national",
    "immediate", "immediately", "original", "originally", "additional", "separate",
    "amendment", "provision", "reasonable", "probable", "accurate", "apparent",
    "rehabilitation", "incarceration", "correction", "probation", "forensic", "forensics",
    "intelligence", "description", "explanation", "sergeant", "lieutenant", "captain",
    "corporal", "sheriff", "detective", "Thompson", "manipulated", "likelihood",
    "projected", "created", "overlooked", "benchmark",
]:
    KNOWN_WORDS.add(word.lower())

# Also keep common short words to avoid flagging "is it" as "isit"
COMMON_SHORT_WORDS = {
    'a', 'i', 'an', 'am', 'as', 'at', 'be', 'by', 'do', 'go', 'he', 'if', 'in',
    'is', 'it', 'me', 'my', 'no', 'of', 'on', 'or', 'so', 'to', 'up', 'us', 'we',
    'ad', 'ah', 'al', 'ed', 'eh', 'el', 'em', 'en', 'er', 'ex', 'ha', 'hi',
    'ho', 'id', 'lo', 'ma', 'oh', 'ok', 'ow', 'ox', 'pa', 're', 'sh',
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
    'arm', 'cup', 'era', 'eve', 'fan', 'fat', 'fee', 'fog', 'fox', 'fur',
    'gap', 'gas', 'hen', 'hip', 'hug', 'ice', 'ink', 'inn', 'ion', 'jam',
    'jar', 'jaw', 'jet', 'joy', 'kid', 'kit', 'lab', 'lap', 'led', 'log', 'mad',
    'mat', 'mid', 'mob', 'mod', 'mom', 'mud', 'mug', 'net', 'nod', 'nut', 'oak',
    'odd', 'ore', 'owe', 'owl', 'pad', 'pan', 'pat', 'pea', 'pen', 'pet', 'pie',
    'pig', 'pin', 'pit', 'pop', 'pot', 'pub', 'rag', 'ram', 'rat', 'ray', 'rib',
    'rim', 'rip', 'rob', 'rod', 'rot', 'rug', 'rum', 'sad', 'sew', 'shy', 'sin',
    'sip', 'ski', 'sky', 'sly', 'sob', 'sow', 'spy', 'sum', 'sun', 'tab', 'tag',
    'tan', 'tap', 'tar', 'tax', 'tea', 'tie', 'tin', 'tip', 'toe', 'ton', 'toy',
    'tub', 'tug', 'vet', 'vow', 'wax', 'web', 'wet', 'wig', 'wit', 'woe', 'yam',
    'zap', 'zen', 'zip', 'zoo',
}

GENERIC_BROKEN_PATTERN = re.compile(r'(?<![a-zA-Z])([a-zA-Z]{2,})\s+([a-zA-Z]{2,})(?![a-zA-Z])')

def check_generic_broken_word(text):
    """Find cases where two fragments separated by space form a broken word.
    Uses a conservative approach: at least one fragment must NOT be a common
    standalone English word, indicating it's likely a fragment of a broken word."""
    issues = []

    if not is_english_context(text, len(text) // 2):
        return issues  # Skip entirely non-English text

    for m in GENERIC_BROKEN_PATTERN.finditer(text):
        frag1 = m.group(1)
        frag2 = m.group(2)
        f1 = frag1.lower()
        f2 = frag2.lower()
        combined = f1 + f2

        # Skip if both fragments are common standalone words
        if f1 in COMMON_SHORT_WORDS and f2 in COMMON_SHORT_WORDS:
            continue
        if f1 in PREFIX_WORDS and f2 in PREFIX_WORDS:
            continue

        # APPROACH 1: Combined word is in our known words set
        if combined in KNOWN_WORDS:
            # Both being common words -> skip (normal phrase)
            if f1 in (COMMON_SHORT_WORDS | PREFIX_WORDS) and f2 in (COMMON_SHORT_WORDS | PREFIX_WORDS):
                continue
            issues.append({
                "type": "broken_word",
                "matched_text": m.group(),
                "reconstructed": combined,
                "position": m.start(),
                "context": text[max(0, m.start()-25):m.end()+25]
            })
            continue

        # APPROACH 2: At least one fragment is NOT a recognizable word
        # This means it's likely a fragment of a broken word
        f1_is_word = f1 in COMMON_SHORT_WORDS or f1 in PREFIX_WORDS
        f2_is_word = f2 in COMMON_SHORT_WORDS or f2 in PREFIX_WORDS

        # Both are words -> definitely a normal phrase, skip
        if f1_is_word and f2_is_word:
            continue

        # Only flag if in English context at this specific position
        if not is_english_context(text, m.start()):
            continue

        # At least one fragment is NOT a word
        # But we need to be careful - some non-word fragments are just proper nouns,
        # abbreviations, or domain-specific terms
        # Only flag if the non-word fragment looks like a word fragment (not a proper noun)
        non_word_frag = f2 if f1_is_word else (f1 if f2_is_word else None)

        if non_word_frag is None:
            # Neither is a word - both are likely fragments
            # Only flag if combined >= 6 chars (to avoid false positives with short fragments)
            if len(combined) >= 6:
                issues.append({
                    "type": "broken_word",
                    "matched_text": m.group(),
                    "reconstructed": combined,
                    "position": m.start(),
                    "context": text[max(0, m.start()-25):m.end()+25]
                })
        else:
            # One is a word, one is not
            # The non-word fragment should look like a word fragment, not a proper noun
            # Check: is the non-word fragment all lowercase? (proper nouns start with uppercase)
            orig_frag = frag2 if f1_is_word else frag1
            if orig_frag[0].isupper() and len(orig_frag) >= 3:
                continue  # Likely a proper noun
            # Is the non-word fragment very short (1-2 chars)?
            if len(non_word_frag) <= 2:
                # Only flag known suffix patterns: "ed", "er", "ly", "al", "nt", "ng"
                if non_word_frag not in {'ed', 'er', 'ly', 'al', 'nt', 'ng', 'rs', 'ts',
                                          'ns', 'es', 'ds', 'le', 'ty', 'ry', 'cy', 'ny',
                                          'ss', 'ks', 'ps', 'gy', 'fy', 'te', 'ce', 'se',
                                          'ge', 'ne', 'de', 're'}:
                    continue
            issues.append({
                "type": "broken_word",
                "matched_text": m.group(),
                "reconstructed": combined,
                "position": m.start(),
                "context": text[max(0, m.start()-25):m.end()+25]
            })

    return issues


# ============================================================
# 2. MISSING SPACES (words concatenated without space)
# ============================================================

# Detect concatenated words in English text
# We look for sequences of English letters that contain telltale signs of concatenation

# Pattern: lowercase/period followed immediately by uppercase in English context
# e.g., "conveyorbelt", "NewYork", ".Jackson", "scale.And"
CONCAT_LOWER_UPPER = re.compile(r'([a-z]\.?)([A-Z][a-z]{2,})')

# Pattern: known preposition/article stuck to next word
# "ofthe", "inthe", "tothe", "forthe", etc.
PREP_CONCAT = re.compile(
    r'(?<![a-zA-Z])(of|in|to|for|and|on|at|by|from|with|the|than|or|but|as|if|so|nor|yet|per|via|into|onto|upon)'
    r'(the|a|an|this|that|these|those|their|them|they|his|her|its|our|your|my|which|what|who|some|any|all|each|'
    r'every|most|many|much|more|such|same|other|both|few|one|two|no|not|she|he|we|you|it|'
    r'will|can|may|must|has|had|was|were|are|been|have|do|does|did|'
    r'please|also|still|just|now|here|there|when|how|why|where|while|until|after|before|since|'
    r'under|over|through|during|above|below|along|across|around|behind|beside|against|among|'
    r'more|less|very|quite|rather|almost|enough|too|so|really|already)(?=[a-z])',
    re.IGNORECASE
)

# Known specific concatenation patterns seen in data
KNOWN_CONCAT_PATTERNS = [
    (re.compile(r'\bgive\s*me\b', re.IGNORECASE), None),  # will check if no space
    (re.compile(r'\bgiveme\b', re.IGNORECASE), "giveme -> give me"),
    (re.compile(r'\bproceedto\b', re.IGNORECASE), "proceedto -> proceed to"),
    (re.compile(r'\bInternetscam\b', re.IGNORECASE), "Internetscam -> Internet scam"),
    (re.compile(r'\bconveyorbelt\b', re.IGNORECASE), "conveyorbelt -> conveyor belt"),
    (re.compile(r'\balonein\b', re.IGNORECASE), "alonein -> alone in"),
    (re.compile(r'\bofcyber', re.IGNORECASE), "ofcyber... -> of cyber..."),
    (re.compile(r'\bacharge\b', re.IGNORECASE), "acharge -> a charge"),
    (re.compile(r'\bhefai\b', re.IGNORECASE), "hefai -> he fai(led)"),
    (re.compile(r'\bmakeit\b', re.IGNORECASE), "makeit -> make it"),
    (re.compile(r'\bcarry-onbag', re.IGNORECASE), "carry-onbag -> carry-on bag"),
    (re.compile(r'\bsuchas\b', re.IGNORECASE), "suchas -> such as"),
    (re.compile(r'\bshewas\b', re.IGNORECASE), "shewas -> she was"),
    (re.compile(r'\bcanbe\b', re.IGNORECASE), "canbe -> can be"),
    (re.compile(r'\btobe\b', re.IGNORECASE), "tobe -> to be"),
    (re.compile(r'\bsohe\b', re.IGNORECASE), "sohe -> so he"),
    (re.compile(r'\bhowever(?=[a-z])', re.IGNORECASE), None),  # skip
    (re.compile(r'(?<=[a-z])ledto\b', re.IGNORECASE), "...ledto -> ...led to"),
    (re.compile(r'\bregularlyassigned\b', re.IGNORECASE), "regularlyassigned -> regularly assigned"),
    (re.compile(r'\bHowdoes\b', re.IGNORECASE), "Howdoes -> How does"),
    (re.compile(r'\bbannedin\b', re.IGNORECASE), "bannedin -> banned in"),
    (re.compile(r'\bwhene?ver\b', re.IGNORECASE), None),  # skip - valid word
    (re.compile(r'\bifa\b', re.IGNORECASE), "ifa -> if a"),
    (re.compile(r'\borit\b', re.IGNORECASE), "orit -> or it"),
    (re.compile(r'\bsare\b', re.IGNORECASE), "...sare -> ...s are"),
    (re.compile(r'(?<=[a-z])edto\b', re.IGNORECASE), "...edto -> ...ed to"),
    (re.compile(r'\bavictim\b', re.IGNORECASE), "avictim -> a victim"),
    (re.compile(r'\bafine\b', re.IGNORECASE), "afine -> a fine"),
    (re.compile(r'\balocal\b', re.IGNORECASE), "alocal -> a local"),
    (re.compile(r'\bforbiddenit', re.IGNORECASE), "forbiddenit... -> forbidden it..."),
    (re.compile(r'\boffr?audsters\b', re.IGNORECASE), "of fraudsters -> of fraudsters"),
    (re.compile(r'\boflaws?\b', re.IGNORECASE), None),  # skip
    (re.compile(r'\bstep\s*pedupto\b', re.IGNORECASE), "steppedupto -> stepped up to"),
    (re.compile(r'\btocalm\b', re.IGNORECASE), "tocalm -> to calm"),
    (re.compile(r'\bbyplacing\b', re.IGNORECASE), "byplacing -> by placing"),
    (re.compile(r"\bsuspect.?sre\b", re.IGNORECASE), "suspect'sre -> suspect's re..."),
    (re.compile(r'\bingimmediate\b', re.IGNORECASE), "...ingimmediate -> ...ing immediate"),
    (re.compile(r'\bCreationof\b', re.IGNORECASE), "Creationof -> Creation of"),
    (re.compile(r'\bEvolutiono[fp]\b', re.IGNORECASE), "Evolutionof -> Evolution of"),
    (re.compile(r'\bjobop\b', re.IGNORECASE), "jobop -> job op..."),
    (re.compile(r'\bbebuilt\b', re.IGNORECASE), "bebuilt -> be built"),
    (re.compile(r'\bLossof\b', re.IGNORECASE), "Lossof -> Loss of"),
    (re.compile(r'\bsuchasabonus\b', re.IGNORECASE), "suchasabonus -> such as a bonus"),
    (re.compile(r'\borlotteryas\b', re.IGNORECASE), "orlotteryas -> or lottery as"),
    (re.compile(r'\boccur\s*rence\b', re.IGNORECASE), None),  # skip, handled by broken_word
]
KNOWN_CONCAT_PATTERNS = [(p, d) for p, d in KNOWN_CONCAT_PATTERNS if d is not None]


def find_missing_spaces(text):
    """Find missing spaces between concatenated English words."""
    issues = []

    # 1. Known concatenation patterns
    for pattern, description in KNOWN_CONCAT_PATTERNS:
        for match in pattern.finditer(text):
            issues.append({
                "type": "missing_space",
                "subtype": "known_concatenation",
                "matched_text": match.group(),
                "description": description,
                "position": match.start(),
                "context": text[max(0, match.start()-20):match.end()+20]
            })

    # 2. Preposition/article concatenation
    for match in PREP_CONCAT.finditer(text):
        prep = match.group(1)
        next_word_start = match.group(2)
        full_start = match.start()

        # Get the full concatenated string
        rest_text = text[match.end():]
        rest_match = re.match(r'[a-zA-Z]*', rest_text)
        full_concat = match.group() + (rest_match.group() if rest_match else '')

        # Filter out words that legitimately start with these prefixes
        fc_lower = full_concat.lower()
        if fc_lower in PREFIX_WORDS or fc_lower in KNOWN_WORDS:
            continue

        # Additional filter: check if the entire concatenated string is a valid English word
        # by checking if it appears as a standalone word elsewhere or is in common dictionaries
        # Many "in-" words, "or-" words, "as-" words etc. are legitimate
        # If the second capture group + rest forms a valid word on its own, it might be
        # part of a legitimate word, not a concatenation
        remainder = fc_lower[len(prep):]
        if (fc_lower.startswith('in') and remainder + 'e' in PREFIX_WORDS) or \
           (fc_lower.startswith('in') and remainder + 'ed' in PREFIX_WORDS) or \
           (fc_lower.startswith('in') and remainder + 'ing' in PREFIX_WORDS) or \
           (fc_lower.startswith('in') and remainder in PREFIX_WORDS):
            continue
        if (fc_lower.startswith('or') and fc_lower in {'orative', 'orator', 'oration'}):
            continue
        if (fc_lower.startswith('as') and fc_lower.startswith('assoc')):
            continue
        # "Athens" is a proper noun, not "at" + "hens" or "the" + "ns"
        if fc_lower in {'athens', 'athena', 'athenian', 'athenians'}:
            continue

        # Check if the FULL word (prep + rest) matches a word boundary pattern
        # that indicates it's a standalone word rather than two stuck-together words
        # Heuristic: if there are spaces on both sides of the match, and the full_concat
        # looks like it could be a single word (all lowercase, reasonable length)
        # Check the actual text for word boundaries
        char_before = text[full_start - 1] if full_start > 0 else ' '
        char_after_pos = full_start + len(full_concat)
        char_after = text[char_after_pos] if char_after_pos < len(text) else ' '
        if char_before == ' ' and char_after in (' ', '.', ',', '!', '?', ';', ':', '\n'):
            # It's a standalone word - more likely a real word than concatenation
            # Only flag if it's clearly two common words stuck together
            if not (prep.lower() in {'of', 'in', 'to', 'for', 'by', 'at', 'on', 'or', 'as'} and
                    remainder.lower() in COMMON_SHORT_WORDS or
                    remainder.lower().rstrip('s') in COMMON_SHORT_WORDS):
                # Additional check: is the second part a recognizable word?
                if remainder not in {'the', 'a', 'an', 'their', 'them', 'they', 'his', 'her',
                                    'its', 'our', 'your', 'my', 'this', 'that', 'these', 'those',
                                    'all', 'each', 'every', 'some', 'any', 'no', 'not',
                                    'you', 'he', 'she', 'we', 'it', 'will', 'can', 'may',
                                    'must', 'has', 'had', 'was', 'were', 'are', 'been', 'have'}:
                    # Could be a legitimate word - skip unless we're very sure
                    # Only keep if the remainder contains uppercase or other concatenation markers
                    if remainder.islower() and len(full_concat) >= 8:
                        continue

        # Short concatenations that aren't in our known concat list: skip
        if len(full_concat) <= 5 and fc_lower not in {'inthe', 'ofthe', 'tothe', 'onthe',
                                                        'atthe', 'bythe', 'asthe',
                                                        'ofa', 'ina', 'toa', 'fora', 'ona', 'ata', 'bya',
                                                        'inan', 'ofan', 'toan', 'foran',
                                                        'ofit', 'toit', 'init', 'forit',
                                                        }:
            continue

        issues.append({
            "type": "missing_space",
            "subtype": "concatenated_preposition",
            "matched_text": full_concat,
            "description": f"'{prep}' + '{full_concat[len(prep):]}'",
            "position": full_start,
            "context": text[max(0, full_start-20):full_start + len(full_concat) + 20]
        })

    # 3. Lowercase-period-uppercase or lowercase-uppercase concatenation in English
    for match in CONCAT_LOWER_UPPER.finditer(text):
        before = match.group(1)
        after = match.group(2)
        pos = match.start()

        # Only in English context
        if not is_english_context(text, pos):
            continue

        # Skip known abbreviations
        ctx_before = text[max(0, pos-10):pos+len(before)]
        if re.search(r'\b(?:Mr|Mrs|Ms|Dr|Jr|Sr|St|vs|etc|Inc|Ltd|Corp|dept|govt|Prof|Rev|Gen|Sgt|Lt|Capt|Col|Maj|No|Vol|Ch|Sec|Art|Fig|Tab|Eq|Ref|App|dept)\.$', ctx_before, re.IGNORECASE):
            continue
        # Skip U.S.A type abbreviations
        if re.search(r'[A-Z]\.[A-Z]', ctx_before):
            continue

        # Skip unit suffixes like kHz, MHz
        if re.match(r'^[kMGTnmu]?Hz$', before[-1:] + after):
            continue

        # Check if this has a period (missing space after punctuation)
        if '.' in before:
            issues.append({
                "type": "missing_space",
                "subtype": "after_punctuation",
                "matched_text": before + after,
                "description": f"no space after period: '{before}{after}'",
                "position": pos,
                "context": text[max(0, pos-20):match.end()+20]
            })
        else:
            # CamelCase concatenation
            # Get full word before
            word_before_match = re.search(r'([a-zA-Z]+)$', text[:pos+len(before)])
            if word_before_match:
                full_word = word_before_match.group(1)
                if len(full_word) >= 2:
                    issues.append({
                        "type": "missing_space",
                        "subtype": "camelcase_concatenation",
                        "matched_text": full_word + after,
                        "description": f"'{full_word}' + '{after}' concatenated",
                        "position": word_before_match.start(),
                        "context": text[max(0, word_before_match.start()-15):match.end()+15]
                    })

    # 4. Comma without space in English context
    for match in re.finditer(r'(?<=[a-zA-Z]),([a-zA-Z]{2,})', text):
        if is_english_context(text, match.start()):
            issues.append({
                "type": "missing_space",
                "subtype": "after_comma",
                "matched_text": text[match.start():match.end()],
                "position": match.start(),
                "context": text[max(0, match.start()-20):match.end()+20]
            })

    return issues


# ============================================================
# 3. GARBLED/BROKEN CHARACTERS & ENCODING ISSUES
# ============================================================

GARBLED_PATTERNS = [
    (re.compile(r'\ufffd'), "replacement_character"),
    (re.compile(r'\x00'), "null_byte"),
    (re.compile(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]'), "control_character"),
    (re.compile(r'[\ue000-\uf8ff]'), "private_use_area_char"),
    (re.compile(r'&(?:amp|lt|gt|quot|nbsp|apos|#\d+|#x[0-9a-fA-F]+);'), "unescaped_html_entity"),
    (re.compile(r'\(cid:\d+\)'), "cid_reference"),
    (re.compile('[\u00c0-\u00c3][\u0080-\u00bf]'), "mojibake_utf8_as_latin1"),
]


# ============================================================
# 4. Extra whitespace in English text
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
    """Scan a text string for OCR artifacts."""
    issues = []
    seen_spans = []  # Track (start, end) to avoid overlapping reports

    def overlaps(start, end):
        for s, e in seen_spans:
            if start < e and end > s:
                return True
        return False

    # 1. Specific broken word patterns (highest confidence)
    for pattern, description in SPECIFIC_OCR_BREAKS:
        for match in pattern.finditer(text):
            mt = match.group()
            # MUST contain at least one space to be a broken word
            if ' ' not in mt and '\t' not in mt:
                continue
            if not overlaps(match.start(), match.end()):
                seen_spans.append((match.start(), match.end()))
                issues.append({
                    "type": "broken_word",
                    "field": field_name,
                    "matched_text": mt,
                    "description": description,
                    "position": match.start(),
                    "context": text[max(0, match.start()-30):match.end()+30]
                })

    # 2. Generic broken word detection
    for item in check_generic_broken_word(text):
        start = item["position"]
        end = start + len(item["matched_text"])
        if not overlaps(start, end):
            seen_spans.append((start, end))
            item["field"] = field_name
            issues.append(item)

    # 3. Missing spaces
    for item in find_missing_spaces(text):
        item["field"] = field_name
        issues.append(item)

    # 4. Garbled/encoding issues
    for pattern, gtype in GARBLED_PATTERNS:
        for match in pattern.finditer(text):
            matched = match.group()
            issues.append({
                "type": "encoding_issue",
                "subtype": gtype,
                "field": field_name,
                "matched_text": repr(matched) if gtype not in ("cid_reference", "unescaped_html_entity") else matched,
                "char_code": f"U+{ord(matched[0]):04X}" if len(matched) >= 1 and gtype not in ("cid_reference", "unescaped_html_entity") else "",
                "position": match.start(),
                "context": text[max(0, match.start()-20):match.end()+20]
            })

    # 5. Extra whitespace in English text
    for match in MULTI_SPACE_IN_ENGLISH.finditer(text):
        if is_english_context(text, match.start()):
            issues.append({
                "type": "extra_whitespace",
                "field": field_name,
                "matched_text": repr(match.group()),
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
            found = scan_text_for_issues(text, field_name)
            for issue in found:
                issue["question_number"] = q_num
                issue["question_type"] = q_type
                file_issues.append(issue)

    return file_issues


def deduplicate_issues(issues):
    """Remove duplicate issues."""
    seen = set()
    unique = []
    for issue in issues:
        key = (issue.get("type"), issue.get("subtype", ""),
               issue.get("field"), issue.get("position", 0),
               issue.get("matched_text"))
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique


def main():
    print("Starting OCR artifact scan (v3)...", file=sys.stderr)

    # Collect all exam JSON files (skip top-level metadata)
    exam_files = []
    for root, dirs, files in os.walk(BASE_DIR):
        for fname in files:
            if fname.endswith('.json'):
                fpath = os.path.join(root, fname)
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

    # Build report
    report = {
        "scan_summary": {
            "total_files_scanned": len(exam_files),
            "files_with_issues": files_with_issues,
            "total_issues_found": total_issues,
            "issue_type_breakdown": {},
            "issue_subtype_breakdown": {}
        },
        "files_with_issues": all_results
    }

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

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\nScan complete!", file=sys.stderr)
    print(f"  Files scanned: {len(exam_files)}", file=sys.stderr)
    print(f"  Files with issues: {files_with_issues}", file=sys.stderr)
    print(f"  Total issues found: {total_issues}", file=sys.stderr)
    print(f"  Report written to: {OUTPUT_FILE}", file=sys.stderr)
    print(json.dumps(report["scan_summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
