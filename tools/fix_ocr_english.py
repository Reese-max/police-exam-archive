#!/usr/bin/env python3
"""
Fix OCR artifacts in English text within police exam JSON files.

The OCR process systematically inserted spaces within English words and
removed spaces between words. This script fixes both types of artifacts
using a dictionary-based approach.

Two main artifact types:
1. Spaces inserted within words: "Art ificial" -> "Artificial"
2. Spaces removed between words: "toevolve" -> "to evolve"
"""

import json
import os
import re
import sys
from pathlib import Path
from collections import defaultdict

BASE_DIR = "/home/user/police-exam-archive/考古題庫"
WORDS_FILE = "/home/user/police-exam-archive/tools/english_words.json"
LOG_FILE = "/home/user/police-exam-archive/tools/fix_ocr_english_log.txt"

# ============================================================================
# WORD DICTIONARY
# ============================================================================

def build_dictionary():
    """Build a comprehensive English dictionary for validation."""
    words = set()

    # Load from english_words.json
    if os.path.exists(WORDS_FILE):
        with open(WORDS_FILE, 'r', encoding='utf-8') as f:
            word_freq = json.load(f)
            words.update(w.lower() for w in word_freq.keys())

    # Common English words that might not be in the frequency list
    # This is a comprehensive set focusing on words commonly found in these exams
    extra_words = {
        # Articles, prepositions, conjunctions, pronouns
        "a", "an", "the", "in", "on", "at", "to", "for", "of", "with",
        "by", "from", "up", "about", "into", "through", "during", "before",
        "after", "above", "below", "between", "under", "over", "out",
        "off", "down", "near", "against", "along", "around", "behind",
        "beside", "beyond", "toward", "towards", "upon", "within", "without",
        "and", "but", "or", "nor", "so", "yet", "both", "either", "neither",
        "not", "only", "also", "than", "then", "when", "where", "while",
        "although", "because", "since", "unless", "until", "whether",
        "i", "me", "my", "mine", "myself", "we", "us", "our", "ours",
        "ourselves", "you", "your", "yours", "yourself", "yourselves",
        "he", "him", "his", "himself", "she", "her", "hers", "herself",
        "it", "its", "itself", "they", "them", "their", "theirs", "themselves",
        "this", "that", "these", "those", "what", "which", "who", "whom",
        "whose", "how", "why", "if", "as",

        # Common verbs (all forms)
        "is", "am", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "having", "do", "does", "did", "doing", "done",
        "will", "would", "shall", "should", "may", "might", "can", "could",
        "must", "need", "dare", "ought",
        "get", "gets", "got", "getting", "gotten",
        "go", "goes", "went", "going", "gone",
        "come", "comes", "came", "coming",
        "make", "makes", "made", "making",
        "take", "takes", "took", "taken", "taking",
        "give", "gives", "gave", "given", "giving",
        "find", "finds", "found", "finding",
        "know", "knows", "knew", "known", "knowing",
        "think", "thinks", "thought", "thinking",
        "say", "says", "said", "saying",
        "see", "sees", "saw", "seen", "seeing",
        "tell", "tells", "told", "telling",
        "use", "uses", "used", "using",
        "try", "tries", "tried", "trying",
        "keep", "keeps", "kept", "keeping",
        "let", "lets", "letting",
        "begin", "begins", "began", "begun", "beginning",
        "show", "shows", "showed", "shown", "showing",
        "hear", "hears", "heard", "hearing",
        "play", "plays", "played", "playing",
        "run", "runs", "ran", "running",
        "move", "moves", "moved", "moving",
        "live", "lives", "lived", "living",
        "believe", "believes", "believed", "believing",
        "bring", "brings", "brought", "bringing",
        "happen", "happens", "happened", "happening",
        "write", "writes", "wrote", "written", "writing",
        "sit", "sits", "sat", "sitting",
        "stand", "stands", "stood", "standing",
        "lose", "loses", "lost", "losing",
        "pay", "pays", "paid", "paying",
        "meet", "meets", "met", "meeting",
        "include", "includes", "included", "including",
        "continue", "continues", "continued", "continuing",
        "set", "sets", "setting",
        "learn", "learns", "learned", "learning",
        "change", "changes", "changed", "changing",
        "lead", "leads", "led", "leading",
        "understand", "understands", "understood", "understanding",
        "watch", "watches", "watched", "watching",
        "follow", "follows", "followed", "following",
        "stop", "stops", "stopped", "stopping",
        "create", "creates", "created", "creating",
        "speak", "speaks", "spoke", "spoken", "speaking",
        "read", "reads", "reading",
        "allow", "allows", "allowed", "allowing",
        "add", "adds", "added", "adding",
        "spend", "spends", "spent", "spending",
        "grow", "grows", "grew", "grown", "growing",
        "open", "opens", "opened", "opening",
        "walk", "walks", "walked", "walking",
        "win", "wins", "won", "winning",
        "offer", "offers", "offered", "offering",
        "remember", "remembers", "remembered", "remembering",
        "consider", "considers", "considered", "considering",
        "appear", "appears", "appeared", "appearing",
        "buy", "buys", "bought", "buying",
        "wait", "waits", "waited", "waiting",
        "serve", "serves", "served", "serving",
        "die", "dies", "died", "dying",
        "send", "sends", "sent", "sending",
        "expect", "expects", "expected", "expecting",
        "build", "builds", "built", "building",
        "stay", "stays", "stayed", "staying",
        "fall", "falls", "fell", "fallen", "falling",
        "cut", "cuts", "cutting",
        "reach", "reaches", "reached", "reaching",
        "kill", "kills", "killed", "killing",
        "remain", "remains", "remained", "remaining",
        "suggest", "suggests", "suggested", "suggesting",
        "raise", "raises", "raised", "raising",
        "pass", "passes", "passed", "passing",
        "sell", "sells", "sold", "selling",
        "require", "requires", "required", "requiring",
        "report", "reports", "reported", "reporting",
        "decide", "decides", "decided", "deciding",
        "pull", "pulls", "pulled", "pulling",
        "develop", "develops", "developed", "developing",
        "cause", "causes", "caused", "causing",
        "cross", "crosses", "crossed", "crossing",
        "ensure", "ensures", "ensured", "ensuring",
        "recognize", "recognizes", "recognized", "recognizing",
        "determine", "determines", "determined", "determining",
        "evolve", "evolves", "evolved", "evolving",
        "discuss", "discusses", "discussed", "discussing",
        "collect", "collects", "collected", "collecting",

        # Common nouns found in these exam passages
        "people", "person", "time", "year", "years", "way", "day", "days",
        "man", "men", "woman", "women", "child", "children", "world",
        "life", "hand", "part", "place", "case", "week", "company",
        "system", "program", "question", "work", "government", "number",
        "night", "point", "home", "water", "room", "mother", "area",
        "money", "story", "fact", "month", "lot", "right", "study",
        "book", "eye", "job", "word", "business", "issue", "side",
        "kind", "head", "house", "service", "friend", "father", "power",
        "hour", "game", "line", "end", "members", "family", "law",
        "car", "city", "community", "name", "president", "team", "minute",
        "idea", "body", "information", "back", "parent", "face", "others",
        "level", "office", "door", "health", "art", "war", "history",
        "party", "result", "change", "morning", "reason", "research",
        "girl", "guy", "moment", "air", "teacher", "force", "education",

        # Words commonly OCR-broken in these exams
        "artificial", "intelligence", "workforce", "alarmist", "headlines",
        "machines", "humans", "passion", "responsibilities", "abilities",
        "existing", "replaced", "created", "uncertainty", "challenging",
        "transformative", "reaching", "economic", "regulatory", "implications",
        "discussing", "preparing", "determining", "pedestrian", "examples",
        "challenges", "intelligent", "unforeseen", "consequences", "unintended",
        "outcomes", "proficient", "designed", "crosses", "ethical", "boundaries",
        "original", "intent", "humanity", "destructive", "efficient",
        "negatively", "overarching", "algorithms", "powered", "compromised",
        "businesses", "governments", "decisions", "oppression",
        "officials", "overseas", "fighting", "extradition", "extraction",
        "exposition", "exemption", "accounts", "terrestrial", "tremendous",
        "tenacious", "dominance", "manufacturer", "clicking", "phishing",
        "appealing", "alluding", "conviction", "differentiate", "conductive",
        "opportunities", "projected", "vehicles", "streets", "control",
        "super", "collecting", "vast", "data",
        "officers", "officer", "contently", "tournament", "industries",
        "transcultural", "intercultural", "transnational", "abandons",
        "smoother", "stranded", "coordination", "inclination", "contestant",

        # Biometric passage words
        "biometric", "biometrics", "identification", "fingerprints", "fingerprint",
        "scanners", "behavioral", "physiological", "morphology", "irises",
        "identifiers", "prevalentasa", "enhancing", "protecting", "individuals",
        "features", "ensures", "claims", "impossible", "steal",
        "unique", "signature", "problematic", "copied", "subtleties",
        "intonation", "accents", "likewise", "convincingly", "applications",
        "verification", "discover", "passports", "forged", "effective",
        "additions", "replacements", "photographs", "promise", "concerns",
        "surrounding", "critics", "possibility", "legitimate", "organizations",
        "advocates", "potential", "abuse", "authorities", "policymakers",
        "considerations", "developing",

        # Additional common English words
        "able", "about", "above", "according", "across", "actually", "after",
        "again", "against", "ago", "agree", "ahead", "almost", "along",
        "already", "also", "always", "among", "amount", "another", "answer",
        "any", "anyone", "anything", "anyway", "apart", "apparently",
        "apply", "approach", "argument", "around", "ask", "attention",
        "available", "away", "bad", "based", "beautiful", "became",
        "become", "becomes", "becoming", "been", "before", "began",
        "behind", "being", "best", "better", "between", "big", "bit",
        "black", "blood", "blue", "board", "body", "book", "both",
        "boy", "break", "bring", "brother", "brown", "build", "business",
        "busy", "call", "came", "campaign", "care", "carry", "caught",
        "center", "central", "certain", "certainly", "chair", "chance",
        "character", "charge", "check", "choice", "church", "claim",
        "class", "clean", "clear", "clearly", "close", "cold",
        "college", "color", "common", "community", "complete", "computer",
        "concern", "condition", "conference", "consider", "contain",
        "continue", "control", "cost", "could", "country", "couple",
        "course", "court", "cover", "crime", "criminal", "cultural",
        "cup", "current", "customer", "cut", "dangerous", "dark",
        "data", "daughter", "deal", "death", "debate", "decade",
        "decision", "deep", "degree", "demand", "department", "describe",
        "design", "despite", "detail", "develop", "development",
        "difference", "different", "difficult", "dinner", "direction",
        "director", "discover", "discussion", "disease", "doctor",
        "dog", "done", "door", "down", "draw", "dream", "drink",
        "drive", "drop", "drug", "during", "each", "early", "east",
        "easy", "eat", "economic", "economy", "edge", "education",
        "effect", "effort", "eight", "either", "election", "else",
        "employee", "energy", "enjoy", "enough", "enter", "entire",
        "environment", "especially", "establish", "even", "evening",
        "ever", "every", "everybody", "everyone", "everything",
        "evidence", "exactly", "example", "executive", "exist",
        "experience", "expert", "explain", "eye", "face", "factor",
        "fail", "family", "far", "fast", "father", "fear", "federal",
        "feel", "few", "field", "fight", "figure", "fill", "film",
        "final", "finally", "financial", "find", "fine", "finger",
        "finish", "fire", "firm", "first", "fish", "five", "floor",
        "fly", "follow", "food", "foot", "force", "foreign", "forget",
        "form", "former", "forward", "four", "free", "friend", "front",
        "full", "fund", "future", "garden", "general", "generation",
        "girl", "glass", "goal", "going", "gold", "gone", "good",
        "great", "green", "ground", "group", "growth", "guess", "gun",
        "guy", "hair", "half", "hand", "hang", "happy", "hard",
        "head", "heart", "heat", "heavy", "help", "here", "herself",
        "high", "himself", "hit", "hold", "hope", "hospital", "hot",
        "hotel", "hour", "house", "huge", "human", "hundred",

        # Words with common OCR breaks
        "execution", "terminated", "disseminating", "fraudulent",
        "specialness", "significance", "sufficient", "proficiency",
        "emergency", "excellence", "extraordinary", "implementation",
        "investigation", "manufacturing", "organization", "participation",
        "predominantly", "representation", "simultaneously", "specifically",
        "substantially", "transformation", "unconstitutional", "unfortunately",
        "characterization", "communication", "comprehensive", "concentration",
        "consideration", "demonstration", "determination", "identification",
        "independently", "organizational", "overwhelming", "pharmaceutical",

        # Police/law enforcement vocabulary
        "arrest", "bail", "burglary", "conviction", "custody", "defendant",
        "detective", "enforcement", "evidence", "felony", "forensic",
        "guilty", "harassment", "homicide", "incarceration", "indictment",
        "investigation", "jurisdiction", "juvenile", "kidnapping", "larceny",
        "manslaughter", "misdemeanor", "narcotics", "negligence",
        "offender", "parole", "patrol", "penalty", "perjury", "plaintiff",
        "plea", "probation", "prosecution", "prosecutor", "robbery",
        "sentence", "smuggling", "stalking", "surveillance", "suspect",
        "testimony", "theft", "trafficking", "trespassing", "vandalism",
        "verdict", "violation", "warrant", "witness",

        # Technology/AI vocabulary
        "algorithm", "application", "autonomous", "blockchain", "chatbot",
        "cybercrime", "cybersecurity", "database", "deepfake", "digital",
        "encryption", "malware", "network", "phishing", "privacy",
        "ransomware", "recognition", "software", "technology", "virtual",

        # More comprehensive word list - common suffixed forms
        "ability", "accessible", "accountability", "achievement", "acquisition",
        "activities", "additional", "addressed", "administration", "advantage",
        "affecting", "affordable", "agencies", "aggressive", "alternative",
        "amendment", "analysis", "announcement", "appearance", "applicable",
        "appreciation", "arrangement", "assessment", "assistance", "associated",
        "assumption", "attendance", "awareness",
        "basically", "beginning", "beneficial", "boundaries",
        "calculated", "capability", "categories", "celebration", "certainly",
        "characteristic", "circumstances", "classification", "collaboration",
        "combination", "comfortable", "commercial", "commission", "committed",
        "communicate", "comparison", "competition", "complaint", "completely",
        "complexity", "compliance", "complicated", "composition", "compromise",
        "concentrate", "concluded", "conducted", "confident", "confirmed",
        "confronted", "connected", "consequence", "conservation", "considerable",
        "consistently", "conspiracy", "constitutional", "construction",
        "consultation", "consumption", "contemporary", "contribution",
        "controversial", "conventional", "convinced", "cooperation",
        "corporation", "corresponding", "criticism", "crucial",
        "damaged", "dangerous", "deadline", "dedicated", "definitely",
        "deliberately", "democratic", "demonstrate", "departure", "depending",
        "depression", "description", "designated", "desperation", "destination",
        "destruction", "determination", "devastating", "differences",
        "dimensional", "diplomatic", "disability", "disadvantage", "disagreement",
        "disappointed", "discipline", "discrimination", "displaying",
        "distribution", "documentary", "documentation", "dramatically",
        "ecological", "educational", "effectiveness", "efficiently",
        "electronic", "elimination", "embarrassed", "emergency", "emotional",
        "emphasized", "employment", "empowered", "encountered", "encouraged",
        "engagement", "engineering", "entertainment", "enthusiasm",
        "environmental", "equipment", "equivalent", "essential", "established",
        "evaluation", "eventually", "examination", "exceptional", "excitement",
        "exclusively", "exhibition", "expanded", "expectation", "expedition",
        "experienced", "experiment", "explanation", "explicitly", "exploration",
        "expression", "extensively", "extraordinary",

        # More word forms
        "cigarettes", "cigarette", "addiction", "dichotomy", "dissonance",
        "impeccable", "intolerance", "concentration", "acceleration",
        "breathalyzer", "breath", "alcohol", "pathologists", "forbidden",
        "screening", "activities", "endanger", "sentences", "excess",
        "eligible", "released",

        # Words from passage context
        "letting", "countries", "response", "developed", "recognize",
        "invention", "agencies", "century", "increasingly", "prevalent",
        "means", "security", "interests", "morphology", "programs",
        "physical", "scanned", "personal", "numbers", "access",
        "extremely", "difficult", "impossible", "criminals", "behavioral",
        "certain", "behaviors", "classic", "marker", "nature",
        "automatically", "subtleties", "speaks", "regional", "patterns",
        "typing", "observe", "mimic", "convincingly", "potential",
        "discover", "identity", "unknown", "joined", "common",
        "purpose", "verify", "stolen", "forged", "effective", "fool",
        "utilizing", "instance", "implemented", "utilizes", "addition",
        "shows", "various", "surrounding", "critics", "worry",
        "possibility", "legitimate", "scanners", "information", "civil",
        "liberties", "concerned", "therefore", "makers", "balance",
        "freedom", "privacy",

        # More forms
        "regarding", "disregard", "protecting", "likelihood", "misuse",
        "signatures", "protect", "created", "projected",
    }

    words.update(extra_words)

    return words


# ============================================================================
# EXPLICIT OCR FIX MAPPINGS
# ============================================================================

# These are patterns found by examining the actual data. They handle both
# spaces-within-words and missing-spaces-between-words cases.
# Order matters - longer/more specific patterns should come first.

EXPLICIT_FIXES = [
    # === Multi-word compound fixes (spaces removed between words) ===
    # These MUST come before single-word fixes to avoid partial matches

    # Very long compound patterns first
    ("prevalentasa means ofenhancing", "prevalent as a means of enhancing"),
    ("feature sensu rest hat the", "features ensure that the"),
    ("behavior sareuniquetoindividuals", "behaviors are unique to individuals"),
    ("behavior albiometric mark eris aperson'ssig nature", "behavioral biometric marker is a person's signature"),
    ("problematica sit canbe", "problematic as it can be"),
    ("subt let ies", "subtleties"),
    ("into nation and regional", "intonation and regional"),
    ("app lications", "applications"),
    ("consider ing biometric add itions to or replace ments of exist ing", "considering biometric additions to or replacements of existing"),
    ("andiris scans, in add ition top hot ographs", "and iris scans, in addition to photographs"),
    ("consider ations must be taken into account when develop ing", "considerations must be taken into account when developing"),
    ("protect ingindividuals'", "protecting individuals'"),
    ("isbiometric", "is biometric"),
    ("asbiometricidentifiers", "as biometric identifiers"),
    ("age ncies", "agencies"),
    ("finger prints", "fingerprints"),
    ("finger print", "fingerprint"),
    ("effectivebiometric", "effective biometric"),
    ("for ged", "forged"),
    ("Behavior albiometrics", "Behavioral biometrics"),
    ("behavior albiometrics", "behavioral biometrics"),
    ("like wise", "likewise"),
    ("canbe stolen", "can be stolen"),
    ("canbe problematic", "can be problematic"),
    ("canbe copied", "can be copied"),

    # Passage about AI
    ("Art ificial intelligence", "Artificial intelligence"),
    ("art ificial intelligence", "artificial intelligence"),
    ("Art ificial Intelligence", "Artificial Intelligence"),
    ("work force toevolve", "workforce to evolve"),
    ("work force responsibilities", "workforce responsibilities"),
    ("work force", "workforce"),
    ("alarm ist head lines", "alarmist headlines"),
    ("loss ofjobs tom achines", "loss of jobs to machines"),
    ("ofjobs tom achines", "of jobs to machines"),
    ("human sto find their pass ion", "humans to find their passion"),
    ("exist ing jobs will be replace dbyAI", "existing jobs will be replaced by AI"),
    ("replace dbyAI", "replaced by AI"),
    ("in the UKfrom", "in the UK from"),
    ("jobs could becreated", "jobs could be created"),
    ("the change sto how", "the changes to how"),
    ("could bech all enging", "could be challenging"),
    ("trans form ative impact ofartificial", "transformative impact of artificial"),
    ("far-reach ing economic", "far-reaching economic"),
    ("implication sthatwe need tobediscus sing", "implications that we need to be discussing"),
    ("De term ining who", "Determining who"),
    ("de term ining who", "determining who"),
    ("pede str ian", "pedestrian"),
    ("example sof the challenge stobefaced", "examples of the challenges to be faced"),
    ("example sof", "examples of"),
    ("challenge stobefaced", "challenges to be faced"),
    ("super-in tell igent", "super-intelligent"),
    ("uper-in tell igent", "uper-intelligent"),  # for "becomes uper-intelligent"
    ("becomes uper-in tell igent", "become super-intelligent"),
    ("wedo know", "we do know"),
    ("unfore seen consequences", "unforeseen consequences"),
    ("unin ten ded out comes of art ificial", "unintended outcomes of artificial"),
    ("unin ten ded out comes", "unintended outcomes"),
    ("was designed todo that itcrosses", "was designed to do that it crosses"),
    ("designed todo", "designed to do"),
    ("itcrosses over", "it crosses over"),
    ("orig ina lintent", "original intent"),
    ("human ity", "humanity"),
    ("over arching goals", "overarching goals"),
    ("bus inesses and governments", "businesses and governments"),
    ("bus inesses", "businesses"),

    # Q41: officials / overseas
    ("off icials were accused", "officials were accused"),
    ("off icials", "officials"),
    ("over seas before", "overseas before"),
    ("over seas", "overseas"),

    # Q42: fighting / extradition
    ("fight ing_____to theU. K.to", "fighting _____ to the U.K. to"),
    ("fight ing", "fighting"),
    ("theU. K.to", "the U.K. to"),
    ("theU. K.", "the U.K."),
    ("extr action", "extraction"),

    # Q43: exposition
    ("expo sit ion", "exposition"),

    # Q44: card accounts
    ("car dac counts", "card accounts"),

    # Q45: terrestrial, tremendous, tenacious
    ("terres trial", "terrestrial"),
    ("trem end ous", "tremendous"),
    ("ten acious", "tenacious"),
    ("when ever she was", "whenever she was"),
    ("when ever", "whenever"),

    # Q46: dominance, manufacturer
    ("Taiwan'sdom ina nce can be", "Taiwan's dominance can be"),
    ("dom ina nce", "dominance"),
    ("be_____toTSMC", "be _____ to TSMC"),
    ("_____toTSMC", "_____ to TSMC"),
    ("world'slargest contract chipmanu fact urer", "world's largest contract chip manufacturer"),
    ("world'slargest", "world's largest"),
    ("chipmanu fact urer", "chip manufacturer"),
    ("manu fact urer", "manufacturer"),

    # Q47: clicking on, phishing links
    ("clickingon those phishinglinks", "clicking on those phishing links"),
    ("clickingon", "clicking on"),
    ("phishinglinks", "phishing links"),

    # Q48: appealing, alluding, John is
    ("Johnis _____to the court", "John is _____ to the court"),
    ("Johnis", "John is"),
    ("appeal ing", "appealing"),
    ("all uding", "alluding"),

    # Q49: of a, to grant
    ("Because ofa previous", "Because of a previous"),
    ("ofa previous", "of a previous"),
    ("refused togrant David", "refused to grant David"),
    ("togrant", "to grant"),

    # Q50: differentiate, conductive
    ("different iate between", "differentiate between"),
    ("different iate", "differentiate"),
    ("conduct ive", "conductive"),

    # Q56-60 options
    ("Loss ofjobs tom achines", "Loss of jobs to machines"),
    ("ofjobs tom achines", "of jobs to machines"),
    ("op port unit ies", "opportunities"),
    ("collect ingvast amounts ofdata", "collecting vast amounts of data"),
    ("collect ingvast", "collecting vast"),
    ("amounts ofdata", "amounts of data"),
    ("ofdata", "of data"),
    ("vehicle son the str eets", "vehicles on the streets"),
    ("son the str eets", "s on the streets"),
    ("str eets", "streets"),
    ("ofhuman control", "of human control"),
    ("ofhuman", "of human"),
    ("Unfore seen", "Unforeseen"),
    ("unfore seen", "unforeseen"),
    ("projectedtobe create dbyAI", "projected to be created by AI"),
    ("projectedtobe", "projected to be"),
    ("create dbyAI", "created by AI"),
    ("theUK are", "the UK are"),
    ("theUK", "the UK"),
    ("byartificial intelligence", "by artificial intelligence"),
    ("byartificial", "by artificial"),
    ("AIalgorithms must be built", "AI algorithms must be built"),
    ("AIalgorithms", "AI algorithms"),
    ("Aslon gas the AIis doing", "As long as the AI is doing"),
    ("Aslon gas", "As long as"),
    ("AIis doing", "AI is doing"),
    ("wemayas well", "we may as well"),
    ("wemayas", "we may as"),
    ("becomes uper-in tell igent", "become super-intelligent"),
    ("bebuilt", "be built"),
    ("howdoes", "how does"),
    ("biometricmarker", "biometric marker"),
    ("theword\"forged\"mean", "the word \"forged\" mean"),
    ("theword", "the word"),
    ("likelihoodof misuse byauthorities", "likelihood of misuse by authorities"),
    ("likelihoodof", "likelihood of"),
    ("byauthorities", "by authorities"),
    ("dis regard for", "disregard for"),
    ("protect ing personal", "protecting personal"),
    ("Sign atures", "Signatures"),

    # Q112 year 43: forbidden items / airport
    ("for for biddenitems", "for forbidden items"),
    ("for biddenitems", "forbidden items"),
    ("act ivities", "activities"),
    ("end anger", "endanger"),

    # Q112 year 44: sentences in excess, eligible to be released on
    ("for sentence sinexcess off our years", "for sentences in excess of four years"),
    ("sentence sinexcess", "sentences in excess"),
    ("sinexcess", "s in excess"),
    ("off our years", "of four years"),
    ("eligib let obe release don", "eligible to be released on"),
    ("eligib let obe", "eligible to be"),
    ("release don", "released on"),

    # Q112 year 45
    ("_______isa criminal", "_______ is a criminal"),
    ("prosecution take sit very", "prosecution takes it very"),
    ("take sit very", "takes it very"),
    ("Dis son ance", "Dissonance"),
    ("dis son ance", "dissonance"),

    # Q112 year 46
    ("impecc able", "impeccable"),

    # Q112 year 47
    ("consume do range juic eat the party", "consumed orange juice at the party"),
    ("consume do range", "consumed orange"),
    ("juic eat the", "juice at the"),
    ("mybr eat halcohol", "my breath alcohol"),
    ("mybr eat h", "my breath"),
    ("eat halcohol", "alcohol"),
    ("into lerance", "intolerance"),

    # Q112 year 48: carrying
    ("carry ing out", "carrying out"),

    # Q112 year 50: e-cigarettes, addiction
    ("e-cig are ttes", "e-cigarettes"),
    ("cig are ttes", "cigarettes"),
    ("add iction", "addiction"),

    # Q112 year passage: letting, one response is
    ("we'renot let ting", "we're not letting"),
    ("we'renot", "we're not"),
    ("let ting", "letting"),
    ("countries?One response", "countries? One response"),
    ("heor she claims", "he or she claims"),
    ("heor she", "he or she"),
    ("ifnot impossible", "if not impossible"),
    ("ifnot", "if not"),
    ("for criminals tosteal", "for criminals to steal"),
    ("tosteal", "to steal"),
    ("usedto identify", "used to identify"),
    ("usedto", "used to"),
    ("suchas their speech", "such as their speech"),
    ("suchas", "such as"),
    ("aperson'ssig nature", "a person's signature"),
    ("aperson's", "a person's"),
    ("sig nature", "signature"),
    ("forthis purpose", "for this purpose"),
    ("forthis", "for this"),
    ("acommon tool", "a common tool"),
    ("acommon", "a common"),
    ("policy makers", "policymakers"),
    ("develop ing", "developing"),
    ("protect ing", "protecting"),
    ("consider ing", "considering"),
    ("add itions", "additions"),
    ("replace ments", "replacements"),
    ("exist ing", "existing"),
    ("add ition", "addition"),

    # Q112 year 42: pathologists
    ("path ologists", "pathologists"),

    # Q112 year 44: dichotomy
    ("dic hot omy", "dichotomy"),

    # Common patterns across many files
    ("isto ", "is to "),

    # More from passage review
    ("tobe ", "to be "),
    ("canbe ", "can be "),
    ("dowe ", "do we "),
    ("tothe ", "to the "),
    ("inthe ", "in the "),
    ("ofthe ", "of the "),
    ("isthe ", "is the "),
    ("forthe ", "for the "),
    ("onthe ", "on the "),
    ("atthe ", "at the "),
    ("bythe ", "by the "),
    ("andthe ", "and the "),
    ("fromthe ", "from the "),
    ("withthe ", "with the "),

    # Two-word merges
    ("toevolve", "to evolve"),
    ("todo ", "to do "),
    ("tobe", "to be"),
    ("canbe", "can be"),
    ("becreated", "be created"),
    ("itcrosses", "it crosses"),

    # 7.2million etc (number+word)
    ("7.2million", "7.2 million"),
    ("7million", "7 million"),
    ("14.2million", "14.2 million"),
    ("0.2million", "0.2 million"),

    # === Additional high-frequency OCR patterns found across all exam files ===

    # fight ers (128 occurrences across fire/police files)
    ("fire fight ers", "firefighters"),
    ("fire fight er", "firefighter"),
    ("fight ers are", "fighters are"),
    ("fight ers have", "fighters have"),
    ("fight ers", "fighters"),

    # depend ent (76 occurrences)
    ("in depend ent", "independent"),
    ("depend ent", "dependent"),

    # employ ees (64 occurrences)
    ("employ ees", "employees"),
    ("employ ee", "employee"),

    # racial ine quality (60 occurrences)
    ("racial ine quality", "racial inequality"),
    ("ine quality", "inequality"),

    # com man ded (60 occurrences)
    ("com man ded", "commanded"),
    ("com man der", "commander"),
    ("com man d", "command"),
    ("com bin ing", "combining"),
    ("Com bin ing", "Combining"),
    ("com bin ed", "combined"),
    ("com bin ation", "combination"),

    # harm ful (60 occurrences)
    ("harm ful", "harmful"),

    # apply ing (55 occurrences)
    ("apply ing", "applying"),

    # learn ing (55 occurrences)
    ("learn ing", "learning"),

    # reason ing (55 occurrences)
    ("reason ing", "reasoning"),

    # digital mis conduct (55 occurrences)
    ("digital mis conduct", "digital misconduct"),
    ("mis conduct", "misconduct"),

    # job dis place ment (55 occurrences)
    ("job dis place ment", "job displacement"),
    ("dis place ment", "displacement"),
    ("dis place men", "displacemen"),

    # dissem ina ting (48 occurrences)
    ("dissem ina ting", "disseminating"),
    ("dissem ina tion", "dissemination"),
    ("dissem ina te", "disseminate"),

    # gather ing (48 occurrences)
    ("gather ing", "gathering"),

    # reck less dis regard (48 occurrences)
    ("reck less dis regard", "reckless disregard"),
    ("reck less", "reckless"),

    # avoid ing (35 occurrences)
    ("avoid ing", "avoiding"),

    # local ism (33 occurrences)
    ("local ism", "localism"),

    # board ing (27 occurrences)
    ("board ing", "boarding"),

    # trauma tic (25 occurrences)
    ("post-trauma tic stress dis order", "post-traumatic stress disorder"),
    ("trauma tic", "traumatic"),
    ("stress dis order", "stress disorder"),
    ("dis order", "disorder"),

    # face ted (24 occurrences)
    ("multi face ted", "multifaceted"),
    ("face ted", "faceted"),

    # the ory (24 occurrences)
    ("the ory", "theory"),

    # research ers (23 occurrences)
    ("research ers", "researchers"),
    ("Research ers", "Researchers"),

    # conduct ing (16 occurrences)
    ("conduct ing", "conducting"),

    # term ina ted (13 occurrences)
    ("term ina ted", "terminated"),
    ("term ina tion", "termination"),
    ("term ina te", "terminate"),

    # personal ity (13 occurrences)
    ("personal ity", "personality"),

    # guard ian (13 occurrences)
    ("guard ian", "guardian"),

    # except ion (12 occurrences)
    ("except ion", "exception"),

    # front ier (12 occurrences)
    ("front ier", "frontier"),

    # adult ery (12 occurrences)
    ("adult ery", "adultery"),

    # protest ors (12 occurrences)
    ("protest ors", "protestors"),

    # wait ing (12 occurrences)
    ("wait ing", "waiting"),

    # side nce / are side nce (12 occurrences)
    ("are side nce", "aresidence"),  # will be caught by "residence" merge
    ("side nce", "sidence"),

    # achieve dby (12 occurrences)
    ("achieve dby", "achieved by"),

    # Respect ful (12 occurrences)
    ("Respect ful", "Respectful"),
    ("respect ful", "respectful"),

    # Dis app roving (12 occurrences)
    ("Dis app roving", "Disapproving"),
    ("dis app roving", "disapproving"),

    # effect sof (12 occurrences)
    ("effect sof", "effects of"),
    ("Effect sof", "Effects of"),

    # sentence dto (12 occurrences)
    ("sentence dto", "sentenced to"),

    # process ion (12 occurrences)
    ("process ion", "procession"),

    # hand edd own (12 occurrences)
    ("hand edd own", "handed down"),

    # people ona (12 occurrences)
    ("people ona", "people on a"),

    # statement sis (8 occurrences)
    ("statement sis", "statements is"),

    # civil ian (7 occurrences)
    ("civil ian", "civilian"),

    # cook ing (8 occurrences)
    ("Cook ing", "Cooking"),
    ("cook ing", "cooking"),

    # listen ing (11 occurrences)
    ("listen ing", "listening"),

    # allow ing (11 occurrences)
    ("allow ing", "allowing"),

    # offer ing (11 occurrences)
    ("offer ing", "offering"),

    # fail ure (10 occurrences)
    ("fail ure", "failure"),

    # scooter ist (12 occurrences)
    ("scooter ist", "scooterist"),

    # Additional space-between-words fixes
    ("setting upa", "setting up a"),
    ("kind oft", "kind of t"),
    ("system sto", "systems to"),
    ("demolishment ofa", "demolishment of a"),
    ("witness ina case", "witness in a case"),
    ("witness ina", "witness in a"),
    ("mobsterdead ina", "mobster dead in a"),
    ("either ina", "either in a"),
    ("under goa", "undergo a"),
    ("federal lym", "federally m"),

    # Collect ive (12 occurrences)
    ("Collect ive", "Collective"),
    ("collect ive", "collective"),

    # Contract ive (12 occurrences)
    ("Contract ive", "Contractive"),
    ("contract ive", "contractive"),

    # Change sin (12 occurrences)
    ("Change sin", "Changes in"),
    ("change sin", "changes in"),

    # Poll ina tors (12 occurrences)
    ("Poll ina tors", "Pollinators"),
    ("poll ina tors", "pollinators"),
    ("poll ina tion", "pollination"),

    # Problem sof (12 occurrences)
    ("Problem sof", "Problems of"),
    ("problem sof", "problems of"),

    # Beat ing Back (12 occurrences)
    ("Beat ing", "Beating"),
    ("beat ing", "beating"),

    # Carry ing out (12 occurrences)
    ("Carry ing", "Carrying"),

    # Declining (already good)

    # cap size (water police files)
    ("cap size", "capsize"),

    # str ucturalcollapses
    ("str uctural", "structural"),
    ("str ucture", "structure"),
    ("str eets", "streets"),
    ("str engt", "strengt"),

    # for mid able
    ("for mid able", "formidable"),

    # reflect ion (Chinese context versions will be skipped)
    # Only fix when clearly in English context

    # ob scene
    ("ob scene", "obscene"),

    # step ping
    ("step ping", "stepping"),

    # age ncies (multiple contexts)
    ("age ncies", "agencies"),

    # into xicating / bever age
    ("into xicating bever age", "intoxicating beverage"),
    ("into xicating", "intoxicating"),
    ("bever age", "beverage"),

    # Pain ful
    ("pain ful", "painful"),

    # vacc ina ted
    ("vacc ina ted", "vaccinated"),
    ("vacc ina tion", "vaccination"),
    ("vacc ina te", "vaccinate"),

    # near est
    ("near est", "nearest"),

    # tem per atur
    ("tem per atur", "temperatur"),
    ("tem per ature", "temperature"),

    # recon str uct
    ("recon str uct", "reconstruct"),

    # emp has izes
    ("emp has izes", "emphasizes"),
    ("emp has ize", "emphasize"),
    ("emp has is", "emphasis"),

    # admini str ative
    ("admini str ative", "administrative"),
    ("admini str ation", "administration"),

    # clo thing
    ("clo thing", "clothing"),

    # form er
    ("a for mof", "a form of"),

    # con fined
    ("con fined", "confined"),
    ("con fine dto", "confined to"),
    ("con fine d", "confined"),
    ("con front", "confront"),
    ("con tend", "contend"),
    ("con test", "contest"),

    # affect ive
    ("Affect ive Dis orde", "Affective Disorde"),
    ("affect ive", "affective"),

    # Poi son ing
    ("Poi son ing", "Poisoning"),
    ("poi son ing", "poisoning"),
    ("poi son", "poison"),

    # deep-sea ted
    ("deep-sea ted", "deep-seated"),

    # Vulnerabi lity
    ("Vulnerabi lity", "Vulnerability"),
    ("vulnerabi lity", "vulnerability"),
    ("Vuln erab", "Vulnerab"),

    # acc ident
    ("acc ident", "accident"),

    # ach ieve
    ("ach ieve ment", "achievement"),

    # thou sand
    ("thousand sof", "thousands of"),

    # aware ness / aware n
    ("aware ness", "awareness"),
    ("aware n", "awaren"),

    # de part ment
    ("de part ment", "department"),

    # acrashed
    ("acrashed", "a crashed"),

    # tend sto
    ("tend sto", "tends to"),

    # lications (partial from "applications")
    ("app lication", "application"),

    # ofc once ntrating
    ("ofc once ntrating", "of concentrating"),
    ("ofc once ntra", "of concentra"),
    ("once ntra", "concentra"),

    # bin ing -> combining already handled
    # but standalone:
    ("bin ing", "bining"),

    # char act er
    ("char act er", "character"),

    # att ract
    ("attr act i onto", "attraction to"),
    ("attr act ion", "attraction"),
    ("attr act", "attract"),

    # radio active was tes
    ("radio active was tes", "radioactive wastes"),
    ("radio active", "radioactive"),

    # Mass achusetts
    ("Mass achusetts", "Massachusetts"),

    # Thail and
    ("Thail and", "Thailand"),

    # dis tort ing
    ("dis tort ing", "distorting"),
    ("dis tort", "distort"),

    # tort ing already handled via distorting

    # act ing -> keep this conservative, "acting" is common but "act ing" could be legitimate
    # Only fix specific known patterns
    ("extr act ing", "extracting"),
    ("attr act ing", "attracting"),
    ("contr act ing", "contracting"),

    # ac counts -> accounts (when preceded by card)
    # already handled in car dac counts

    # ampheta mine
    ("mph etamine", "mphetamine"),

    # ob scene images
    ("ob scene images", "obscene images"),

    # fit ting
    ("fit ting", "fitting"),

    # Taiwa nese
    ("Taiwa nese", "Taiwanese"),

    # speci fic / specif ically
    ("speci fic", "specific"),
    ("specif ically", "specifically"),

    # hist ory
    ("hist ory", "history"),

    # Remaining edge cases found in final verification
    ("Art ificials election", "Artificial selection"),
    ("Art ificial s election", "Artificial selection"),
    ("com pass ion", "compassion"),
    ("com pass ionate", "compassionate"),
    ("reach ing the sea shore", "reaching the seashore"),
    ("reach ing", "reaching"),
    ("sea shore", "seashore"),

    # === Additional patterns found in final scan ===

    # sit uations (60 occurrences)
    ("unpleasant sit uations", "unpleasant situations"),
    ("sit uation", "situation"),

    # chemis try (56 occurrences)
    ("chemis try", "chemistry"),

    # photogramme try (55 occurrences)
    ("photogramme try", "photogrammetry"),

    # AIcom pan ionc hat bots (55 occurrences)
    ("AIcom pan ionc hat bots", "AI companion chatbots"),
    ("AIcom pan ion", "AI companion"),
    ("com pan ion", "companion"),
    ("com pan ionc hat", "companion chat"),
    ("com pan y", "company"),
    ("ionc hat bots", "ion chatbots"),

    # light add resses (48 occurrences)
    ("light add resses", "light addresses"),
    ("add resses", "addresses"),
    ("add ress", "address"),

    # police men (33 occurrences)
    ("police men", "policemen"),
    ("country men", "countrymen"),

    # never str ictly (33 occurrences)
    ("never str ictly", "never strictly"),
    ("str ictly", "strictly"),

    # can man ifest (24 occurrences)
    ("can man ifest", "can manifest"),
    ("man ifest", "manifest"),

    # alter ms (24 occurrences)
    ("alter ms", "alter ms"),  # This might be "alarms" context - skip for now

    # univer sit ies (16 occurrences)
    ("univer sit ies", "universities"),
    ("univer sit y", "university"),

    # ange red / end ange red (13 occurrences)
    ("end ange red", "endangered"),
    ("ange red", "angered"),

    # infer red (13 occurrences)
    ("infer red", "inferred"),

    # exe cut ion (12 occurrences)
    ("exe cut ion", "execution"),
    ("exe cut ive", "executive"),
    ("exe cut e", "execute"),

    # oflottery win ners (12 occurrences)
    ("oflottery win ners", "of lottery winners"),
    ("win ners", "winners"),
    ("oflottery", "of lottery"),

    # camoufl age (12 occurrences)
    ("camoufl age", "camouflage"),

    # tap eof (12 occurrences)
    ("tap eof", "tape of"),

    # ingunpleasant (12 occurrences)
    ("fix ingunpleasant", "fixing unpleasant"),
    ("ingunpleasant", "ing unpleasant"),

    # List ing (12 occurrences)
    ("List ing", "Listing"),
    ("list ing", "listing"),

    # live sto rescue individual sand
    ("live sto rescue", "lives to rescue"),
    ("individual sand", "individuals and"),
    ("Fore most", "Foremost"),
    ("fore most", "foremost"),

    # fish ers (water police)
    ("fish ers", "fishers"),
    ("fish ermen", "fishermen"),
    ("fish eries", "fisheries"),

    # Taiwan ese (various water police)
    ("Taiwan ese", "Taiwanese"),

    # rock yheadlands
    ("rock yheadlands", "rocky headlands"),
    ("rock y", "rocky"),

    # hand gun
    ("hand gun", "handgun"),

    # solving kit
    ("solving kit", "solving kit"),  # This is actually correct already

    # protect ing (still appearing)
    ("Protect ing", "Protecting"),

    # More merged-word fixes (no space between words)
    ("theuni formed", "the uniformed"),
    ("thein str uctor", "the instructor"),
    ("str uctor", "structor"),
]

# ============================================================================
# GENERIC PATTERN-BASED FIXES
# ============================================================================

def contains_chinese(text):
    """Check if text contains any Chinese characters."""
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            return True
    return False


def is_english_segment(text):
    """Check if a text segment is primarily English (letters, spaces, punctuation)."""
    if not text:
        return False
    english_chars = sum(1 for c in text if c.isascii())
    return english_chars / len(text) > 0.7


def extract_english_segments(text):
    """Extract English segments from mixed Chinese-English text.
    Returns list of (start, end, segment) tuples."""
    segments = []
    # Match sequences of ASCII characters (English text with spaces/punctuation)
    pattern = re.compile(r'[A-Za-z][A-Za-z\s,.\'"!?;:\-_/()0-9]+[A-Za-z.,!?;:\'")\d]|[A-Za-z]{2,}')
    for m in pattern.finditer(text):
        seg = m.group()
        if len(seg) >= 3:  # Only consider segments of 3+ chars
            segments.append((m.start(), m.end(), seg))
    return segments


# Known English words for merged-word splitting.
# This is a comprehensive set used to validate that splitting a merged token
# produces real English words on both sides.
_SPLIT_DICT = None

def _get_split_dict():
    """Lazy-load the dictionary for merged word splitting."""
    global _SPLIT_DICT
    if _SPLIT_DICT is not None:
        return _SPLIT_DICT

    # Common English words that could be the "prefix" part of a merge
    prefixes = {
        'a', 'an', 'the', 'of', 'in', 'to', 'for', 'on', 'at', 'by',
        'or', 'and', 'is', 'as', 'be', 'we', 'he', 'it', 'no', 'if',
        'so', 'do', 'up', 'not', 'but', 'can', 'may', 'has', 'had',
        'was', 'are', 'were', 'his', 'her', 'our', 'its', 'who', 'how',
        'all', 'any', 'new', 'own', 'too', 'now', 'few', 'did', 'let',
        'yet', 'nor', 'got', 'per', 'she', 'you', 'they', 'this',
        'that', 'with', 'from', 'have', 'will', 'been', 'into', 'over',
        'back', 'down', 'just', 'also', 'more', 'most', 'some', 'such',
        'very', 'only', 'even', 'both', 'here', 'what', 'when', 'your',
        'them', 'than', 'then', 'much', 'each', 'many',
        'these', 'those', 'their', 'there', 'which', 'while', 'about',
        'would', 'could', 'should', 'being', 'where', 'after', 'other',
        'between', 'before', 'alone', 'still',
    }

    # Common English words that could be the "suffix" part of a merge
    suffixes = {
        'the', 'a', 'an', 'of', 'in', 'to', 'for', 'on', 'at', 'by',
        'or', 'and', 'is', 'as', 'be', 'it', 'no', 'if', 'so', 'do',
        'up', 'not', 'but', 'can', 'may', 'his', 'her', 'our', 'its',
        'all', 'any', 'new', 'own', 'too', 'now', 'out',
        'their', 'them', 'they', 'this', 'that', 'these', 'those',
        'jobs', 'human', 'data', 'root', 'iris', 'built',
        'each', 'some', 'such', 'very', 'also', 'only', 'just', 'even',
        'both', 'here', 'been', 'from', 'have', 'will', 'with',
        'into', 'over', 'back', 'down', 'more', 'most', 'many', 'much',
        'what', 'when', 'your', 'them', 'than', 'then', 'where',
        'about', 'would', 'could', 'should', 'being', 'while',
        'other', 'between', 'before', 'after', 'which',
    }

    _SPLIT_DICT = (prefixes, suffixes)
    return _SPLIT_DICT


# Known merged-word tokens and their corrections.
# These are tokens that appear as standalone "words" but are actually
# two words merged together due to OCR missing the space.
MERGED_WORD_MAP = {
    # of + word
    'ofthe': 'of the', 'ofthis': 'of this', 'ofthat': 'of that',
    'oftheir': 'of their', 'ofthese': 'of these', 'ofthose': 'of those',
    'ofjobs': 'of jobs', 'ofhuman': 'of human', 'ofdata': 'of data',
    'ofthem': 'of them',
    # in + word
    'inthe': 'in the', 'inthis': 'in this', 'inthat': 'in that',
    'intheir': 'in their', 'intheUK': 'in the UK', 'intheUS': 'in the US',
    'ina': 'in a',
    # to + word
    'tothe': 'to the', 'totheir': 'to their', 'tothis': 'to this',
    'toroot': 'to root', 'tobe': 'to be',
    # for + word
    'forthe': 'for the', 'forthis': 'for this',
    # on + word
    'onthe': 'on the',
    # at + word
    'atthe': 'at the',
    # by + word
    'bythe': 'by the',
    # and + word
    'andthe': 'and the', 'andiris': 'and iris', 'andso': 'and so',
    # from + word
    'fromthe': 'from the',
    # with + word
    'withthe': 'with the',
    # is + word
    'isthe': 'is the', 'isto': 'is to', 'isbiometric': 'is biometric',
    # be + word
    'bebuilt': 'be built',
    # as + word
    'asbiometric': 'as biometric', 'asbiometricidentifiers': 'as biometric identifiers',
    # we + word
    'wemayas': 'we may as',
    # she + word
    'shewas': 'she was',
    # he + word
    'heor': 'he or',
    # do + word
    'dowe': 'do we',
    # alone + word
    'alonein': 'alone in',
    # other compound merges
    'canbe': 'can be',
    'youpost': 'you post', 'youhave': 'you have',
    'giveme': 'give me',
    'orelse': 'or else',
    'waythat': 'way that',
    'onethat': 'one that',
    'thesame': 'the same',
    'nowon': 'now on',
    'theway': 'the way',
    'thefact': 'the fact',
    'thebest': 'the best',
    'fondof': 'fond of',
    'aperson': 'a person',
    'alocal': 'a local',
    'acommon': 'a common',
    'afine': 'a fine',
    'abonus': 'a bonus',
    'abait': 'a bait',
    'suchas': 'such as',
    'usedto': 'used to',
    'ledto': 'led to',
    'inafine': 'in a fine',
    'acrashed': 'a crashed',
    'asearch': 'a search',
    'aperson': 'a person',
    'herwith': 'her with',
    'becreated': 'be created',
    'itcrosses': 'it crosses',
    'clickingon': 'clicking on',
    'phishinglinks': 'phishing links',
    'settingupa': 'setting up a',
    'toevolve': 'to evolve',
    'togrant': 'to grant',
    'tosteal': 'to steal',
    'tosniff': 'to sniff',
    'tosteal': 'to steal',
    'aitools': 'AI tools',
    'withai': 'with AI',
    'aiis': 'AI is',
    'effectivebiometric': 'effective biometric',
    'biometricmarker': 'biometric marker',
    'theword': 'the word',
    'likelihoodof': 'likelihood of',
    'byauthorities': 'by authorities',
    'Johnis': 'John is',
    'integrationschemes': 'integration schemes',
    'Aslon': 'As lon',
}


def fix_merged_words(text):
    """Fix merged words (missing spaces between words) in text.

    Finds standalone tokens that are not real English words and splits them
    if they match known merged-word patterns.
    """
    if not text:
        return text

    def replace_token(match):
        token = match.group(0)
        # Check exact match in our known merged word map
        if token in MERGED_WORD_MAP:
            return MERGED_WORD_MAP[token]
        # Check lowercase version
        if token.lower() in MERGED_WORD_MAP:
            return MERGED_WORD_MAP[token.lower()]
        return token

    # Process each English word token in the text
    # We use word boundaries to match standalone tokens
    result = re.sub(r'\b[a-zA-Z]{4,}\b', replace_token, text)

    return result


def fix_text_with_explicit_patterns(text):
    """Apply explicit pattern fixes to text."""
    if not text:
        return text, False

    original = text

    for wrong, right in EXPLICIT_FIXES:
        if wrong in text:
            text = text.replace(wrong, right)

    # Split merged words (missing spaces) using word-boundary-aware approach.
    # Find tokens that are not real English words and try splitting them
    # into known word combinations.
    text = fix_merged_words(text)

    return text, text != original


def fix_generic_ocr_spaces(text, dictionary):
    """Fix remaining OCR space artifacts using dictionary lookup.

    Strategy:
    1. Find sequences of short fragments separated by single spaces
       that could form valid English words when merged
    2. Only merge if the result is in the dictionary
    3. Be conservative - require fragments to look like word parts
    """
    if not text:
        return text, False

    original = text

    # Pattern: find sequences like "word frag ment" where fragments are short
    # and merging adjacent ones creates dictionary words
    # We process English segments only

    # First pass: fix space-within-word patterns
    # Look for: lowercase_letters + space + lowercase_letters where merged = dictionary word
    # Only when at least one fragment is short (1-4 chars), suggesting OCR artifact

    def try_merge_fragments(match_text):
        """Try to merge space-separated fragments into dictionary words."""
        words = match_text.split(' ')
        if len(words) < 2:
            return match_text

        result = []
        i = 0
        while i < len(words):
            if i < len(words) - 1:
                # Try merging current word with next 1, 2, or 3 words
                merged = False
                for span in range(min(4, len(words) - i), 1, -1):
                    candidate = ''.join(words[i:i+span])
                    candidate_lower = candidate.lower()

                    # Check if any fragment in the span is suspiciously short (1-4 chars)
                    fragments = words[i:i+span]
                    has_short_fragment = any(len(f) <= 4 for f in fragments)

                    # Check: are all fragments real standalone English words?
                    # If so, do NOT merge them - they are separate words, not OCR fragments.
                    # A real OCR fragment would NOT be a common English word.
                    common_short_words = {
                        'a', 'i', 'an', 'am', 'as', 'at', 'be', 'by', 'do', 'go',
                        'he', 'if', 'in', 'is', 'it', 'me', 'my', 'no', 'of', 'ok',
                        'on', 'or', 'so', 'to', 'up', 'us', 'we',
                        'add', 'age', 'ago', 'aid', 'aim', 'air', 'all', 'and', 'any',
                        'are', 'arm', 'art', 'ask', 'ate', 'bad', 'bag', 'ban', 'bar',
                        'bat', 'bed', 'big', 'bit', 'box', 'boy', 'bus', 'but', 'buy',
                        'can', 'cap', 'car', 'cat', 'cow', 'cup', 'cut', 'day', 'did',
                        'die', 'dig', 'dog', 'dry', 'due', 'ear', 'eat', 'egg', 'end',
                        'era', 'etc', 'eve', 'eye', 'fan', 'far', 'fat', 'fed', 'few',
                        'fit', 'fix', 'fly', 'for', 'fox', 'fun', 'gap', 'gas', 'get',
                        'god', 'got', 'gun', 'gut', 'guy', 'gym', 'had', 'has', 'hat',
                        'her', 'hid', 'him', 'his', 'hit', 'hot', 'how', 'ice', 'ill',
                        'its', 'jam', 'jar', 'jaw', 'jet', 'job', 'joy', 'key', 'kid',
                        'kit', 'lab', 'lap', 'law', 'lay', 'led', 'leg', 'let', 'lie',
                        'lip', 'log', 'lot', 'low', 'mad', 'man', 'map', 'may', 'men',
                        'met', 'mix', 'mom', 'mud', 'net', 'new', 'nor', 'not', 'now',
                        'nut', 'odd', 'off', 'oil', 'old', 'one', 'our', 'out', 'owe',
                        'own', 'pan', 'pay', 'per', 'pet', 'pie', 'pin', 'pit', 'pop',
                        'pot', 'pre', 'pro', 'pub', 'put', 'ran', 'raw', 'red', 'rid',
                        'rob', 'rod', 'row', 'run', 'sad', 'sat', 'saw', 'say', 'sea',
                        'set', 'she', 'sir', 'sit', 'six', 'ski', 'sky', 'son', 'spy',
                        'sub', 'sum', 'sun', 'tax', 'tea', 'ten', 'the', 'tie', 'tip',
                        'toe', 'too', 'top', 'toy', 'try', 'two', 'use', 'van', 'via',
                        'war', 'was', 'way', 'web', 'wet', 'who', 'why', 'win', 'wit',
                        'won', 'yet', 'you', 'zoo', 'act', 'dna', 'may',
                    }
                    # If any fragment is a common standalone word, skip this merge
                    any_fragment_is_real_word = any(
                        f.lower() in common_short_words or
                        (f.lower() in dictionary and len(f) >= 3)
                        for f in fragments
                    )

                    if (has_short_fragment and
                        not any_fragment_is_real_word and
                        candidate_lower in dictionary and
                        len(candidate_lower) >= 5):  # Only merge if result is 5+ chars

                        # Preserve original capitalization
                        result.append(candidate)
                        i += span
                        merged = True
                        break

                if not merged:
                    result.append(words[i])
                    i += 1
            else:
                result.append(words[i])
                i += 1

        return ' '.join(result)

    # Apply to English segments within the text
    # Split text by Chinese characters and process English parts
    parts = re.split(r'([\u4e00-\u9fff\u3400-\u4dbf]+)', text)
    new_parts = []
    for part in parts:
        if contains_chinese(part):
            new_parts.append(part)
        else:
            new_parts.append(try_merge_fragments(part))

    text = ''.join(new_parts)

    # Second pass: fix missing spaces between words (merged words)
    # Look for patterns like "lowercase}Uppercase" which suggest missing space
    # e.g., "toTSMC" -> already handled by explicit patterns
    # Also: "word1word2" where both are in dictionary
    # This is harder and more error-prone, so we only handle clear cases

    # Fix camelCase-like patterns where a lowercase letter is followed by uppercase
    # in the middle of what should be separate words
    # e.g., "clickingon" -> "clicking on" (but NOT "iPhone")
    # We handle this conservatively

    return text, text != original


def fix_space_before_punctuation(text):
    """Fix spaces incorrectly placed before punctuation marks."""
    if not text:
        return text, False
    original = text
    # Remove space before period, comma, semicolon, colon at end of English word
    text = re.sub(r'([a-zA-Z]) ([.,;:])', r'\1\2', text)
    return text, text != original


# ============================================================================
# MAIN PROCESSING
# ============================================================================

def process_text_field(text, dictionary, changes_log, file_path, field_name, question_num):
    """Process a single text field and return fixed text."""
    if not text or not isinstance(text, str):
        return text, False

    # Skip if no English content
    if not re.search(r'[a-zA-Z]{2,}', text):
        return text, False

    original = text

    # Step 1: Apply explicit pattern fixes
    text, changed1 = fix_text_with_explicit_patterns(text)

    # Step 2: Apply generic dictionary-based fixes
    text, changed2 = fix_generic_ocr_spaces(text, dictionary)

    if text != original:
        changes_log.append({
            "file": file_path,
            "field": field_name,
            "question": question_num,
            "before": original,
            "after": text,
        })
        return text, True

    return text, False


def process_file(filepath, dictionary, changes_log):
    """Process a single JSON file and fix OCR artifacts in English text."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"  ERROR: Cannot parse {filepath}: {e}")
        return 0

    # Handle non-dict JSON files (e.g., list format)
    if not isinstance(data, dict):
        return 0

    fix_count = 0
    questions = data.get('questions', [])

    for q in questions:
        qnum = q.get('number', '?')

        # Fix passage
        if 'passage' in q and q['passage']:
            new_text, changed = process_text_field(
                q['passage'], dictionary, changes_log, filepath, 'passage', qnum
            )
            if changed:
                q['passage'] = new_text
                fix_count += 1

        # Fix stem
        if 'stem' in q and q['stem']:
            new_text, changed = process_text_field(
                q['stem'], dictionary, changes_log, filepath, 'stem', qnum
            )
            if changed:
                q['stem'] = new_text
                fix_count += 1

        # Fix options
        if 'options' in q and isinstance(q['options'], dict):
            for key, val in q['options'].items():
                if val and isinstance(val, str):
                    new_text, changed = process_text_field(
                        val, dictionary, changes_log, filepath, f'option_{key}', qnum
                    )
                    if changed:
                        q['options'][key] = new_text
                        fix_count += 1

    # Write back if modified
    if fix_count > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return fix_count


def main():
    print("=" * 70)
    print("Fix OCR English Artifacts in Police Exam JSON Files")
    print("=" * 70)

    # Build dictionary
    print("\nBuilding English dictionary...")
    dictionary = build_dictionary()
    print(f"  Dictionary size: {len(dictionary)} words")

    # Find all JSON files
    json_files = []
    for root, dirs, files in os.walk(BASE_DIR):
        for fname in files:
            if fname.endswith('.json') and fname != 'download_summary.json':
                json_files.append(os.path.join(root, fname))

    print(f"  Found {len(json_files)} JSON files to scan")

    # Process files
    changes_log = []
    total_fixes = 0
    files_modified = 0

    for filepath in sorted(json_files):
        fix_count = process_file(filepath, dictionary, changes_log)
        if fix_count > 0:
            rel_path = os.path.relpath(filepath, BASE_DIR)
            print(f"  Fixed {fix_count} field(s) in: {rel_path}")
            total_fixes += fix_count
            files_modified += 1

    # Write log
    print(f"\n{'=' * 70}")
    print(f"Results:")
    print(f"  Files scanned:  {len(json_files)}")
    print(f"  Files modified: {files_modified}")
    print(f"  Total fields fixed: {total_fixes}")
    print(f"  Total individual changes: {len(changes_log)}")

    # Write detailed log
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        f.write(f"OCR English Fix Log\n")
        f.write(f"{'=' * 70}\n")
        f.write(f"Files scanned:  {len(json_files)}\n")
        f.write(f"Files modified: {files_modified}\n")
        f.write(f"Total fields fixed: {total_fixes}\n\n")

        for i, change in enumerate(changes_log, 1):
            f.write(f"--- Change #{i} ---\n")
            f.write(f"File: {change['file']}\n")
            f.write(f"Question: {change['question']}, Field: {change['field']}\n")
            f.write(f"BEFORE: {change['before'][:200]}...\n" if len(change['before']) > 200 else f"BEFORE: {change['before']}\n")
            f.write(f"AFTER:  {change['after'][:200]}...\n\n" if len(change['after']) > 200 else f"AFTER:  {change['after']}\n\n")

    print(f"\nDetailed log saved to: {LOG_FILE}")

    return total_fixes


if __name__ == '__main__':
    total = main()
    print(f"\nDone. Total fixes: {total}")
