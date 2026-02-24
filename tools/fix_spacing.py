#!/usr/bin/env python3
"""Fix PDF parsing spacing issues in recovered English reading comprehension questions."""

import json
import re
import glob


# Known compound words that need splitting
KNOWN_FIXES = {
    "childpornography": "child pornography",
    "bordersecurity": "border security",
    "emergencymanagement": "emergency management",
    "crimescene": "crime scene",
    "domesticabuse": "domestic abuse",
    "restorativejustice": "restorative justice",
    "uniformedpresence": "uniformed presence",
    "excessiveenforcement": "excessive enforcement",
    "cyberterrorism": "cyberterrorism",  # already correct
    "internetfraud": "internet fraud",
    "emailhacking": "email hacking",
    "secretservice": "secret service",
    "drugtrafficking": "drug trafficking",
    "armedrobbery": "armed robbery",
    "domesticviolence": "domestic violence",
    "Humantrafficking": "Human trafficking",
    "nofewerthan": "no fewer than",
    "nomorethan": "no more than",
    "nosoonerthan": "no sooner than",
    "nolaterthan": "no later than",
    "filteredout": "filtered out",
    "referredto": "referred to",
    "indulgedin": "indulged in",
    "ledto": "led to",
    "wasdeprivedof": "was deprived of",
    "wasclearedof": "was cleared of",
    "wascomposedof": "was composed of",
    "wastrespassedon": "was trespassed on",
    "indetention": "in detention",
    "forthemotion": "for the motion",
    "inresponse": "in response",
    "inthiscase": "in this case",
    "wasfound": "was found",
    "socialreintegrationschemes": "social reintegration schemes",
    "riskmanagementtools": "risk management tools",
    "communitycorrections": "community corrections",
    "drugtreatmentprograms": "drug treatment programs",
    "forensicengineering": "forensic engineering",
    "informationmanagement": "information management",
    "copyrightinfringement": "copyright infringement",
    "restrainingorder": "restraining order",
    "policecruiser": "police cruiser",
    "handgunholster": "handgun holster",
    "camouflageuniform": "camouflage uniform",
    "mobileinformation": "mobile information",
    "approachingto": "approaching to",
    "deprivingof": "depriving of",
    "fleeingfrom": "fleeing from",
    "returningto": "returning to",
    "dugup": "dug up",
    "raisedup": "raised up",
    "takenup": "taken up",
    "caughtup": "caught up",
    "atatimeof": "at a time of",
    "intheextentof": "in the extent of",
    "intheperiodof": "in the period of",
    "atanint": "at an int",
    "thepurposeofthis": "the purpose of this",
    "thepronoun": "the pronoun",
    "inthelast": "in the last",
    "sentenceofthefir": "sentence of the fir",
}


def fix_text(text):
    """Apply comprehensive spacing fixes to text."""
    if not text:
        return text

    # Apply known compound word fixes
    for wrong, right in KNOWN_FIXES.items():
        text = text.replace(wrong, right)

    # Fix camelCase (lowercase followed by uppercase)
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)

    # Fix missing space after periods (but not abbreviations like Mr. Mrs. Dr.)
    text = re.sub(r'(?<![A-Z])\.([A-Z])', r'. \1', text)

    # Fix missing space after commas
    text = re.sub(r',([A-Za-z])', r', \1', text)

    # Fix missing space after colons (but not in time like 10:30)
    text = re.sub(r':([A-Z])', r': \1', text)

    # Fix missing space after semicolons
    text = re.sub(r';([A-Za-z])', r'; \1', text)

    # Fix missing space after closing quotes
    text = re.sub(r'"([A-Za-z])', r'" \1', text)

    # Fix "- -" artifacts
    text = text.replace(" - -", "")
    text = text.replace("- -", "")

    # Fix multiple spaces
    text = re.sub(r'  +', ' ', text)

    # Fix common specific patterns from these exams
    text = text.replace("frequencyof", "frequency of")
    text = text.replace("ofanation", "of a nation")
    text = text.replace("economicandtechnological", "economic and technological")
    text = text.replace("Agencyhasutilizedinformationtechnologysuchas",
                       "Agency has utilized information technology such as")
    text = text.replace("territoryand", "territory and")
    text = text.replace("havebeen", "have been")
    text = text.replace("moneyfrom", "money from")
    text = text.replace("threateningtorevealtothepressvideo",
                       "threatening to reveal to the press video")
    text = text.replace("tapeofhis", "tape of his")
    text = text.replace("theyhavebeenstronglycriticizedas",
                       "they have been strongly criticized as")
    text = text.replace("mymoneyback", "my money back")
    text = text.replace("Youshould", "You should")
    text = text.replace("thinkbefore", "think before")
    text = text.replace("youpost", "you post")
    text = text.replace("anymessage", "any message")
    text = text.replace("youdothroughthe", "you do through the")
    text = text.replace("Iwillcontactour", "I will contact our")
    text = text.replace("Netsafeunittohelpdealwiththiscaseaboutthe",
                       "Netsafe unit to help deal with this case about the")
    text = text.replace("Internetscam", "Internet scam")
    text = text.replace("Tellmeexactly", "Tell me exactly")
    text = text.replace("youconsider", "you consider")
    text = text.replace("yourselfavictim", "yourself a victim")
    text = text.replace("ofcyberbullying", "of cyberbullying")
    text = text.replace("pleasedial", "please dial")
    text = text.replace("immediatelyourhotlineforhelp",
                       "immediately our hotline for help")
    text = text.replace("anyobscene", "any obscene")
    text = text.replace("ofcybercrimes", "of cybercrimes")
    text = text.replace("students'behaviors", "students' behaviors")
    text = text.replace("misintepretation", "misinterpretation")

    # Q58 109年 fixes
    text = text.replace("Thegangsters", "The gangsters")

    # Q59 109年 fixes
    text = text.replace("theyhave beenstronglycriticizedas",
                       "they have been strongly criticized as")
    text = text.replace("theyhavebeenstronglycriticizedas",
                       "they have been strongly criticized as")
    text = text.replace("beenstronglycriticizedas",
                       "been strongly criticized as")

    # 111年 passage fixes
    text = text.replace("indifferentways", "in different ways")
    text = text.replace("Generallyspeaking", "Generally speaking")
    text = text.replace("terroristgroupsandorganizedcrimegroups",
                       "terrorist groups and organized crime groups")
    text = text.replace("OCGsontheotherhandtypicallyengageinsecretoperationssoastoobtainafinancial",
                       "OCGs on the other hand typically engage in secret operations so as to obtain a financial")
    text = text.replace("orothermaterialbenefit", "or other material benefit")
    text = text.replace("whileavoidingdetectionby", "while avoiding detection by")
    text = text.replace("lawenforcementauthorities", "law enforcement authorities")
    text = text.replace("Ratherthanaimingtoeffectpoliticalchange",
                       "Rather than aiming to effect political change")
    text = text.replace("thedisruptiontheyseektoimposeonterritoriesunder",
                       "the disruption they seek to impose on territories under")
    text = text.replace("Stateauthority", "State authority")
    text = text.replace("ismeant", "is meant")
    text = text.replace("toperpetuateconditions", "to perpetuate conditions")
    text = text.replace("thatarebeneficialtotheir", "that are beneficial to their")
    text = text.replace("Inpracticalterms", "In practical terms")
    text = text.replace("thelinkagesbetweenterrorismandorganizedcrimebecomeapparentmostnotably",
                       "the linkages between terrorism and organized crime become apparent most notably")
    text = text.replace("inthefinancingofterrorism", "in the financing of terrorism")
    text = text.replace("Inothercases", "In other cases")
    text = text.replace("theselinkagesmayinvolve", "these linkages may involve")
    text = text.replace("thesmugglingofmigrants", "the smuggling of migrants")
    text = text.replace("andillicitarms", "and illicit arms")
    text = text.replace("traffickinginvolvingsmallarms",
                       "trafficking involving small arms")
    text = text.replace("lightweaponsandothermilitaryequipment",
                       "light weapons and other military equipment")
    text = text.replace("cartheft", "car theft")
    text = text.replace("illicitmineralextraction", "illicit mineral extraction")
    text = text.replace("kidnappingforransom", "kidnapping for ransom")
    text = text.replace("drugtrafficking", "drug trafficking")
    text = text.replace("traffickinginother", "trafficking in other")
    text = text.replace("illicitgoods", "illicit goods")
    text = text.replace("Instancesinvolving", "Instances involving")
    text = text.replace("OCGsfacilitatingthetransportofterroristsacrossbordersactivities",
                       "OCGs facilitating the transport of terrorists across borders activities")
    text = text.replace("alsorepresentpossiblescenarioswherethesetwophenomenabecomeintertwined",
                       "also represent possible scenarios where these two phenomena become intertwined")

    # 111年 specific fixes
    text = text.replace("thepurposeofthis passage",
                       "the purpose of this passage")
    text = text.replace('thepronoun"they"referto',
                       'the pronoun "they" refer to')
    text = text.replace("inthelast sentenceofthefirst",
                       "in the last sentence of the first")
    text = text.replace("sentenceofthefir", "sentence of the fir")
    text = text.replace('"Ratherthanaimingtoeffectpoliticalchange,thedisruptiontheyseektoimposeonterritoriesunder',
                       '"Rather than aiming to effect political change, the disruption they seek to impose on territories under')
    text = text.replace("Stateauthorityis", "State authority is")
    text = text.replace("toperpetuate", "to perpetuate")
    text = text.replace("arebeneficial", "are beneficial")
    text = text.replace("totheir", "to their")
    text = text.replace("theterrorist", "the terrorist")
    text = text.replace("theorganizedcrime", "the organized crime")
    text = text.replace("smugglingactivities", "smuggling activities")
    text = text.replace("illicitgoods", "illicit goods")

    # NOTE: Do NOT use generic word-boundary heuristics here.
    # A previous attempt to split on common prepositions broke valid words
    # like "attention" -> "attenti on", "This" -> "Th is", etc.

    # Fix double spaces again
    text = re.sub(r'  +', ' ', text)

    return text.strip()


def main():
    # Find all English exam files
    modified = 0
    for filepath in sorted(glob.glob("考古題庫/**/試題.json", recursive=True)):
        if "英文" not in filepath:
            continue

        with open(filepath) as f:
            data = json.load(f)

        changed = False
        for q in data["questions"]:
            if q.get("type") != "choice":
                continue

            # Fix stem
            old_stem = q.get("stem", "")
            new_stem = fix_text(old_stem)
            if new_stem != old_stem:
                q["stem"] = new_stem
                changed = True

            # Fix options
            for key in list(q.get("options", {}).keys()):
                old_opt = q["options"][key]
                new_opt = fix_text(old_opt)
                if new_opt != old_opt:
                    q["options"][key] = new_opt
                    changed = True

            # Fix passage
            old_passage = q.get("passage", "")
            if old_passage:
                new_passage = fix_text(old_passage)
                if new_passage != old_passage:
                    q["passage"] = new_passage
                    changed = True

        if changed:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            modified += 1

    print(f"Fixed spacing in {modified} files")


if __name__ == "__main__":
    main()
