#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copilot CLI エージェント定義の検証スクリプト

各エージェント定義ファイル（.instructions.md）が正確に記述されているか、
必要なセクション・キーワードが含まれているかを検証します。
"""

import os
import json
import re
import sys
from pathlib import Path

# Windows環境での文字コード対応
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# プロジェクトルート
PROJECT_ROOT = Path(__file__).parent
INSTRUCTIONS_DIR = PROJECT_ROOT / ".github" / "instructions"

# 各エージェントに期待される定義ファイル
EXPECTED_AGENTS = [
    "orchestrator",
    "box-research",
    "algorithm-research",
    "algorithm-programmer",
    "test-programmer",
    "tester",
    "visualizer",
    "supervisor"
]

# 各エージェント定義に必須のセクション
REQUIRED_SECTIONS = {
    "ロール・責務",
    "主要入力ファイル",
    "主要出力ファイル",
    "利用可能なツール",
    "行動指針"
}

def check_instruction_files():
    """エージェント定義ファイルの存在と整合性を確認"""
    print("=" * 60)
    print("Copilot CLI エージェント定義ファイル検証")
    print("=" * 60)
    
    results = []
    
    for agent_name in EXPECTED_AGENTS:
        file_path = INSTRUCTIONS_DIR / f"{agent_name}.instructions.md"
        
        print(f"\n📋 {agent_name}.instructions.md")
        
        # ファイル存在確認
        if not file_path.exists():
            print(f"  ❌ ファイルが見つかりません: {file_path}")
            results.append((agent_name, False, "ファイルなし"))
            continue
        
        print(f"  ✅ ファイル存在: {file_path}")
        
        # ファイル内容を読み込み
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"  ❌ ファイル読み込みエラー: {e}")
            results.append((agent_name, False, "読み込みエラー"))
            continue
        
        # 必須セクション確認
        missing_sections = []
        for section in REQUIRED_SECTIONS:
            if section not in content:
                missing_sections.append(section)
        
        if missing_sections:
            print(f"  ⚠️  欠落セクション: {', '.join(missing_sections)}")
            results.append((agent_name, False, f"欠落: {len(missing_sections)}セクション"))
        else:
            print(f"  ✅ 全必須セクション確認: {len(REQUIRED_SECTIONS)}/{ len(REQUIRED_SECTIONS)}")
            results.append((agent_name, True, "OK"))
        
        # 内容の簡易検証
        line_count = len(content.split('\n'))
        print(f"  📄 行数: {line_count}")
        
        # ロール・責務の行数確認（最低限の内容があるか）
        if "ロール・責務" in content:
            role_section = content.split("ロール・責務")[1].split("###")[0] if "###" in content.split("ロール・責務")[1] else content.split("ロール・責務")[1]
            role_lines = len(role_section.split('\n'))
            print(f"  📝 ロール定義の行数: {role_lines}")
    
    print("\n" + "=" * 60)
    print("検証結果サマリー")
    print("=" * 60)
    
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    
    print(f"\n✅ 成功: {passed}/{total}")
    
    for agent_name, ok, status in results:
        symbol = "✅" if ok else "❌"
        print(f"{symbol} {agent_name}: {status}")
    
    return passed == total

def check_constraints_compatibility():
    """constraints.md が Copilot CLI で理解可能か確認"""
    print("\n" + "=" * 60)
    print("constraints/constraints.md 互換性確認")
    print("=" * 60)
    
    constraints_file = PROJECT_ROOT / "constraints" / "constraints.md"
    
    if not constraints_file.exists():
        print(f"❌ constraints.md が見つかりません")
        return False
    
    with open(constraints_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 重要なセクション確認
    important_sections = [
        "パレットおよび積載領域",
        "積載高さ",
        "嵌合",
        "段積み",
        "回転角度"
    ]
    
    print("\n必須制約項目の確認:")
    all_found = True
    for section in important_sections:
        if section in content:
            print(f"  ✅ {section}")
        else:
            print(f"  ❌ {section}")
            all_found = False
    
    # 数値制約の確認
    print("\n数値制約の確認:")
    constraints = {
        "1200": "最大積載高さ（mm）",
        "1360": "長辺オーバーハング（mm）",
        "800": "短辺最小（mm）",
        "1100": "短辺最大（mm）"
    }
    
    for value, description in constraints.items():
        if value in content:
            print(f"  ✅ {description}: {value}mm")
        else:
            print(f"  ❌ {description}: {value}mm")
            all_found = False
    
    return all_found

def check_data_schemas():
    """既存データスキーマの互換性確認"""
    print("\n" + "=" * 60)
    print("データスキーマ互換性確認")
    print("=" * 60)
    
    # box_db.json 確認
    box_db_file = PROJECT_ROOT / "box_research" / "box_db.json"
    
    print("\n📦 box_db.json 確認:")
    if box_db_file.exists():
        with open(box_db_file, 'r', encoding='utf-8') as f:
            box_db = json.load(f)
        
        print(f"  ✅ ファイル存在")
        print(f"  📊 登録箱数: {len(box_db)}")
        
        # 各箱のスキーマ確認
        required_fields = {"id", "width", "length", "height", "fitting_depth", "rib_thickness"}
        
        all_valid = True
        for box_id, box_data in box_db.items():
            missing = required_fields - set(box_data.keys())
            if missing:
                print(f"  ⚠️  {box_id}: 欠落フィールド {missing}")
                all_valid = False
        
        if all_valid:
            print(f"  ✅ 全箱が必須フィールドを保有")
        
        # モジュール比率の確認
        module_ratios = set(box.get("module_ratio", "N/A") for box in box_db.values())
        print(f"  🔹 モジュール比率: {module_ratios}")
        
        return True
    else:
        print(f"  ❌ ファイルが見つかりません: {box_db_file}")
        return False

def check_directory_structure():
    """プロジェクトディレクトリ構造の確認"""
    print("\n" + "=" * 60)
    print("プロジェクトディレクトリ構造確認")
    print("=" * 60)
    
    required_dirs = [
        "constraints",
        "box_research",
        "algorithm_research",
        "algorithm_programmer",
        "test_programmer",
        "tester",
        "visualizer",
        "supervisor",
        ".github/instructions"
    ]
    
    print("\nディレクトリ確認:")
    all_exist = True
    for dir_name in required_dirs:
        dir_path = PROJECT_ROOT / dir_name
        if dir_path.exists():
            print(f"  ✅ {dir_name}/")
        else:
            print(f"  ❌ {dir_name}/ （欠落）")
            all_exist = False
    
    return all_exist

def main():
    """メイン検証実行"""
    
    print("\n🔍 Copilot CLI 移行準備状況の検証\n")
    
    results = {
        "instruction_files": check_instruction_files(),
        "constraints": check_constraints_compatibility(),
        "data_schemas": check_data_schemas(),
        "directories": check_directory_structure()
    }
    
    print("\n" + "=" * 60)
    print("総合検証結果")
    print("=" * 60)
    
    all_passed = all(results.values())
    
    for check_name, passed in results.items():
        symbol = "✅" if passed else "⚠️"
        print(f"{symbol} {check_name}: {'PASS' if passed else 'FAIL'}")
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 フェーズ5 準備完了！")
        print("次のステップ: 各エージェントを Copilot CLI で実行してください")
        print("\n  cd palletizing_prototype")
        print("  gh copilot")
        print("  /agent orchestrator")
    else:
        print("⚠️  問題が検出されました。修正してください。")
    
    print("=" * 60 + "\n")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
