#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_round2.py — 二次審計修復腳本
修復 deep_audit.py 發現的所有問題（P0/P1/P2）
"""

import json
import os
import re
import glob
import copy
import shutil
from datetime import datetime
from pathlib import Path
from collections import defaultdict

try:
    import pdfplumber
except ImportError:
    pdfplumber = None
    print("警告: pdfplumber 未安裝，無法從 PDF 提取選項")

BASE = '考古題庫'
BACKUP_DIR = f'backups/round2_fix_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
STATS = defaultdict(int)

# ──────────────────────────────────────────────
# 工具函數
# ──────────────────────────────────────────────

def backup_file(filepath):
    """備份檔案到 BACKUP_DIR，保留目錄結構"""
    rel = os.path.relpath(filepath, '.')
    dest = os.path.join(BACKUP_DIR, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(filepath, dest)

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def log(msg):
    print(f'  {msg}')

def extract_pdf_text(pdf_path):
    """從 PDF 提取所有頁面文字"""
    if not pdfplumber:
        return ""
    with pdfplumber.open(pdf_path) as pdf:
        texts = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                texts.append(text)
    return '\n'.join(texts)

def extract_options_from_pdf_lines(lines, qnum, next_qnum=None):
    """從 PDF 文字行中提取指定題號的選項

    支援兩種格式：
    1. 單詞型（4個詞在一行）: coincide plummet speculate intervene
    2. 句子型（每行一個選項）
    3. 編號組合型: ①②③④ ①②③ 等
    """
    # 找到題號行
    q_start = None
    q_end = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(rf'^{qnum}\s', stripped):
            q_start = i
        elif q_start is not None and next_qnum and re.match(rf'^{next_qnum}\s', stripped):
            q_end = i
            break
        elif q_start is not None and re.match(r'^\d{1,3}\s', stripped):
            num = int(re.match(r'^(\d{1,3})', stripped).group(1))
            if num > qnum:
                q_end = i
                break

    if q_start is None:
        return None

    if q_end is None:
        q_end = min(q_start + 20, len(lines))

    # 提取題目區塊
    block_lines = []
    for i in range(q_start, q_end):
        stripped = lines[i].strip()
        # 跳過頁面標頭
        if re.match(r'^代號[:：]', stripped) or re.match(r'^頁次[:：]', stripped):
            continue
        if re.match(r'^\d{5}', stripped) and len(stripped) < 20:
            continue
        block_lines.append(stripped)

    if not block_lines:
        return None

    # 嘗試識別選項行（題幹之後的行）
    # 策略：找到不以題號開頭、且不是題幹延續的行
    # 選項通常在題幹結束後的行

    return block_lines


# ══════════════════════════════════════════════════════
#  P0-1: 108年外國文（英文）40 題缺 options
# ══════════════════════════════════════════════════════

def fix_p0_1_english_40():
    """修復 108年外國文（英文）40 題缺 options

    從 PDF 重新解析選項。這份考卷的選項格式特殊：
    - Q1-Q10: 詞彙題，4個單詞在一行
    - Q11-Q15: 填空閱讀，4個單詞在一行
    - Q16-Q20: 填空閱讀，4個單詞在一行
    - Q21-Q25: 填空閱讀
    - Q26+: 閱讀理解，選項為完整句子
    """
    print('\n' + '=' * 60)
    print('P0-1: 修復 108年外國文（英文）40 題缺 options')
    print('=' * 60)

    json_path = glob.glob(f'{BASE}/公共安全學系情報組/108年/外國文*英文*/試題.json')
    if not json_path:
        log('找不到 JSON 檔案')
        return

    json_path = json_path[0]
    data = load_json(json_path)

    # 從 PDF 提取
    pdf_path = 'downloads_for_fix/108_601_外國文（英文）_試題.pdf'
    if not os.path.exists(pdf_path):
        # 嘗試從考古題庫找
        pdf_candidates = glob.glob(f'{BASE}/公共安全學系情報組/108年/外國文*英文*/試題.pdf')
        if pdf_candidates:
            pdf_path = pdf_candidates[0]
        else:
            log(f'找不到 PDF: {pdf_path}')
            return

    full_text = extract_pdf_text(pdf_path)
    lines = full_text.split('\n')

    # 硬編碼從 PDF 中提取的選項（手動核對）
    # 格式: {qnum: {'A': ..., 'B': ..., 'C': ..., 'D': ...}}
    options_map = {
        1:  {'A': 'coincide', 'B': 'plummet', 'C': 'speculate', 'D': 'intervene'},
        2:  {'A': 'broken', 'B': 'portable', 'C': 'contagious', 'D': 'disciplined'},
        3:  {'A': 'riddles', 'B': 'utensils', 'C': 'cabinets', 'D': 'aspects'},
        4:  {'A': 'industrious', 'B': 'distressing', 'C': 'agricultural', 'D': 'spectacular'},
        5:  {'A': 'saturated', 'B': 'intimidated', 'C': 'designated', 'D': 'aggravated'},
        6:  {'A': 'redundant', 'B': 'radiant', 'C': 'competent', 'D': 'intermittent'},
        7:  {'A': 'abysmally', 'B': 'evasively', 'C': 'impudently', 'D': 'observantly'},
        8:  {'A': 'compensate', 'B': 'donate', 'C': 'rotate', 'D': 'speculate'},
        9:  {'A': 'reconciliation', 'B': 'circumference', 'C': 'amendment', 'D': 'indictment'},
        10: {'A': 'deficient', 'B': 'omniscient', 'C': 'transcient', 'D': 'proficient'},
        # Q11-15: 閱讀填空
        11: {'A': 'settled', 'B': 'safeguarded', 'C': 'saturated', 'D': 'seduced'},
        12: {'A': 'infection', 'B': 'inspiration', 'C': 'legalization', 'D': 'litigation'},
        13: {'A': 'determining', 'B': 'disposing', 'C': 'defying', 'D': 'disembarking'},
        14: {'A': 'deletion', 'B': 'defensiveness', 'C': 'divisiveness', 'D': 'diagnosis'},
        15: {'A': 'epitomizes', 'B': 'resolves', 'C': 'affects', 'D': 'elevates'},
        # Q16-20: 閱讀填空
        16: {'A': 'disappeared', 'B': 'vanquished', 'C': 'overheard', 'D': 'reduced'},
        17: {'A': 'resurgence', 'B': 'reduction', 'C': 'rendition', 'D': 'repartee'},
        18: {'A': 'demographics', 'B': 'statistics', 'C': 'opportunities', 'D': 'densities'},
        19: {'A': 'exit', 'B': 'survive', 'C': 'remove', 'D': 'deteriorate'},
        20: {'A': 'daydreaming', 'B': 'anxiety', 'C': 'novelty', 'D': 'nostalgia'},
        # Q21-25: 閱讀填空（超音波檢查文章）
        21: {'A': 'emits', 'B': 'dismisses', 'C': 'neutralizes', 'D': 'eliminates'},
        22: {'A': 'small', 'B': 'large', 'C': 'empty', 'D': 'full'},
        23: {'A': 'inferior to', 'B': 'superior to', 'C': 'prior to', 'D': 'posterior to'},
        24: {'A': 'assess', 'B': 'accede', 'C': 'access', 'D': 'address'},
        25: {'A': 'due', 'B': 'blind', 'C': 'appointed', 'D': 'expiration'},
        # Q26-30: 閱讀理解（健保移民文章）
        26: {'A': 'Reasons why the health care costs are rapidly increasing.',
             'B': 'Potential benefits of providing health insurance coverage to illegal immigrants.',
             'C': 'Reasons why illegal immigrants should not be included in national health insurance plans.',
             'D': 'How health care costs may decrease due to inclusion of illegal immigrants in national health insurance plans.'},
        27: {'A': 'Given the ease of travel nowadays, including illegal immigrants in health insurance can reduce the spread of infectious diseases.',
             'B': 'Illegal immigrants should be excluded from the health care system before being sent back to their countries of origin.',
             'C': 'Excluding illegal immigrants from the health care insurance is an effective way to lower the nation\'s health care costs.',
             'D': 'It is necessary to design more rules to keep illegal immigrants from using expensive medical services in the country.'},
        28: {'A': 'More research may be needed to understand the issue further.',
             'B': 'Some policy modifications may be needed in the future.',
             'C': 'More funds may be needed to implement the policy.',
             'D': 'Some health care benefits of the public may need to be further reduced.'},
        29: {'A': 'The health insurance should be handled by the private sector.',
             'B': 'Providing public health care to illegal immigrants is the local government\'s business.',
             'C': 'The federal government should reform the public health insurance to make it accessible to illegal immigrants.',
             'D': 'The proposed health insurance reform should wait until the immigration reform is completed.'},
        30: {'A': 'The health insurance premiums will decrease.',
             'B': 'More immigrants will have access to preventive medical treatments.',
             'C': 'There will be more infectious diseases in the country.',
             'D': 'More immigrants will end up in emergency rooms with critical illness.'},
        # Q31-35: 閱讀理解（素食文章）
        31: {'A': 'The Environmental Impact of Vegetarianism.',
             'B': 'The Health Benefits of Plant-based Diets.',
             'C': 'The Social Challenges of Being Vegans.',
             'D': 'The Popularity of Meat-free Products.'},
        32: {'A': 'The steady supply of fruit and vegetables.',
             'B': 'The influence of cultures with plant-based eating.',
             'C': 'The protection of animal welfare and resources.',
             'D': 'The wide availability of dietary supplements.'},
        33: {'A': 'Abandoning.', 'B': 'Transporting.', 'C': 'Generating.', 'D': 'Escaping.'},
        34: {'A': 'To explain why previous research produced negative results about vegetarianism.',
             'B': 'To provide scientific evidence supporting the health effects of vegan diets.',
             'C': 'To reveal the increase in the number of vegans in the American society.',
             'D': 'To show how plant-based eating can be associated with certain chronic illness.'},
        35: {'A': 'Converting to a Mediterranean diet can reduce the risk of chronic illness.',
             'B': 'Going vegan has become a way of showing personal freedom.',
             'C': 'Adopting a partial vegetarian diet can still make people healthy.',
             'D': 'Foods like tofu and beans provide a good source of protein for vegans.'},
        # Q36-40: 閱讀理解（政治兩極化文章）
        36: {'A': 'To argue against the open-closed theory and offer a better explanation.',
             'B': 'To show evidence that open and closed are not necessarily opposites.',
             'C': 'To criticize the division between left and right that defines politics.',
             'D': 'To make evident that political polarization is not a new phenomenon.'},
        37: {'A': 'To imply that the example given before is to offer an opposite view.',
             'B': 'To introduce an instance which is true for the same reason that was given previously.',
             'C': 'To add another case which is more important than what was said and to correct it.',
             'D': 'To indicate that what is said is partly true in spite of the thing that has happened.'},
        38: {'A': 'It allows access to a world that is protected from the disadvantage of globalization.',
             'B': 'It guarantees jobs with superstar companies that have measures to protect themselves.',
             'C': 'It reveals the deeper forces dividing the worlds and expresses the concerns of losers.',
             'D': 'It provides a middle-class organization that offers security and the state bureaucracy.'},
        39: {'A': 'To imply that having a strong border gives people a sense that they can be more open.',
             'B': 'To make readers doubt the boast the city once made of having a formidable wall.',
             'C': 'To suggest that the world\'s great center of commerce was the crossroads and the harbor.',
             'D': 'To question whether a walled city necessarily means closedness.'},
        40: {'A': 'United by anger at the elitists, they are eager to change the existing system.',
             'B': 'They play down the legitimate concerns of losers and spare winners.',
             'C': 'With a common outlook, they legitimize their disdain for rival tribes.',
             'D': 'They are willing to be more open as long as their jobs are protected.'},
    }

    backup_file(json_path)
    fixed = 0
    for q in data['questions']:
        if q.get('type') == 'choice' and not q.get('options'):
            qnum = q.get('number')
            if qnum in options_map and options_map[qnum]:
                opts = options_map[qnum]
                q['options'] = opts
                # 同時清理 stem（移除選項文字殘留）
                stem = q.get('stem', '')
                # 移除末尾的選項文字
                for label in ['A', 'B', 'C', 'D']:
                    opt_text = opts.get(label, '')
                    if opt_text and opt_text in stem:
                        stem = stem.replace(opt_text, '').strip()
                # 移除殘留的連結文字（如 "請依下文回答..."）
                if '請依下文回答' in stem:
                    pos = stem.find('請依下文回答')
                    stem = stem[:pos].strip()
                q['stem'] = stem.rstrip(' 、，,.')
                fixed += 1

    save_json(json_path, data)
    log(f'修復 {fixed} 題 options（{json_path}）')
    STATS['p0_1_fixed'] = fixed


def _extract_word_options_from_pdf(lines, qnums):
    """從 PDF 提取單詞型選項（4個詞在一行）"""
    result = {}
    for qnum in qnums:
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(rf'^{qnum}\s', stripped):
                # 向後搜索選項行
                for j in range(i+1, min(i+8, len(lines))):
                    opt_line = lines[j].strip()
                    # 跳過標頭
                    if re.match(r'^(代號|頁次)', opt_line) or re.match(r'^\d{5}', opt_line):
                        continue
                    # 檢查是否為下一題
                    if re.match(r'^\d{1,3}\s', opt_line):
                        break
                    # 嘗試分割為 4 個詞
                    words = opt_line.split()
                    if len(words) == 4 and all(len(w) > 1 for w in words):
                        result[qnum] = {
                            'A': words[0], 'B': words[1],
                            'C': words[2], 'D': words[3]
                        }
                        break
                break
    return result


def _extract_sentence_options_from_pdf(lines, qnums):
    """從 PDF 提取句子型選項（閱讀理解）"""
    result = {}

    for qnum in qnums:
        # 找到題目開始
        q_start = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(rf'^{qnum}\s', stripped):
                q_start = i
                break

        if q_start is None:
            continue

        # 收集題幹和選項
        stem_lines = [lines[q_start].strip()]
        option_lines = []
        in_options = False

        for j in range(q_start + 1, min(q_start + 20, len(lines))):
            stripped = lines[j].strip()
            # 跳過頁面標頭
            if re.match(r'^(代號|頁次)', stripped) or re.match(r'^\d{5}', stripped):
                continue
            if not stripped:
                continue
            # 到下一題了
            if re.match(r'^\d{1,3}\s', stripped):
                next_num = int(re.match(r'^(\d{1,3})', stripped).group(1))
                if next_num > qnum:
                    break
            # 到下一段落
            if re.match(r'^請依下文', stripped):
                break

            # 判斷是否進入選項區域
            # 選項通常在「？」之後
            if not in_options:
                if '?' in ' '.join(stem_lines) or '？' in ' '.join(stem_lines):
                    in_options = True
                    option_lines.append(stripped)
                else:
                    stem_lines.append(stripped)
            else:
                option_lines.append(stripped)

        if not in_options:
            # 沒有找到問號，嘗試用最後幾行作為選項
            all_content = stem_lines[1:]  # 排除題號行
            if len(all_content) >= 4:
                option_lines = all_content[-4:]
                in_options = True

        if option_lines and len(option_lines) >= 4:
            result[qnum] = {
                'A': option_lines[0],
                'B': option_lines[1],
                'C': option_lines[2],
                'D': option_lines[3],
            }
        elif option_lines:
            # 可能選項跨行，嘗試合併
            combined = ' '.join(option_lines)
            # 看看是否能分成 4 段
            parts = re.split(r'(?<=[.。]) (?=[A-Z])', combined)
            if len(parts) >= 4:
                result[qnum] = {
                    'A': parts[0], 'B': parts[1],
                    'C': parts[2], 'D': parts[3],
                }

    return result


# ══════════════════════════════════════════════════════
#  P0-2: 共用科目跨學系缺 options
# ══════════════════════════════════════════════════════

def fix_p0_2_shared_subjects():
    """修復共用科目缺 options

    - 108年 中華民國憲法與警察專業英文 #54（12 個四等學系）
    - 111年 中華民國憲法與警察專業英文 #11（11 個四等學系）
    - 113年 警察法規 #18（10 個四等學系）
    """
    print('\n' + '=' * 60)
    print('P0-2: 修復共用科目跨學系缺 options')
    print('=' * 60)

    total_fixed = 0

    # ── 108年 Q54 ──
    # 從 PDF: 54 operated dissolved overthrown standardized
    q54_options = {'A': 'operated', 'B': 'dissolved', 'C': 'overthrown', 'D': 'standardized'}
    q54_stem = "a definition for self-driving vehicles. Some experts tell CNN Business that the government needs to step in to prevent businesses from misleading and confusing"
    # 注意: Q54 是填空題，stem 是文章上下文；實際填空位置在 passage 中

    for f in sorted(glob.glob(f'{BASE}/*/108年/中華民國憲法與警察專業英文/試題.json')):
        data = load_json(f)
        for q in data['questions']:
            if q.get('number') == 54 and not q.get('options'):
                backup_file(f)
                q['options'] = q54_options.copy()
                save_json(f, data)
                total_fixed += 1
                log(f'108年 Q54 已修復: {f}')
                break

    # ── 111年 Q11 ──
    # 從 PDF: 真正的 Q11 是「關於公務員之懲戒，下列敘述何者錯誤？」
    q11_correct = {
        'stem': '關於公務員之懲戒，下列敘述何者錯誤？',
        'options': {
            'A': '公務員之懲戒屬於司法權',
            'B': '於合理範圍內，公務員之懲戒得以法律規定由公務員之長官行使',
            'C': '依公務人員考績法所為免職之懲處處分，實質上屬於懲戒處分',
            'D': '公務人員對於懲處處分不服，得向懲戒法院請求救濟',
        }
    }

    for f in sorted(glob.glob(f'{BASE}/*/111年/中華民國憲法與警察專業英文/試題.json')):
        data = load_json(f)
        for q in data['questions']:
            if q.get('number') == 11 and not q.get('options'):
                backup_file(f)
                q['stem'] = q11_correct['stem']
                q['options'] = q11_correct['options'].copy()
                save_json(f, data)
                total_fixed += 1
                log(f'111年 Q11 已修復: {f}')
                break

    # ── 113年 Q18 ──
    # stem 中已有 (A)(B)(C)(D) 但被截斷，從 PDF 確認: (D) 是 ①②③④⑤
    q18_options = {
        'A': '僅①②③④',
        'B': '僅①②③',
        'C': '僅①②',
        'D': '①②③④⑤',
    }

    for f in sorted(glob.glob(f'{BASE}/*/113年/警察法規*/試題.json')):
        data = load_json(f)
        for q in data['questions']:
            if q.get('number') == 18 and not q.get('options'):
                backup_file(f)
                # 清理 stem 中的 (A)(B)(C)(D) 部分
                stem = q.get('stem', '')
                pos = stem.find('(A)')
                if pos == -1:
                    pos = stem.find('（A）')
                if pos > 0:
                    q['stem'] = stem[:pos].strip()
                q['options'] = q18_options.copy()
                save_json(f, data)
                total_fixed += 1
                log(f'113年 Q18 已修復: {f}')
                break

    log(f'共修復 {total_fixed} 個檔案')
    STATS['p0_2_fixed'] = total_fixed


# ══════════════════════════════════════════════════════
#  P0-3: 刑事警察系列散落缺 options
# ══════════════════════════════════════════════════════

def fix_p0_3_criminal_police():
    """修復刑事警察系列散落缺 options（18題/8檔）

    這些題目的 stem 中大部分已有 (A)(B)(C)(D) 但被截斷。
    需要從 PDF 提取完整的 (D) 選項。
    """
    print('\n' + '=' * 60)
    print('P0-3: 修復刑事警察系列散落缺 options')
    print('=' * 60)

    # 從 PDF 手動核對的正確選項
    # 格式: (glob_pattern, qnum, options_dict, clean_stem)
    fixes = [
        # 106年 刑案現場 Q17
        (f'{BASE}/刑事警察/106年/刑案現場處理與刑事鑑識/試題.json', 17,
         {'A': '①②④⑤', 'B': '①②③⑤⑥', 'C': '②③④⑤', 'D': '①③④⑥'},
         None),

        # 107年 刑案現場 Q23
        (f'{BASE}/刑事警察/107年/刑案現場處理與刑事鑑識/試題.json', 23,
         {'A': '①②③④⑤', 'B': '②③④⑤', 'C': '①②④⑤', 'D': '②⑤'},
         None),

        # 109年 刑案現場 Q11
        (f'{BASE}/刑事警察/109年/刑案現場處理與刑事鑑識/試題.json', 11,
         {'A': '①②③④⑤', 'B': '④⑤②③①', 'C': '④⑤③②①', 'D': '④⑤②①③'},
         None),

        # 110年 犯罪偵查學 Q7
        (f'{BASE}/刑事警察/110年/犯罪偵查學/試題.json', 7,
         {'A': '①②④⑤', 'B': '①②④', 'C': '③⑤', 'D': '①②③④⑤'},
         None),

        # 110年 犯罪偵查學 Q8
        (f'{BASE}/刑事警察/110年/犯罪偵查學/試題.json', 8,
         {'A': '①②④⑤', 'B': '③④', 'C': '①②③④⑤', 'D': '①②③'},
         None),

        # 110年 犯罪偵查學 Q9
        (f'{BASE}/刑事警察/110年/犯罪偵查學/試題.json', 9,
         {'A': '①②③⑤', 'B': '②③④', 'C': '①④⑤', 'D': '①②③④⑤'},
         None),

        # 110年 犯罪偵查學 Q14
        (f'{BASE}/刑事警察/110年/犯罪偵查學/試題.json', 14,
         {'A': '①②③④⑤', 'B': '③④⑤', 'C': '①②④', 'D': '①③⑤'},
         None),

        # 111年 刑案現場 Q2
        (f'{BASE}/刑事警察/111年/刑案現場處理與刑事鑑識/試題.json', 2,
         {'A': '①②④', 'B': '①③④⑤', 'C': '②③④⑤', 'D': '①②③④⑤'},
         None),

        # 111年 刑案現場 Q11
        (f'{BASE}/刑事警察/111年/刑案現場處理與刑事鑑識/試題.json', 11,
         {'A': '①②⑤', 'B': '③④⑤', 'C': '②③④⑤', 'D': '①②③④⑤'},
         None),

        # 111年 刑案現場 Q17
        (f'{BASE}/刑事警察/111年/刑案現場處理與刑事鑑識/試題.json', 17,
         {'A': '①③④', 'B': '①②③④', 'C': '①②③④⑥', 'D': '①②③④⑤⑥'},
         None),

        # 111年 刑案現場 Q25
        (f'{BASE}/刑事警察/111年/刑案現場處理與刑事鑑識/試題.json', 25,
         {'A': '①②③④⑤', 'B': '僅①②③④', 'C': '僅①②③', 'D': '僅①③④'},
         None),

        # 111年 犯罪偵查學 Q10
        (f'{BASE}/刑事警察/111年/犯罪偵查學/試題.json', 10,
         {'A': '①②③④⑤', 'B': '①②④⑤', 'C': '①②⑤', 'D': '②④⑤'},
         None),

        # 111年 犯罪偵查學 Q16
        (f'{BASE}/刑事警察/111年/犯罪偵查學/試題.json', 16,
         {'A': '①②③④⑤', 'B': '②③④⑤', 'C': '②④⑤', 'D': '②③④'},
         None),

        # 111年 犯罪偵查學 Q22
        (f'{BASE}/刑事警察/111年/犯罪偵查學/試題.json', 22,
         {'A': '①②③④', 'B': '①②③④⑤', 'C': '②③④⑤', 'D': '②③④'},
         None),

        # 113年 刑案現場 Q2
        (f'{BASE}/刑事警察/113年/刑案現場處理與刑事鑑識/試題.json', 2,
         {'A': '①③⑤', 'B': '③④⑤', 'C': '①②④⑤', 'D': '①②③④⑤'},
         None),

        # 113年 刑案現場 Q6
        (f'{BASE}/刑事警察/113年/刑案現場處理與刑事鑑識/試題.json', 6,
         {'A': '①③④⑤②', 'B': '①④③⑤②', 'C': '①④③②⑤', 'D': '①③④②⑤'},
         None),

        # 114年 刑案現場 Q7
        (f'{BASE}/刑事警察/114年/刑案現場處理與刑事鑑識/試題.json', 7,
         {'A': '①②', 'B': '①②③', 'C': '②③④', 'D': '①②③④⑤'},
         None),

        # 114年 刑案現場 Q11
        (f'{BASE}/刑事警察/114年/刑案現場處理與刑事鑑識/試題.json', 11,
         {'A': '①②③④⑤', 'B': '②③④⑤', 'C': '③④⑤', 'D': '②③④'},
         None),
    ]

    total_fixed = 0
    files_fixed = set()

    for filepath, qnum, options, clean_stem in fixes:
        if not os.path.exists(filepath):
            log(f'找不到: {filepath}')
            continue

        data = load_json(filepath)
        for q in data['questions']:
            if q.get('number') == qnum and not q.get('options'):
                if filepath not in files_fixed:
                    backup_file(filepath)
                    files_fixed.add(filepath)

                # 清理 stem 中的 (A)(B)(C)(D)
                stem = q.get('stem', '')
                pos = stem.find('(A)')
                if pos == -1:
                    pos = stem.find('（A）')
                if pos > 0:
                    q['stem'] = stem[:pos].strip()

                if clean_stem:
                    q['stem'] = clean_stem

                q['options'] = options.copy()
                total_fixed += 1
                break

        save_json(filepath, data)

    log(f'修復 {total_fixed} 題（{len(files_fixed)} 個檔案）')
    STATS['p0_3_fixed'] = total_fixed


# ══════════════════════════════════════════════════════
#  P0-4: 其他個別檔案缺 options
# ══════════════════════════════════════════════════════

def fix_p0_4_individual():
    """修復其他個別檔案缺 options"""
    print('\n' + '=' * 60)
    print('P0-4: 修復其他個別檔案缺 options')
    print('=' * 60)

    total_fixed = 0

    # ── 水上警察 109年 情境實務 Q2 → 圖片型選項 ──
    for f in glob.glob(f'{BASE}/水上警察/109年/水上警察情境實務*/試題.json'):
        data = load_json(f)
        for q in data['questions']:
            if q.get('number') == 2 and not q.get('options'):
                backup_file(f)
                q['options'] = {
                    'A': '[圖片選項]',
                    'B': '[圖片選項]',
                    'C': '[圖片選項]',
                    'D': '[圖片選項]',
                }
                q['_note'] = '選項為拖帶方式示意圖，無法從 PDF 文字提取'
                save_json(f, data)
                total_fixed += 1
                log(f'水上警察 109年 Q2 標記為圖片選項: {f}')
                break

    # ── 消防警察 113年 消防與災害防救法規 Q4,Q5,Q10,Q18,Q19 ──
    fire_fixes = {
        4:  {'A': '①③④', 'B': '①②③④', 'C': '①②④⑤', 'D': '①②③④⑤'},
        5:  {'A': '①②④', 'B': '①③⑤', 'C': '①②④⑤', 'D': '①②③④⑤'},
        10: {'A': '①②③', 'B': '①②③⑤', 'C': '①②④⑤', 'D': '①②③④⑤'},
        18: {'A': '①②④', 'B': '①③⑤', 'C': '①②③④', 'D': '①②③④⑤'},
        19: {'A': '①②③', 'B': '①③⑤', 'C': '①②④', 'D': '①②③④⑤'},
    }

    for f in glob.glob(f'{BASE}/消防警察/113年/消防與災害防救法規*/試題.json'):
        data = load_json(f)
        backed_up = False
        for q in data['questions']:
            qnum = q.get('number')
            if qnum in fire_fixes and not q.get('options'):
                if not backed_up:
                    backup_file(f)
                    backed_up = True
                stem = q.get('stem', '')
                pos = stem.find('(A)')
                if pos == -1:
                    pos = stem.find('（A）')
                if pos > 0:
                    q['stem'] = stem[:pos].strip()
                q['options'] = fire_fixes[qnum].copy()
                total_fixed += 1
        if backed_up:
            save_json(f, data)
            log(f'消防與災害防救法規 修復 {sum(1 for q in data["questions"] if q.get("number") in fire_fixes and q.get("options"))} 題: {f}')

    # ── 消防警察 113年 情境實務 Q20 → 可能為圖片選項 ──
    for f in glob.glob(f'{BASE}/消防警察/113年/消防警察情境實務*/試題.json'):
        data = load_json(f)
        for q in data['questions']:
            if q.get('number') == 20 and not q.get('options'):
                backup_file(f)
                # PDF 中 Q20 選項為空白，可能是圖片型
                q['options'] = {
                    'A': '[圖片選項]',
                    'B': '[圖片選項]',
                    'C': '[圖片選項]',
                    'D': '[圖片選項]',
                }
                q['_note'] = '選項可能為圖表型，無法從 PDF 文字提取'
                save_json(f, data)
                total_fixed += 1
                log(f'消防情境 113年 Q20 標記為圖片選項: {f}')
                break

    # ── 鑑識科學 106年 犯罪偵查 Q47 ──
    for f in glob.glob(f'{BASE}/鑑識科學/106年/犯罪偵查/試題.json'):
        data = load_json(f)
        for q in data['questions']:
            if q.get('number') == 47 and not q.get('options'):
                backup_file(f)
                stem = q.get('stem', '')
                pos = stem.find('(A)')
                if pos == -1:
                    pos = stem.find('（A）')
                if pos > 0:
                    q['stem'] = stem[:pos].strip()
                q['options'] = {
                    'A': '①③④②⑤',
                    'B': '①③②④⑤',
                    'C': '③①②④⑤',
                    'D': '③①④②⑤',
                }
                save_json(f, data)
                total_fixed += 1
                log(f'鑑識科學 106年 Q47 已修復: {f}')
                break

    # ── 鑑識科學 108年 犯罪偵查 Q3 ──
    for f in glob.glob(f'{BASE}/鑑識科學/108年/犯罪偵查/試題.json'):
        data = load_json(f)
        for q in data['questions']:
            if q.get('number') == 3 and not q.get('options'):
                backup_file(f)
                stem = q.get('stem', '')
                pos = stem.find('(A)')
                if pos == -1:
                    pos = stem.find('（A）')
                if pos > 0:
                    q['stem'] = stem[:pos].strip()
                q['options'] = {
                    'A': '①②③④⑤',
                    'B': '②③④⑤',
                    'C': '①②③⑤',
                    'D': '①②④⑤',
                }
                save_json(f, data)
                total_fixed += 1
                log(f'鑑識科學 108年 Q3 已修復: {f}')
                break

    # ── 水上警察 106年 Q54 ──
    for f in glob.glob(f'{BASE}/水上警察/106年/中華民國憲法與水上警察專業英文/試題.json'):
        data = load_json(f)
        for q in data['questions']:
            if q.get('number') == 54 and not q.get('options'):
                backup_file(f)
                q['options'] = {
                    'A': 'cargo',
                    'B': 'fishing',
                    'C': 'naval',
                    'D': 'recreational',
                }
                save_json(f, data)
                total_fixed += 1
                log(f'水上警察 106年 Q54 已修復: {f}')
                break

    log(f'共修復 {total_fixed} 題')
    STATS['p0_4_fixed'] = total_fixed


# ══════════════════════════════════════════════════════
#  P1-1: 海巡法規 Q8 缺 D 選項
# ══════════════════════════════════════════════════════

def fix_p1_haijun_q8():
    """修復 水上警察 108年 海巡法規 Q8 缺 D 選項

    水上警察學系版有完整的 Q8（含 D 選項和正確 stem），
    用它來修復水上警察版。
    """
    print('\n' + '=' * 60)
    print('P1-1: 修復海巡法規 Q8 缺 D 選項')
    print('=' * 60)

    # 讀取完整版（水上警察學系）
    source_files = glob.glob(f'{BASE}/水上警察學系/108年/海巡*/*.json')
    if not source_files:
        log('找不到來源（水上警察學系版）')
        return

    source_data = load_json(source_files[0])
    source_q8 = None
    for q in source_data['questions']:
        if q.get('number') == 8:
            source_q8 = q
            break

    if not source_q8:
        log('來源中找不到 Q8')
        return

    # 修復目標（水上警察版）
    target_files = glob.glob(f'{BASE}/水上警察/108年/海巡*/*.json')
    fixed = 0
    for f in target_files:
        data = load_json(f)
        for q in data['questions']:
            if q.get('number') == 8:
                opts = q.get('options', {})
                if 'D' not in opts:
                    backup_file(f)
                    q['stem'] = source_q8['stem']
                    q['options'] = copy.deepcopy(source_q8['options'])
                    save_json(f, data)
                    fixed += 1
                    log(f'已修復: {f}')
                break

    STATS['p1_haijun_fixed'] = fixed


# ══════════════════════════════════════════════════════
#  P1-2: 114年缺 essay 題（從 PDF 重新解析）
# ══════════════════════════════════════════════════════

def fix_p1_114_missing_essays():
    """修復 114年 28 個檔案缺 essay 題

    這些檔案的 notes 提到申論/作文/公文，但 questions 中只有 choice 題。
    需要從 PDF 重新解析 essay 題。
    """
    print('\n' + '=' * 60)
    print('P1-2: 修復 114年缺 essay 題')
    print('=' * 60)

    if not pdfplumber:
        log('需要 pdfplumber 來處理此問題')
        return

    fixed_files = 0
    fixed_essays = 0

    for f in sorted(glob.glob(f'{BASE}/*/114年/*/試題.json')):
        data = load_json(f)
        notes = data.get('notes', [])
        notes_text = ' '.join(notes) if isinstance(notes, list) else str(notes)
        questions = data.get('questions', [])
        essay_qs = [q for q in questions if q.get('type') == 'essay']

        has_essay_mention = '申論' in notes_text or '作文' in notes_text or '公文' in notes_text
        if not has_essay_mention or essay_qs:
            continue

        # 找對應 PDF
        json_dir = os.path.dirname(f)
        pdf_path = os.path.join(json_dir, '試題.pdf')
        if not os.path.exists(pdf_path):
            log(f'找不到 PDF: {pdf_path}')
            continue

        # 從 PDF 提取 essay
        essays = _extract_essays_from_pdf(pdf_path)
        if not essays:
            log(f'PDF 中未找到申論題: {f}')
            continue

        backup_file(f)

        # 加入 essay 題目到 questions 最前面（申論題在選擇題之前）
        choice_qs = [q for q in questions if q.get('type') == 'choice']
        data['questions'] = essays + choice_qs

        save_json(f, data)
        fixed_files += 1
        fixed_essays += len(essays)
        log(f'添加 {len(essays)} 題 essay: {f}')

    log(f'共修復 {fixed_files} 個檔案，添加 {fixed_essays} 題 essay')
    STATS['p1_114_files'] = fixed_files
    STATS['p1_114_essays'] = fixed_essays


def _extract_essays_from_pdf(pdf_path):
    """從 114年 PDF 中提取申論題"""
    full_text = extract_pdf_text(pdf_path)
    lines = full_text.split('\n')

    essays = []
    in_essay_section = False
    current_essay = None

    # 中文數字
    cn_nums = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
    essay_pattern = re.compile(r'^\s*([一二三四五六七八九十]+)\s*[、．.]\s*(.+)')
    section_pattern = re.compile(r'^\s*(甲|乙)\s*[、．.]\s*(申論|測驗|選擇)')

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 檢查分段
        section_match = section_pattern.match(stripped)
        if section_match:
            if '申論' in section_match.group(2):
                in_essay_section = True
            elif '測驗' in section_match.group(2) or '選擇' in section_match.group(2):
                in_essay_section = False
                if current_essay:
                    essays.append(current_essay)
                    current_essay = None
            continue

        # 處理特殊格式：「英文作文」「英文作文：」等
        if re.match(r'^\s*英文作文\s*[：:]?', stripped) and not current_essay:
            in_essay_section = True
            # 以下內容為作文題幹
            current_essay = {
                'number': cn_nums[len(essays)] if len(essays) < len(cn_nums) else str(len(essays) + 1),
                'type': 'essay',
                'stem': stripped,
                'section': '甲、申論題',
            }
            continue

        # 處理作文題（notes 中包含的題幹）
        if re.match(r'^\s*作文[:：]?\s*[\(（]', stripped):
            current_essay = {
                'number': cn_nums[len(essays)] if len(essays) < len(cn_nums) else str(len(essays) + 1),
                'type': 'essay',
                'stem': stripped,
                'section': '甲、申論題',
            }
            continue

        # 標準申論題格式
        if in_essay_section:
            essay_match = essay_pattern.match(stripped)
            if essay_match:
                if current_essay:
                    essays.append(current_essay)

                num_str = essay_match.group(1)
                stem = essay_match.group(2).strip()
                current_essay = {
                    'number': num_str,
                    'type': 'essay',
                    'stem': stem,
                    'section': '甲、申論題',
                }
                continue

            # 延續當前 essay stem
            if current_essay:
                # 排除標頭行
                if any(kw in stripped for kw in ['代號', '頁次', '考試別', '等別', '類科']):
                    continue
                if re.match(r'^\d{5}', stripped) and len(stripped) < 20:
                    continue
                # 遇到測驗題開始就停止
                if re.match(r'^\d{1,3}\s+', stripped):
                    # 這是選擇題，結束 essay
                    essays.append(current_essay)
                    current_essay = None
                    in_essay_section = False
                    continue
                current_essay['stem'] += '\n' + stripped

    if current_essay:
        essays.append(current_essay)

    return essays


# ══════════════════════════════════════════════════════
#  P1-3: 申論題號重複（結構問題）
# ══════════════════════════════════════════════════════

def fix_p1_essay_duplicates():
    """修復申論題號重複

    108年國文（作文、公文與測驗）中，作文和公文各自用「一」「二」編號，
    但 PDF 解析時把作文的背景資料段落也當成了新的申論題。
    需要合併重複的題目。
    """
    print('\n' + '=' * 60)
    print('P1-3: 修復申論題號重複')
    print('=' * 60)

    fixed_files = 0

    for f in sorted(glob.glob(f'{BASE}/**/試題.json', recursive=True)):
        data = load_json(f)
        essay_qs = [q for q in data['questions'] if q.get('type') == 'essay']
        if not essay_qs:
            continue

        # 檢查重複
        from collections import Counter
        nums = [q.get('number') for q in essay_qs]
        counter = Counter(nums)
        dups = {n: c for n, c in counter.items() if c > 1}

        if not dups:
            continue

        # 對於每個重複的題號，合併 stem
        backup_file(f)
        modified = False

        for dup_num in dups:
            dup_essays = [q for q in essay_qs if q.get('number') == dup_num]
            if len(dup_essays) < 2:
                continue

            # 保留第一個，將後續的 stem 合併進去
            primary = dup_essays[0]
            for secondary in dup_essays[1:]:
                secondary_stem = secondary.get('stem', '')
                if secondary_stem and secondary_stem not in primary.get('stem', ''):
                    primary['stem'] = primary['stem'] + '\n\n' + secondary_stem
                # 從 questions 中移除 secondary
                data['questions'].remove(secondary)
                modified = True

        if modified:
            save_json(f, data)
            fixed_files += 1
            log(f'合併重複申論題: {f} ({dups})')

    log(f'共修復 {fixed_files} 個檔案')
    STATS['p1_essay_dup_fixed'] = fixed_files


# ══════════════════════════════════════════════════════
#  P2-1: answer='*' 改為 '送分'
# ══════════════════════════════════════════════════════

def fix_p2_star_answers():
    """將 answer='*' 統一改為 '送分'"""
    print('\n' + '=' * 60)
    print('P2-1: 將 answer="*" 改為 "送分"')
    print('=' * 60)

    fixed = 0
    files_fixed = 0

    for f in sorted(glob.glob(f'{BASE}/**/試題.json', recursive=True)):
        data = load_json(f)
        modified = False
        for q in data.get('questions', []):
            if q.get('answer') == '*':
                if not modified:
                    backup_file(f)
                    modified = True
                q['answer'] = '送分'
                fixed += 1
        if modified:
            save_json(f, data)
            files_fixed += 1

    log(f'修復 {fixed} 題 answer（{files_fixed} 個檔案）')
    STATS['p2_star_fixed'] = fixed


# ══════════════════════════════════════════════════════
#  P2-2: 申論 stem 殘留 metadata
# ══════════════════════════════════════════════════════

def fix_p2_metadata_residual():
    """清理申論 stem 中殘留的考試 metadata"""
    print('\n' + '=' * 60)
    print('P2-2: 清理申論 stem 殘留 metadata')
    print('=' * 60)

    patterns_to_clean = [
        (re.compile(r'\s*乙、測驗題.*$', re.DOTALL), ''),
        (re.compile(r'\s*代號[:：]\s*\d+.*$', re.DOTALL), ''),
        (re.compile(r'\s*頁次[:：]\s*\d.*$', re.DOTALL), ''),
        (re.compile(r'\s*背面尚有試題.*$', re.DOTALL), ''),
        (re.compile(r'\s*請接背面.*$', re.DOTALL), ''),
        (re.compile(r'\s*全\s*一\s*張.*$', re.DOTALL), ''),
    ]

    fixed = 0
    files_fixed = 0

    for f in sorted(glob.glob(f'{BASE}/**/試題.json', recursive=True)):
        data = load_json(f)
        modified = False

        for q in data.get('questions', []):
            if q.get('type') != 'essay':
                continue
            stem = q.get('stem', '')
            if not stem:
                continue

            original = stem
            for pattern, replacement in patterns_to_clean:
                stem = pattern.sub(replacement, stem)

            stem = stem.rstrip()
            if stem != original:
                if not modified:
                    backup_file(f)
                    modified = True
                q['stem'] = stem
                fixed += 1

        if modified:
            save_json(f, data)
            files_fixed += 1

    log(f'清理 {fixed} 題 metadata（{files_fixed} 個檔案）')
    STATS['p2_metadata_fixed'] = fixed


# ══════════════════════════════════════════════════════
#  P0 補充: 處理 stem 中內嵌的 (A)(B)(C)(D) 但未提取的題目
# ══════════════════════════════════════════════════════

def fix_remaining_embedded_options():
    """掃描所有仍缺 options 的選擇題，嘗試從 stem 中提取 (A)(B)(C)(D)"""
    print('\n' + '=' * 60)
    print('補充: 處理 stem 中殘留的內嵌選項')
    print('=' * 60)

    option_pattern = re.compile(
        r'[\(（]([A-Da-d])[\)）]\s*(.+?)(?=\s*[\(（][A-Da-d][\)）]|\s*$)',
        re.DOTALL
    )

    fixed = 0
    files_fixed = 0

    for f in sorted(glob.glob(f'{BASE}/**/試題.json', recursive=True)):
        data = load_json(f)
        modified = False

        for q in data.get('questions', []):
            if q.get('type') == 'choice' and not q.get('options'):
                stem = q.get('stem', '')
                matches = option_pattern.findall(stem)
                if len(matches) >= 3:  # 至少 3 個選項（有些 D 可能被截斷）
                    if not modified:
                        backup_file(f)
                        modified = True

                    # 從 stem 中分離選項
                    for marker in ['(A)', '（A）']:
                        pos = stem.find(marker)
                        if pos > 0:
                            q['stem'] = stem[:pos].strip()
                            break

                    q['options'] = {}
                    for letter, text in matches:
                        q['options'][letter.upper()] = text.strip()

                    fixed += 1

        if modified:
            save_json(f, data)
            files_fixed += 1

    log(f'修復 {fixed} 題內嵌選項（{files_fixed} 個檔案）')
    STATS['embedded_fixed'] = fixed


# ══════════════════════════════════════════════════════
#  主程式
# ══════════════════════════════════════════════════════

if __name__ == '__main__':
    os.makedirs(BACKUP_DIR, exist_ok=True)
    print(f'備份目錄: {BACKUP_DIR}')
    print(f'開始二次審計修復...\n')

    # P0: 嚴重問題
    fix_p0_1_english_40()
    fix_p0_2_shared_subjects()
    fix_p0_3_criminal_police()
    fix_p0_4_individual()

    # P0 補充
    fix_remaining_embedded_options()

    # P1: 中度問題
    fix_p1_haijun_q8()
    fix_p1_114_missing_essays()
    fix_p1_essay_duplicates()

    # P2: 輕微問題
    fix_p2_star_answers()
    fix_p2_metadata_residual()

    # 統計
    print('\n' + '=' * 60)
    print('修復統計')
    print('=' * 60)
    for key, val in sorted(STATS.items()):
        print(f'  {key}: {val}')

    # 儲存統計
    stats_path = 'fix_round2_stats.json'
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(dict(STATS), f, ensure_ascii=False, indent=2)
    print(f'\n統計已儲存: {stats_path}')
    print(f'備份目錄: {BACKUP_DIR}')
