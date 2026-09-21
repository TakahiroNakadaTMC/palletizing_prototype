#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tester: テスト実行サマリー生成スクリプト

既存の tester/results/*.json から test_summary.md を自動生成
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Windows環境での文字コード対応
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def generate_test_summary():
    """テスト結果から test_summary.md を生成"""
    project_root = Path(__file__).parent
    results_dir = project_root / 'tester' / 'results'
    
    if not results_dir.exists():
        print(f"❌ {results_dir} が見つかりません")
        return False
    
    # 結果ファイルの読み込み
    results = []
    for result_file in sorted(results_dir.glob('result_*.json')):
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
                results.append(result_data)
        except Exception as e:
            print(f"⚠️  {result_file.name} の読み込みエラー: {e}")
    
    if not results:
        print(f"❌ テスト結果ファイルが見つかりません")
        return False
    
    print(f"✅ {len(results)} 個のテスト結果を読み込み\n")
    
    # test_summary.md の生成
    summary_content = f"""# テスト実行サマリーレポート

**生成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**テストケース数**: {len(results)}

---

## テスト結果一覧

| # | テスト名 | ステータス | 投入個数 | 配置個数 | 配置率 | 実行時間(ms) | エラー |
|---|---------|---------|---------|---------|--------|-----------|---------|
"""
    
    # 結果テーブル生成
    passed_count = 0
    failed_count = 0
    total_placed = 0
    total_input = 0
    
    for idx, result in enumerate(results, 1):
        test_name = result.get('test_name', '不明')
        status = result.get('status', 'unknown')
        input_count = result.get('input_box_count', 0)
        placed_count = result.get('placed_box_count', 0)
        placement_rate = result.get('placement_rate', 0)
        exec_time = result.get('execution_time_ms', 0)
        error = result.get('error', None)
        
        if status == 'success':
            status_symbol = '✅ PASS'
            passed_count += 1
        else:
            status_symbol = '❌ FAIL'
            failed_count += 1
        
        error_text = error if error else '-'
        if error and len(error) > 30:
            error_text = error[:30] + '...'
        
        summary_content += f"| {idx} | {test_name} | {status_symbol} | {input_count} | {placed_count} | {placement_rate:.1f}% | {exec_time} | {error_text} |\n"
        
        total_placed += placed_count
        total_input += input_count
    
    # 集計行
    overall_rate = (total_placed / total_input * 100) if total_input > 0 else 0
    summary_content += f"\n| **合計** | | | {total_input} | {total_placed} | {overall_rate:.1f}% | | |\n"
    
    summary_content += f"""
---

## テスト実行統計

### 成功/失敗の集計

| 項目 | 結果 |
|-----|------|
| **テスト成功** | {passed_count}/{len(results)} ({(passed_count/len(results)*100 if results else 0):.1f}%) |
| **テスト失敗** | {failed_count}/{len(results)} ({(failed_count/len(results)*100 if results else 0):.1f}%) |
| **全体配置率** | {total_placed}/{total_input} ({overall_rate:.1f}%) |

### パフォーマンス統計

| 指標 | 値 |
|-----|-----|
| **平均実行時間** | {sum(r.get('execution_time_ms', 0) for r in results) / len(results) if results else 0:.1f}ms |
| **最速実行** | {min((r.get('execution_time_ms', 0) for r in results), default=0):.1f}ms |
| **最遅実行** | {max((r.get('execution_time_ms', 0) for r in results), default=0):.1f}ms |

---

## テストケース詳細

"""
    
    for result in results:
        test_name = result.get('test_name', '不明')
        status = result.get('status', 'unknown')
        input_count = result.get('input_box_count', 0)
        placed_count = result.get('placed_box_count', 0)
        placement_rate = result.get('placement_rate', 0)
        exec_time = result.get('execution_time_ms', 0)
        pallet_dim = result.get('pallet_dimensions', {})
        error = result.get('error', None)
        
        status_text = 'パス' if status == 'success' else 'フェイル'
        
        summary_content += f"""
### {test_name}

- **ステータス**: {status_text}
- **投入箱数**: {input_count}個
- **配置成功数**: {placed_count}個
- **配置率**: {placement_rate:.1f}%
- **実行時間**: {exec_time}ms
"""
        
        if pallet_dim:
            summary_content += f"""- **最終荷姿寸法**:
  - 長辺: {pallet_dim.get('width', 'N/A')}mm
  - 短辺: {pallet_dim.get('length', 'N/A')}mm
  - 高さ: {pallet_dim.get('height', 'N/A')}mm
"""
        
        if error:
            summary_content += f"- **エラー**: `{error}`\n"
    
    summary_content += f"""
---

## 推奨アクション

"""
    
    if failed_count > 0:
        summary_content += f"""
### ⚠️ {failed_count}個のテストが失敗

**確認すべき項目:**
1. エラーメッセージの内容を確認
2. algorithm-programmer の palletizer.py の制約ロジック確認
3. fitting_depth の計算が正確か確認
4. 配置アルゴリズムの改善が必要な可能性

**対応方法:**
- Supervisor の validate.py で詳細な制約違反を確認
- Algorithm-programmer に改善フィードバックを提供

"""
    else:
        summary_content += """
### ✅ 全テスト成功

**次のステップ:**
1. Supervisor で制約バリデーション実行
2. 結果を visualizer で3D可視化
3. フェーズ6 (統合テスト) へ進む

"""
    
    # ファイル出力
    summary_file = project_root / 'tester' / 'test_summary.md'
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(summary_content)
    
    print(f"✅ {summary_file} を生成しました")
    return True

if __name__ == "__main__":
    print("🔍 Tester: テスト実行サマリー生成\n")
    generate_test_summary()
