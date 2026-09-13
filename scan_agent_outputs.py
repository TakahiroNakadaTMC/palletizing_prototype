#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
フェーズ5統合検証: 全エージェント実装状況サマリー

各エージェントの成果物をスキャンし、Copilot CLI 移行の準備状況を可視化。
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

# Windows環境での文字コード対応
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def check_agent_outputs():
    """各エージェントの出力ファイルをスキャン"""
    project_root = Path(__file__).parent
    
    agents = {
        'box-research': {
            'dir': project_root / 'box_research',
            'outputs': ['box_db.json', 'README.md'],
            'description': '箱仕様調査'
        },
        'algorithm-research': {
            'dir': project_root / 'algorithm_research',
            'outputs': ['proposal.md'],
            'description': 'アルゴリズム調査'
        },
        'algorithm-programmer': {
            'dir': project_root / 'algorithm_programmer',
            'outputs': ['palletizer.py', 'models.py', 'README.md'],
            'description': 'パレタイズ実装'
        },
        'test-programmer': {
            'dir': project_root / 'test_programmer',
            'outputs': ['generate_testcases.py', 'test_cases/', 'README.md'],
            'description': 'テスト生成'
        },
        'tester': {
            'dir': project_root / 'tester',
            'outputs': ['run_simulation.py', 'results/', 'test_summary.md'],
            'description': 'シミュレーション実行'
        },
        'visualizer': {
            'dir': project_root / 'visualizer',
            'outputs': ['visualize.py', 'viewer_template.html', 'output/'],
            'description': '3D/2D可視化'
        },
        'supervisor': {
            'dir': project_root / 'supervisor',
            'outputs': ['validate.py', 'reports/', 'validation_summary.md'],
            'description': '制約検証'
        }
    }
    
    print("\n" + "="*70)
    print("フェーズ5: エージェント成果物スキャン")
    print("="*70 + "\n")
    
    summary = defaultdict(dict)
    
    for agent_name, agent_info in sorted(agents.items()):
        agent_dir = agent_info['dir']
        print(f"📋 {agent_name} ({agent_info['description']})")
        print(f"   {agent_dir}\n")
        
        # ディレクトリ存在確認
        if not agent_dir.exists():
            print(f"   ⚠️  ディレクトリが見つかりません\n")
            summary[agent_name]['status'] = 'missing_dir'
            continue
        
        # 出力ファイル確認
        found_count = 0
        for output in agent_info['outputs']:
            output_path = agent_dir / output
            if output_path.exists():
                if output_path.is_file():
                    size = output_path.stat().st_size
                    print(f"   ✅ {output} ({size} bytes)")
                    found_count += 1
                elif output_path.is_dir():
                    items = list(output_path.iterdir())
                    print(f"   ✅ {output}/ ({len(items)} items)")
                    found_count += 1
            else:
                print(f"   ❌ {output} （未作成）")
        
        # 成熟度評価
        completion_rate = (found_count / len(agent_info['outputs'])) * 100
        if completion_rate == 100:
            status = "ready"
            symbol = "✅"
        elif completion_rate >= 50:
            status = "partial"
            symbol = "🟡"
        else:
            status = "not_started"
            symbol = "❌"
        
        print(f"   {symbol} 成熟度: {completion_rate:.0f}%\n")
        summary[agent_name]['status'] = status
        summary[agent_name]['completion'] = completion_rate
    
    return summary

def print_summary(summary):
    """サマリー表を表示"""
    print("="*70)
    print("統合ステータス")
    print("="*70 + "\n")
    
    statuses = {
        'ready': ('✅', '準備完了'),
        'partial': ('🟡', '部分実装'),
        'not_started': ('❌', '未実装'),
        'missing_dir': ('⚠️', 'ディレクトリなし')
    }
    
    table_data = []
    for agent_name, info in sorted(summary.items()):
        status = info.get('status', 'unknown')
        completion = info.get('completion', 0)
        symbol, status_text = statuses.get(status, ('?', 'unknown'))
        
        table_data.append({
            'agent': agent_name,
            'symbol': symbol,
            'status': status_text,
            'completion': completion
        })
    
    # テーブル出力
    print(f"{'エージェント':<20} {'ステータス':<15} {'成熟度':<10}")
    print("-" * 70)
    
    total_completion = 0
    for row in table_data:
        bar = '█' * int(row['completion'] / 10) + '░' * (10 - int(row['completion'] / 10))
        print(f"{row['agent']:<20} {row['symbol']} {row['status']:<12} {bar} {row['completion']:.0f}%")
        total_completion += row['completion']
    
    avg_completion = total_completion / len(table_data) if table_data else 0
    print("-" * 70)
    print(f"{'平均成熟度':<20} {'':<15} {avg_completion:.1f}%")
    
    print("\n" + "="*70)
    print("推奨次ステップ")
    print("="*70 + "\n")
    
    # 次ステップ提案
    next_steps = []
    
    for agent_name, info in sorted(summary.items()):
        status = info.get('status', 'unknown')
        if status == 'not_started':
            next_steps.append(f"1. {agent_name}: proposal.md / palletizer.py / test_cases 作成")
        elif status == 'partial':
            next_steps.append(f"2. {agent_name}: 残りファイルの実装")
    
    if next_steps:
        for step in sorted(set(next_steps)):
            print(f"  {step}")
    else:
        print("  ✅ 全エージェントの成果物が揃っています！")
        print("  次ステップ: フェーズ6 統合テストの実施")
    
    print("\n" + "="*70 + "\n")

def main():
    """メイン実行"""
    print("🔍 Copilot CLI エージェント実装状況スキャン\n")
    
    summary = check_agent_outputs()
    print_summary(summary)

if __name__ == "__main__":
    main()
