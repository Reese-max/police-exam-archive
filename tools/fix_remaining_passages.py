#!/usr/bin/env python3
"""Fix remaining garbled passages from comprehensive scan."""

import json
import os

BASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "考古題庫")
fixes_applied = 0


def fix_file(relpath, fix_fn):
    global fixes_applied
    fpath = os.path.join(BASE, relpath)
    with open(fpath, "r") as f:
        data = json.load(f)
    count = fix_fn(data)
    if count > 0:
        with open(fpath, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        fixes_applied += count
        print(f"  Fixed {count} issues in {relpath}")


# ── Water police 110 Q56-60 passage ──────────────────────────────────────

WATER_110_OLD_PASSAGE = (
    "請依下文回答第56題至第60題: Members of jury have found former Minneapolis "
    "police officer guilty for the death of an African American,George Floyd. "
    "Floyd die don May 25,2020 after the police officer held his knee against "
    "Floyd's neck or upper body for nearly nine minutes. This police officer "
    "was accused of third-degree murder and second-degree mans laugh ter. This "
    "trial is probably one of the most close lywatched trial sin recent decades, "
    "because it involves a law enforcement officer; and Floyd's death under the "
    "knee of this officer has reverberated around the world. Although, the jury "
    "members have announced that this police officer is guilty in all charges, "
    "this unfortunate incident and Floyd'slast words—I can not brea the—have "
    "been deeply ing rain edin them inds of American and have in cited numerous "
    "marches, and protests across the country. Respond ing to the result of "
    "this trial, former US president, Barack Obama, asked this thought- "
    "provoking question: \"Would justice be done\" after we learned about the "
    "verdict of this trail? While this verdict may have some what uplifted the "
    "minds of Floyd's family and is a necessary step on the road to justice, "
    "itis far from a sufficient one. According to Obama, true justice is "
    "\"about much more than a single verdict ina single trial.\" Obama argues "
    "that we can not over ride what has happened, but it's important for all "
    "citizen sto recognize that million sof people of color live in fear that "
    "their next encounter with a police officer could be their last member "
    "trace. Obama maintained that all of us—in particular the people in "
    "education—have to start doing something that helps unite people of "
    "different colors and of different ethnic back grounds. Add itionally, "
    "Obama also posited that people in law and law enforcement have to follow "
    "through the concrete reforms that may incrementally eliminate racial bias "
    "in the criminal justice system and to ensure that full measure of justice "
    "that Floyd and so many others have been denied. Last but not least, "
    "policymakers have to start enacting laws that can expand the economic "
    "opport unit ies for those minority groups that have been too long "
    "marg ina lized. The above works may look trivial, thank less and "
    "difficult, but they are necessary to make the America the country US "
    "people believe ina gain."
)

WATER_110_NEW_PASSAGE = (
    "請依下文回答第56題至第60題: Members of jury have found former Minneapolis "
    "police officer guilty for the death of an African American, George Floyd. "
    "Floyd died on May 25, 2020 after the police officer held his knee against "
    "Floyd's neck or upper body for nearly nine minutes. This police officer "
    "was accused of third-degree murder and second-degree manslaughter. This "
    "trial is probably one of the most closely watched trials in recent decades, "
    "because it involves a law enforcement officer; and Floyd's death under the "
    "knee of this officer has reverberated around the world. Although, the jury "
    "members have announced that this police officer is guilty in all charges, "
    "this unfortunate incident and Floyd's last words—I cannot breathe—have "
    "been deeply ingrained in the minds of American and have incited numerous "
    "marches, and protests across the country. Responding to the result of "
    "this trial, former US president, Barack Obama, asked this thought-"
    "provoking question: \"Would justice be done\" after we learned about the "
    "verdict of this trail? While this verdict may have somewhat uplifted the "
    "minds of Floyd's family and is a necessary step on the road to justice, "
    "it is far from a sufficient one. According to Obama, true justice is "
    "\"about much more than a single verdict in a single trial.\" Obama argues "
    "that we cannot override what has happened, but it's important for all "
    "citizens to recognize that millions of people of color live in fear that "
    "their next encounter with a police officer could be their last "
    "remembrance. Obama maintained that all of us—in particular the people in "
    "education—have to start doing something that helps unite people of "
    "different colors and of different ethnic backgrounds. Additionally, "
    "Obama also posited that people in law and law enforcement have to follow "
    "through the concrete reforms that may incrementally eliminate racial bias "
    "in the criminal justice system and to ensure that full measure of justice "
    "that Floyd and so many others have been denied. Last but not least, "
    "policymakers have to start enacting laws that can expand the economic "
    "opportunities for those minority groups that have been too long "
    "marginalized. The above works may look trivial, thankless and "
    "difficult, but they are necessary to make the America the country US "
    "people believe in again."
)


def fix_water_110(data):
    count = 0
    for q in data["questions"]:
        if q.get("number") in [56, 57, 58, 59, 60]:
            p = q.get("passage", "")
            if "itis far from" in p or "mans laugh ter" in p:
                q["passage"] = WATER_110_NEW_PASSAGE
                count += 1
    return count


# ── 犯罪防治學系矯治組 113 Q31 ──────────────────────────────────────

def fix_criminal_113_q31(data):
    count = 0
    for q in data["questions"]:
        if q.get("number") == 31:
            old = q.get("stem", "")
            if "dateon them ilk" in old:
                q["stem"] = (
                    "I need to check the date on the milk before using it "
                    "to make sure it is still fresh."
                )
                count += 1
        if q.get("number") == 37:
            old = q.get("stem", "")
            if "Byregulation" in old:
                q["stem"] = (
                    "By regulation, it is _____ for all workers to wear "
                    "protective clothing when they are operating the machine."
                )
                count += 1
            opts = q.get("options", {})
            if opts.get("C") == "indu str ious":
                opts["C"] = "industrious"
                count += 1
    return count


# ── 犯罪防治學系矯治組 113 Q46-50 passage ──────────────────────────────────

CRIMINAL_113_Q46_OLD_MARKER = "region sof Morocco"

CRIMINAL_113_Q46_NEW_PASSAGE = (
    "請依下文回答第46題至第50題 The Saharan regions of Morocco are home to the "
    "Berbers, an ethnic group native to North Africa. Madfouna—a stuffed "
    "flatbread prepared by using a handful of staple ingredients—is "
    "traditionally baked in a fire pit in the sand or a mud oven, and has long "
    "served as a wholesome meal for many Berber families. Once baked, the bread "
    "so closely resembles a pizza that it is locally nicknamed \"the Berber "
    "pizza.\" Using an ancient Saharan bread recipe incorporating flour, yeast, "
    "salt, olive oil, and water, the dough is kneaded and then rolled into a "
    "round shape before being stretched over fillings—including beef, eggs, "
    "nuts, onions, and garlic, and herbs and spices such as cumin, paprika, "
    "turmeric, ginger, and parsley—and pinched closed. Every family has their "
    "own version of madfouna. Some use more basic ingredients such as eggs, "
    "tomatoes, and sunflower or poppy seeds, while others add almonds, cashews, "
    "olives, lamb, chicken, minced beef, or slices of cooked steak. The options "
    "are virtually endless. Whichever ingredients make up the filling, one thing "
    "is agreed upon across the region: the authentic methods of cooking "
    "madfouna in desert sands or using a mud oven undoubtedly lead to the most "
    "delicious version, complete with an unrivalled smoky taste that a modern, "
    "conventional oven cannot replicate. Today, madfouna can mostly be found in "
    "small Berber pizza takeaway joints in Rissani, a sleepy Saharan town "
    "famed for the dish. In Rissani, a slightly faster pace of life than in "
    "the desert leads to a greater demand for fast food. Tucked within the "
    "narrow streets of the market and conveniently placed near the taxi stands "
    "lie small takeaway joints with \"pizza\" symbols to mark where you can "
    "order a takeaway madfouna, the primary dish on the menu. It's not uncommon "
    "for these places to get so busy that people queue for more than an hour as "
    "the chefs rotate the orders in the large fire ovens. Each madfouna is so "
    "particular to each individual's tastes that locals often bring their own "
    "fillings—sourced from trusted butchers or prepared at home by family "
    "members—which they ask the chefs to bake into their orders."
)


def fix_criminal_113_q46(data):
    count = 0
    for q in data["questions"]:
        if q.get("number") in [46, 47, 48, 49, 50]:
            p = q.get("passage", "")
            if CRIMINAL_113_Q46_OLD_MARKER in p:
                q["passage"] = CRIMINAL_113_Q46_NEW_PASSAGE
                count += 1
    return count


# ── Simple replacements in Chinese-mixed text ──────────────────────────────

SIMPLE_FIXES = {
    "公共安全學系社安組/114年/情報學/試題.json": [
        ("FiveEyes", "Five Eyes"),
    ],
    "犯罪防治學系矯治組/113年/監獄學/試題.json": [
        ("PrisonRiot", "Prison Riot"),
    ],
    "行政管理學系/113年/警察危機應變與安全管理/試題.json": [
        ("StevenFink", "Steven Fink"),
    ],
}


def apply_simple_fixes(relpath, replacements):
    fpath = os.path.join(BASE, relpath)
    with open(fpath, "r") as f:
        content = f.read()
    count = 0
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            count += 1
    if count > 0:
        with open(fpath, "w") as f:
            f.write(content)
        print(f"  Fixed {count} simple replacements in {relpath}")
    global fixes_applied
    fixes_applied += count


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Fixing remaining garbled passages...")
    print()

    fix_file(
        "水上警察學系/110年/中華民國憲法與水上警察學系專業英文/試題.json",
        fix_water_110,
    )

    fix_file(
        "犯罪防治學系矯治組/113年/法學知識與英文（包括中華民國憲法、法學緒論、英文）/試題.json",
        lambda data: fix_criminal_113_q31(data) + fix_criminal_113_q46(data),
    )

    for relpath, replacements in SIMPLE_FIXES.items():
        apply_simple_fixes(relpath, replacements)

    print(f"\nTotal fixes applied: {fixes_applied}")
