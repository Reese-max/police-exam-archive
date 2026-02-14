#!/usr/bin/env python3
"""
OCR 瑕疵自動修復腳本
修復資管系考古題總覽.html 中的 OCR 問題：
1. 英文單字被空格拆開（如 ti on → tion）
2. 英文單字黏在一起（如 communitypolicing → community policing）
3. 考卷代號黏在文字尾端（如 arrest51250、51350）
"""

import re
import sys
import os
from pathlib import Path
from difflib import unified_diff

HTML_PATH = Path(r"C:\Users\User\Desktop\考古題下載\資管系考古題\資管系考古題總覽.html")

# ========== Phase 1a: 修復被拆開的英文單字 ==========
# 這些是確定性的替換，不會誤傷正常文字

# 拆開的常見後綴
SPLIT_SUFFIX_FIXES = [
    # -tion 系列
    (r'\bde-escalati on\b', 'de-escalation'),
    (r'\bprobati on\b', 'probation'),
    (r'\bcontaminati on\b', 'contamination'),
    (r'\bauthorizati on\b', 'authorization'),
    (r'\binterrogati on\b', 'interrogation'),
    (r'\bexpediti on\b', 'expedition'),
    (r'\bextraditi on\b', 'extradition'),
    (r'\bextracti on\b', 'extraction'),
    (r'\bexpositi on\b', 'exposition'),
    (r'\bexcursi on\b', 'excursion'),
    (r'\bconventi on\b', 'convention'),
    (r'\bconservati on\b', 'conservation'),
    (r'\bconvicti on\b', 'conviction'),
    (r'\baccelerati on\b', 'acceleration'),
    (r'\bconcentrati on\b', 'concentration'),
    (r'\bimportati on\b', 'importation'),
    (r'\bInvestigati on\b', 'Investigation'),
    (r'\brelati on\b', 'relation'),
    (r'\bprotecti on\b', 'protection'),
    (r'\bregulati on\b', 'regulation'),
    (r'\bintervenenti on\b', 'intervention'),  # possible typo in original
    (r'\binterventi on\b', 'intervention'),
    (r'\bexploitati on\b', 'exploitation'),
    (r'\binnovati on\b', 'innovation'),
    (r'\borganizati on\b', 'organization'),
    (r'\bcommunicati on\b', 'communication'),
    (r'\bidentificati on\b', 'identification'),
    (r'\binformati on\b', 'information'),
    (r'\bsituati on\b', 'situation'),
    (r'\bprosecuti on\b', 'prosecution'),
    (r'\bpreventati on\b', 'preventation'),
    (r'\bpreventi on\b', 'prevention'),
    (r'\bdetenti on\b', 'detention'),
    (r'\bcorrupti on\b', 'corruption'),
    (r'\bexaminati on\b', 'examination'),
    (r'\binvestigati on\b', 'investigation'),
    (r'\boperati on\b', 'operation'),
    (r'\bdiscriminati on\b', 'discrimination'),
    (r'\bviolati on\b', 'violation'),
    (r'\brestorati on\b', 'restoration'),
    (r'\blegislati on\b', 'legislation'),
    (r'\binstalati on\b', 'installation'),
    (r'\binstallati on\b', 'installation'),
    (r'\bcompensati on\b', 'compensation'),
    (r'\bpopulati on\b', 'population'),
    (r'\beducati on\b', 'education'),
    (r'\bfoundati on\b', 'foundation'),
    (r'\bapplicati on\b', 'application'),
    (r'\badministrati on\b', 'administration'),
    (r'\belecti on\b', 'election'),
    (r'\binspecti on\b', 'inspection'),
    (r'\bconnecti on\b', 'connection'),
    (r'\bcollecti on\b', 'collection'),
    (r'\bdetecti on\b', 'detection'),
    (r'\bprodcuti on\b', 'production'),
    (r'\bproducti on\b', 'production'),
    (r'\bcorrecti on\b', 'correction'),
    (r'\binteracti on\b', 'interaction'),
    (r'\bprotesti on\b', 'protestation'),
    (r'\bcauti on\b', 'caution'),
    (r'\bsecti on\b', 'section'),
    (r'\bacti on\b', 'action'),
    (r'\bfuncti on\b', 'function'),
    (r'\bpositi on\b', 'position'),
    (r'\bnati on\b', 'nation'),
    (r'\bmoti on\b', 'motion'),
    (r'\bnoti on\b', 'notion'),
    (r'\bopti on\b', 'option'),
    (r'\bporti on\b', 'portion'),
    (r'\bmeneti on\b', 'mention'),
    (r'\bmenti on\b', 'mention'),
    (r'\battenti on\b', 'attention'),
    (r'\brevoluti on\b', 'revolution'),
    (r'\bsoluti on\b', 'solution'),
    (r'\bconstituti on\b', 'constitution'),
    (r'\binstituti on\b', 'institution'),
    (r'\bsubstituti on\b', 'substitution'),
    (r'\bevoluti on\b', 'evolution'),
    (r'\bdistributi on\b', 'distribution'),
    (r'\bpolluti on\b', 'pollution'),
    (r'\bresoluti on\b', 'resolution'),
    (r'\bexecuti on\b', 'execution'),
    (r'\bpersecuti on\b', 'persecution'),
    # -sion 系列
    (r'\bextensi on\b', 'extension'),
    (r'\bdecisi on\b', 'decision'),
    (r'\bconclusi on\b', 'conclusion'),
    (r'\binclusi on\b', 'inclusion'),
    (r'\bexclusi on\b', 'exclusion'),
    (r'\bconfusi on\b', 'confusion'),
    (r'\billusi on\b', 'illusion'),
    (r'\binvasi on\b', 'invasion'),
    (r'\beversi on\b', 'eversion'),
    (r'\bversi on\b', 'version'),
    (r'\bconversi on\b', 'conversion'),
    (r'\boccasi on\b', 'occasion'),
    (r'\bpersuasi on\b', 'persuasion'),
    (r'\bexplosi on\b', 'explosion'),
    (r'\bprofessi on\b', 'profession'),
    (r'\bsessi on\b', 'session'),
    (r'\bimpressi on\b', 'impression'),
    (r'\bexpressi on\b', 'expression'),
    (r'\bagressi on\b', 'aggression'),
    (r'\baggressi on\b', 'aggression'),
    (r'\bcompassi on\b', 'compassion'),
    (r'\bpassi on\b', 'passion'),
    (r'\bmissi on\b', 'mission'),
    (r'\bpermissi on\b', 'permission'),
    (r'\badmissi on\b', 'admission'),
    (r'\bcommissi on\b', 'commission'),
    (r'\bsubmissi on\b', 'submission'),
    (r'\bemissi on\b', 'emission'),
    (r'\bdimensi on\b', 'dimension'),
    (r'\btensi on\b', 'tension'),
    (r'\bsuspensi on\b', 'suspension'),
    (r'\bextensi on\b', 'extension'),
    (r'\bpensi on\b', 'pension'),
    (r'\bprovisi on\b', 'provision'),
    (r'\bdivisi on\b', 'division'),
    (r'\bsupervisi on\b', 'supervision'),
    (r'\brevisi on\b', 'revision'),
    (r'\btelevi si on\b', 'television'),
    (r'\bprisi on\b', 'prison'),
    (r'\bpris on\b', 'prison'),
    (r'\bPris on\b', 'Prison'),
    (r'\breas on\b', 'reason'),
    (r'\bReas on\b', 'Reason'),
    (r'\bseas on\b', 'season'),
    (r'\bSeas on\b', 'Season'),
    (r'\bpers on\b', 'person'),
    (r'\bPers on\b', 'Person'),
    (r'\bpois on\b', 'poison'),
    (r'\bPois on\b', 'Poison'),
    (r'\bles on\b', 'lesson'),  # careful: might match "les on"
    (r'\bLes on\b', 'Lesson'),
    (r'\baccusati on\b', 'accusation'),
    (r'\bAccusati on\b', 'Accusation'),
    (r'\bIndicat or\b', 'Indicator'),
    (r'\bindicat or\b', 'indicator'),
]

# 通用 -tion/-sion 捕獲模式（最後執行，處理上面沒覆蓋到的）
GENERIC_SUFFIX_FIXES = [
    (r'(\w)ti on\b', r'\1tion'),    # 任何 Xti on → Xtion
    (r'(\w)si on\b', r'\1sion'),    # 任何 Xsi on → Xsion
]

# 拆開的常見單字（非後綴型）
SPLIT_WORD_FIXES = [
    (r'\bmonit or\b', 'monitor'),
    (r'\bhum an\b', 'human'),
    (r'\bHum an\b', 'Human'),
    (r'\bTaiw an\b', 'Taiwan'),
    (r'\bYunl in\b', 'Yunlin'),
    (r'\bGodf ather\b', 'Godfather'),
    (r'\bGodfa ther\b', 'Godfather'),
    (r'\bReplik a\b', 'Replika'),
    (r'\bsoftw are\b', 'software'),
    (r'\bSoftw are\b', 'Software'),
    (r'\btoge ther\b', 'together'),
    (r'\bToge ther\b', 'Together'),
    (r'\bperpet or\b', 'perpetrator'),  # might be partial
    (r'\bwom an\b', 'woman'),
    (r'\bWom an\b', 'Woman'),
    (r'\bhum or\b', 'humor'),
    (r'\bmaj or\b', 'major'),
    (r'\bMaj or\b', 'Major'),
    (r'\bcomm on\b', 'common'),
    (r'\bComm on\b', 'Common'),
    (r'\bo ther\b', 'other'),
    (r'\bO ther\b', 'Other'),
    (r'\ban other\b', 'another'),
    (r'\bAn other\b', 'Another'),
    (r'\bwhe ther\b', 'whether'),
    (r'\bWhe ther\b', 'Whether'),
    (r'\btoge ther\b', 'together'),
    (r'\bToge ther\b', 'Together'),
    (r'\bfa ther\b', 'father'),
    (r'\bFa ther\b', 'Father'),
    (r'\bmo ther\b', 'mother'),
    (r'\bMo ther\b', 'Mother'),
    (r'\bwea ther\b', 'weather'),
    (r'\bWea ther\b', 'Weather'),
    (r'\bgath er\b', 'gather'),
    (r'\bGath er\b', 'Gather'),
    (r'\bra ther\b', 'rather'),
    (r'\bRa ther\b', 'Rather'),
    (r'\bei ther\b', 'either'),
    (r'\bEi ther\b', 'Either'),
    (r'\bnei ther\b', 'neither'),
    (r'\bNei ther\b', 'Neither'),
    (r'\bCharact er\b', 'Character'),
    (r'\bcharact er\b', 'character'),
    (r'\bisl and\b', 'island'),
    (r'\bIsl and\b', 'Island'),
    (r'\bdemand\b', 'demand'),  # this shouldn't need fixing, just in case
    (r'\bcomm and\b', 'command'),
    # th 系列
    (r'\bth at\b', 'that'),
    (r'\bTh at\b', 'That'),
    (r'\bth is\b', 'this'),
    (r'\bTh is\b', 'This'),
    (r'\bth an\b', 'than'),
    (r'\bTh an\b', 'Than'),
    (r'\bth en\b', 'then'),
    (r'\bTh en\b', 'Then'),
    (r'\bth e\b', 'the'),
    (r'\bTh e\b', 'The'),
    (r'\bth ey\b', 'they'),
    (r'\bTh ey\b', 'They'),
    (r'\bth eir\b', 'their'),
    (r'\bTh eir\b', 'Their'),
    (r'\bth ere\b', 'there'),
    (r'\bTh ere\b', 'There'),
    (r'\bth ese\b', 'these'),
    (r'\bTh ese\b', 'These'),
    (r'\bth ose\b', 'those'),
    (r'\bTh ose\b', 'Those'),
    (r'\bth ough\b', 'though'),
    (r'\bTh ough\b', 'Though'),
    (r'\bth rough\b', 'through'),
    (r'\bTh rough\b', 'Through'),
    (r'\bth ought\b', 'thought'),
    (r'\bTh ought\b', 'Thought'),
    (r'\bth reat\b', 'threat'),
    (r'\bTh reat\b', 'Threat'),
    (r'\bth re at\b', 'threat'),
    (r'\bTh re at\b', 'Threat'),
    (r'\bathre at\b', 'a threat'),  # special case: athre at -> a threat
    # f 系列
    (r'\bf or\b', 'for'),
    (r'\bF or\b', 'For'),
    (r'\bf rom\b', 'from'),
    (r'\bF rom\b', 'From'),
    # c 系列
    (r'\bc an\b', 'can'),
    (r'\bC an\b', 'Can'),
    # wh 系列
    (r'\bwh at\b', 'what'),
    (r'\bWh at\b', 'What'),
    (r'\bwh en\b', 'when'),
    (r'\bWh en\b', 'When'),
    (r'\bwh ere\b', 'where'),
    (r'\bWh ere\b', 'Where'),
    (r'\bwh ich\b', 'which'),
    (r'\bWh ich\b', 'Which'),
    (r'\bwh ile\b', 'while'),
    (r'\bWh ile\b', 'While'),
    (r'\bwh o\b', 'who'),
    (r'\bWh o\b', 'Who'),
    (r'\bwh y\b', 'why'),
    (r'\bWh y\b', 'Why'),
    # s/he etc
    (r'\bs/he\b', 's/he'),  # keep as is
    (r'\bgre at\b', 'great'),
    (r'\bGre at\b', 'Great'),
    # 其他常見拆字
    (r'\bch at\b', 'chat'),  # be careful with this one - only in English context
    (r'\bin to\b', 'into'),
    (r'\bIn to\b', 'Into'),
    (r'\bsuc has\b', 'such as'),
]

# ========== Phase 1b: 修復英文字黏在一起 ==========
# 針對 114 年憲法與警察專業英文科目的嚴重黏連問題

GLUED_WORD_FIXES = [
    # 114年 英文題 Q44 整段
    ('Policeofficers areprofessionallytrainedtohandle tenseorpotentiallydangerous situations. Inmanycases, insteadofusingphysicalforceimmediately, officersareexpectedtoapply techniquestocalm theindividual andreduce theriskofviolence.',
     'Police officers are professionally trained to handle tense or potentially dangerous situations. In many cases, instead of using physical force immediately, officers are expected to apply _____ techniques to calm the individual and reduce the risk of violence.'),

    # Q45
    ('As part of communitypolicing strategies, officers are regularlyassigned to monit or residential andcommercialareas. During a ,theyremainalertforanysignsofsuspicious, illegal, orunusualactivity that maypose athre at topublicsafety.',
     'As part of community policing strategies, officers are regularly assigned to monitor residential and commercial areas. During a _____, they remain alert for any signs of suspicious, illegal, or unusual activity that may pose a threat to public safety.'),

    # Q45 options
    ('trafficstop', 'traffic stop'),
    ('routinepatrol', 'routine patrol'),
    ('highwayblock', 'highway block'),
    ('vehicleinspection', 'vehicle inspection'),

    # Q46
    ('After conducting a lawful arrest based on sufficient evidence, the police officers decided to placethesuspect in to toensure that hewouldremainundersupervision.',
     'After conducting a lawful arrest based on sufficient evidence, the police officers decided to place the suspect in to _____ to ensure that he would remain under supervision.'),

    # Q47
    ('At a burglary scene, officers must follow proper procedures when handling physical evidence.Wearingglovesisessentialtoprevent ,whichcouldaffect thecredibilityof theevidenceincourt.',
     'At a burglary scene, officers must follow proper procedures when handling physical evidence. Wearing gloves is essential to prevent _____, which could affect the credibility of the evidence in court.'),

    # Q48
    ('Acommonstrategyoffraudsters is offeringfinancial suc has abonus orlotteryas abait.',
     'A common strategy of fraudsters is offering financial _____ such as a bonus or lottery as a bait.'),

    # Q49
    ('Thefact th at noonesteppeduptohelp thevictim in the MRTassault suggests public .',
     'The fact that no one stepped up to help the victim in the MRT assault suggests public _____.'),

    # Q50
    ('The witness was in to silence because her family members were threatened by peopleassociatedwith theoffender.',
     'The witness was _____ into silence because her family members were threatened by people associated with the offender.'),

    # Q44 option (arrest + 代號)
    ('arrest51250、51350', 'arrest'),

    # Q80 option (custodyorder)
    ('custodyorder', 'custody order'),
]

# ========== Phase 1c: 清除考卷代號 ==========
# 代號格式: 5位數字 或 5位數字、5位數字

def clean_exam_codes(text):
    """移除文字中的考卷代號"""
    # Pattern 1: 代號黏在文字末尾 (如 shame51250、51350</span>)
    text = re.sub(r'(\w)(\d{5}(?:、\d{5})*)\s*</span>', r'\1</span>', text)

    # Pattern 2: 代號在中文文字中間 (如 行政執行50720、5082051020、51220)
    # 需要特別處理：有時是 5位數+、+5位數+5位數+、+5位數（代號連在一起）
    text = re.sub(r'([\u4e00-\u9fff])(\d{5}(?:、?\d{5})*)(</span>)', r'\1\3', text)

    # Pattern 3: 移除只含代號的 exam-text 行
    # (保留整行結構但清除代號文字)
    text = re.sub(r'(class="exam-text">)\d{5}(?:、\d{5})*(</)', r'\1\2', text)

    return text

def fix_split_words(line):
    """修復被空格拆開的英文單字"""
    for pattern, replacement in SPLIT_SUFFIX_FIXES:
        line = re.sub(pattern, replacement, line)
    for pattern, replacement in SPLIT_WORD_FIXES:
        line = re.sub(pattern, replacement, line)
    # 最後用通用模式捕獲殘餘的 -tion/-sion 拆字
    for pattern, replacement in GENERIC_SUFFIX_FIXES:
        line = re.sub(pattern, replacement, line)
    return line

def fix_glued_words(line):
    """修復黏在一起的英文單字"""
    for old, new in GLUED_WORD_FIXES:
        if old in line:
            line = line.replace(old, new)
    return line

def is_content_line(line):
    """判斷是否為內容行（非 CSS/JS/HTML 結構行）"""
    stripped = line.strip()
    # 只處理包含 q-text, opt-text, essay-question, exam-text 的行
    if any(cls in stripped for cls in ['q-text', 'opt-text', 'essay-question', 'exam-text']):
        return True
    return False

def fix_line(line):
    """修復單行的所有 OCR 問題"""
    if not is_content_line(line):
        return line

    original = line

    # Step 1: 修復黏字（精確替換）
    line = fix_glued_words(line)

    # Step 2: 修復拆字
    line = fix_split_words(line)

    # Step 3: 清除考卷代號
    line = clean_exam_codes(line)

    return line


def generate_diff(original_lines, fixed_lines):
    """產生可讀的 diff"""
    changes = []
    for i, (orig, fixed) in enumerate(zip(original_lines, fixed_lines), 1):
        if orig != fixed:
            changes.append((i, orig.rstrip(), fixed.rstrip()))
    return changes


def main():
    if not HTML_PATH.exists():
        print(f"❌ 找不到檔案: {HTML_PATH}")
        sys.exit(1)

    print(f"📂 讀取檔案: {HTML_PATH}")
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        original_lines = f.readlines()

    print(f"   共 {len(original_lines)} 行")

    # 執行修復
    fixed_lines = [fix_line(line) for line in original_lines]

    # 產生 diff
    changes = generate_diff(original_lines, fixed_lines)

    if not changes:
        print("✅ 沒有發現需要修復的問題")
        return

    print(f"\n🔧 發現 {len(changes)} 行需要修復：\n")
    for line_num, orig, fixed in changes:
        print(f"  行 {line_num}:")
        print(f"    ❌ {orig[:120]}{'...' if len(orig) > 120 else ''}")
        print(f"    ✅ {fixed[:120]}{'...' if len(fixed) > 120 else ''}")
        print()

    # 檢查是否有 --apply 參數
    if '--apply' in sys.argv:
        print(f"\n💾 寫入修復結果...")
        with open(HTML_PATH, 'w', encoding='utf-8') as f:
            f.writelines(fixed_lines)
        print(f"✅ 已修復 {len(changes)} 行")
    else:
        print(f"\n⚠️  預覽模式 - 使用 --apply 參數來實際寫入修改")
        print(f"   python fix_ocr.py --apply")


if __name__ == '__main__':
    main()
