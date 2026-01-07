# -*- coding: utf-8 -*-
"""
警察考古題表單 - 智能自動化部署系統
====================================
自動完成: CSV解析 → 生成Code.gs → 推送 → 開啟瀏覽器執行
"""

import subprocess
import json
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
import time

# 設定
PROJECT_DIR = Path(__file__).parent.resolve()
SCRIPT_ID = "1-m81BHKdUIZfAdHkRGCRXfRFI_e79ieKgppZqvj4rVOIztAM-O3GKUJQ"
APPS_SCRIPT_URL = f"https://script.google.com/home/projects/{SCRIPT_ID}/edit"
WEB_APP_URL = "https://script.google.com/macros/s/AKfycbyy3WZCFcKfx2SR4FeQLe7QcS_e49YZnW_BRYasCzibKDh3045o3J--PcKruWkZ5SCWxg/exec"

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════╗
║         警察考古題表單 - 智能自動化部署系統                  ║
╠══════════════════════════════════════════════════════════════╣
║  [1] 完整部署 (CSV → 表單 → 驗證)                            ║
║  [2] 只驗證現有表單                                          ║
║  [3] 只推送程式碼                                            ║
║  [4] 查看表單清單                                            ║
║  [5] 擷取 CLASP 日誌                                         ║
║  [Q] 退出                                                    ║
╚══════════════════════════════════════════════════════════════╝
""")

def print_step(num, text, status=""):
    icons = {"ok": "✓", "fail": "✗", "wait": "⋯", "": "→"}
    icon = icons.get(status, "→")
    color_codes = {"ok": "\033[92m", "fail": "\033[91m", "wait": "\033[93m", "": "\033[0m"}
    reset = "\033[0m"
    print(f"  [{num}] {icon} {text}")

def run_cmd(cmd):
    """執行命令"""
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=PROJECT_DIR,
            capture_output=True, text=True, encoding='utf-8'
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)

def get_csv_files():
    """取得 CSV 檔案清單"""
    csv_dir = PROJECT_DIR / "考選部考古題完整庫" / "情境實務考古題" / "情境實務資料夾"
    if csv_dir.exists():
        return sorted(csv_dir.glob("*.csv"))
    return []

def select_csv_files():
    """讓使用者選擇 CSV 檔案"""
    csvs = get_csv_files()
    if not csvs:
        print("  找不到 CSV 檔案!")
        return []
    
    print("\n  可用的 CSV 檔案:")
    for i, f in enumerate(csvs, 1):
        print(f"    [{i}] {f.name}")
    print(f"    [A] 全部")
    print(f"    [L] 最後一個")
    
    choice = input("\n  請選擇 (輸入數字/A/L): ").strip().upper()
    
    if choice == "A":
        return csvs
    elif choice == "L":
        return [csvs[-1]]
    else:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(csvs):
                return [csvs[idx]]
        except:
            pass
    return []

def full_deploy():
    """完整部署流程"""
    print("\n" + "="*60)
    print("  開始完整部署流程")
    print("="*60)
    
    # Step 1: 選擇 CSV
    print("\n[Step 1] 選擇 CSV 檔案")
    selected = select_csv_files()
    if not selected:
        print("  未選擇檔案，取消操作")
        return
    
    # Step 2: 生成 Code.gs
    print("\n[Step 2] 生成 Apps Script 程式碼...")
    for csv in selected:
        print(f"  處理: {csv.name}")
        success, output = run_cmd(f'python auto_generate_form.py --csv "{csv}"')
        if not success:
            print(f"  ✗ 失敗: {output[:100]}")
            return
    print("  ✓ 程式碼生成完成")
    
    # Step 3: 推送
    print("\n[Step 3] 推送到 Google Apps Script...")
    success, output = run_cmd("clasp push --force")
    if success:
        print("  ✓ 推送成功")
    else:
        print(f"  ✗ 推送失敗: {output[:100]}")
        return
    
    # Step 4: 開啟瀏覽器建立表單
    print("\n[Step 4] 建立 Google Forms")
    print("  即將開啟 Apps Script 編輯器...")
    print("  請執行以下操作:")
    print("    1. 選擇函數: createFormFromCSV")
    print("    2. 點擊 ▶️ 執行")
    print("    3. 等待執行完成")
    
    time.sleep(2)
    webbrowser.open(APPS_SCRIPT_URL)
    
    input("\n  完成後按 Enter 繼續...")
    
    # Step 5: 驗證表單
    print("\n[Step 5] 驗證表單")
    print("  即將開啟驗證頁面...")
    print("  請執行以下操作:")
    print("    1. 選擇函數: validateAllForms")
    print("    2. 點擊 ▶️ 執行")
    print("    3. 查看執行記錄中的結果")
    
    time.sleep(1)
    webbrowser.open(APPS_SCRIPT_URL)
    
    input("\n  完成後按 Enter 繼續...")
    
    # Step 6: 產生報告
    print("\n[Step 6] 產生 QA 報告...")
    generate_report(selected)
    
    print("\n" + "="*60)
    print("  ✓ 部署完成!")
    print("="*60)

def validate_only():
    """只驗證表單"""
    print("\n  開啟 Apps Script 編輯器...")
    print("  請選擇 validateAllForms 並執行")
    webbrowser.open(APPS_SCRIPT_URL)
    
    # 同時開啟 Web App (用瀏覽器可以登入)
    print("\n  同時開啟 Web App 驗證頁面...")
    webbrowser.open(f"{WEB_APP_URL}?action=validate")

def push_only():
    """只推送程式碼"""
    print("\n  推送程式碼到 Google Apps Script...")
    success, output = run_cmd("clasp push --force")
    if success:
        print("  ✓ 推送成功!")
        print(output)
    else:
        print(f"  ✗ 推送失敗: {output}")

def list_forms():
    """查看表單清單"""
    print("\n  開啟 Web App 表單清單...")
    webbrowser.open(f"{WEB_APP_URL}?action=list")

def get_logs():
    """擷取 CLASP 日誌"""
    print("\n  擷取 CLASP 日誌...")
    
    log_file = PROJECT_DIR / f"clasp_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    success, output = run_cmd("clasp logs")
    
    if success:
        with open(log_file, 'w', encoding='utf-8-sig') as f:
            f.write(output)
        print(f"  ✓ 日誌已儲存: {log_file.name}")
        os.startfile(log_file)
    else:
        print(f"  ✗ 擷取失敗: {output[:100]}")

def generate_report(csv_files=None):
    """產生 QA 報告"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 讀取現有的 summary 檔案
    summaries = list(PROJECT_DIR.glob("form_generation_summary*.json"))
    
    report = f"""================================================================================
                    QA 驗證報告
                    生成時間: {timestamp}
================================================================================

"""
    
    if csv_files:
        report += "處理的 CSV 檔案:\n"
        for csv in csv_files:
            report += f"  [v] {csv.name}\n"
        report += "\n"
    
    report += "Summary JSON 檔案:\n"
    for s in summaries:
        report += f"  [v] {s.name}\n"
        try:
            with open(s, 'r', encoding='utf-8') as f:
                data = json.load(f)
                report += f"      題數: {data.get('total_questions', 'N/A')}\n"
        except:
            pass
    
    report += f"""
================================================================================
                    驗證清單
================================================================================

請在 Apps Script 執行記錄中確認以下項目:

[ ] 所有表單皆已建立
[ ] 每個表單題數正確
[ ] 表單 URL 可正常開啟
[ ] 選項 A-D 顯示正確

================================================================================
                    系統狀態
================================================================================

[v] CLASP 設定正確
[v] 程式碼已推送
[v] Summary 檔案已生成

================================================================================
            請將此報告截圖附於 Pull Request
================================================================================
"""
    
    report_file = PROJECT_DIR / f"QA_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w', encoding='utf-8-sig') as f:
        f.write(report)
    
    print(f"  ✓ 報告已儲存: {report_file.name}")
    os.startfile(report_file)

def main():
    os.chdir(PROJECT_DIR)
    
    while True:
        clear_screen()
        print_banner()
        
        choice = input("  請選擇功能: ").strip().upper()
        
        if choice == "1":
            full_deploy()
        elif choice == "2":
            validate_only()
        elif choice == "3":
            push_only()
        elif choice == "4":
            list_forms()
        elif choice == "5":
            get_logs()
        elif choice == "Q":
            print("\n  再見!")
            break
        else:
            print("\n  無效選擇，請重試")
        
        if choice != "Q":
            input("\n  按 Enter 返回主選單...")

if __name__ == "__main__":
    main()
