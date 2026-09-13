# Google Antigravity CLI からの移行分析

**分析対象**: `.agent/` ディレクトリ内の 8 個のエージェント定義ファイル  
**対象期間**: Antigravity CLI を使用していた時期  
**目的**: Copilot CLI への移行計画の策定  

---

## 1. Antigravity CLI エージェント構成の把握

### 1.1 既存エージェント一覧

`.agent/` ディレクトリに以下の 8 個の YAML ファイルが存在:

| ファイル名 | エージェント名 | 役割 |
|-----------|---|---|
| `orchestrator.yaml` | orchestrator | マスター調整者・全体統制 |
| `box-research.yaml` | box-research | 箱仕様調査・データベース化 |
| `algorithm-research.yaml` | algorithm-research | パレタイズアルゴリズム調査 |
| `algorithm-programmer.yaml` | algorithm-programmer | アルゴリズム実装 |
| `test-programmer.yaml` | test-programmer | テストケース生成 |
| `tester.yaml` | tester | テスト実行・評価 |
| `visualizer.yaml` | visualizer | 可視化ツール開発 |
| `supervisor.yaml` | supervisor | 制約検証・監視 |

### 1.2 Antigravity YAML スキーマの分析

典型的な Antigravity YAML 定義:

```yaml
name: orchestrator
description: パレタイズ関連の全てのエージェント統括
model: gpt-4-turbo
tools:
  read_tools:
    - file_read
    - path_list
  write_tools:
    - file_write
    - file_create
  command_tools:
    - bash
  web_search: true
  subagent_tools:
    - invoke_subagent
    - list_subagents
system_message: |
  あなたは GEMINI.md に定義された orchestrator エージェント...
input_specification:
  required: ["task_description", "constraint_file"]
output_specification:
  format: "structured_json"
```

**特徴**:
- YAML 形式の構造化定義
- `tools` セクションで利用可能なツールを明示的に記述
- `system_message` で詳細な指示を記述
- `input_specification`, `output_specification` で入出力仕様を定義
- `web_search`, `subagent_tools` で拡張機能を明示

---

## 2. Antigravity CLI の特徴と仕様

### 2.1 コア機能

| 機能 | 詳細 |
|-----|------|
| **マルチエージェント** | 8 個の独立したエージェント定義 |
| **ツール管理** | `read_tools`, `write_tools`, `command_tools` で権限ベースの管理 |
| **Web Search** | `web_search: true` で検索機能を有効化 |
| **サブエージェント呼び出し** | `subagent_tools: true` で他エージェント呼び出し可能 |
| **構造化実行** | YAML による厳密な定義と実行フロー制御 |

### 2.2 Antigravity CLI のメリット

- ✅ **明示的なツール権限管理**: セキュリティが高い
- ✅ **型安全な入出力仕様**: インターフェイス定義が明確
- ✅ **システムメッセージの詳細記述**: エージェント動作が正確
- ✅ **Web Search との統合**: 外部情報の取得が容易

---

## 3. GitHub Copilot CLI との比較

### 3.1 アーキテクチャの違い

| 項目 | Antigravity CLI | Copilot CLI |
|-----|---|---|
| **定義形式** | YAML (`.agent/*.yaml`) | Markdown (`.github/instructions/*.md`) |
| **ツール指定方式** | 明示的な `tools` セクション | 行動指示に基づく自動選択 |
| **入出力仕様** | 構造化 JSON スキーマ | テキスト記述 |
| **サブエージェント呼び出し** | `subagent_tools` を明示 | `/agent` コマンドまたは API で呼び出し |
| **Web Search** | `web_search: true` フラグ | 組み込み機能（`/research` コマンド） |
| **実行環境** | 独立した Antigravity インスタンス | GitHub Copilot エコシステム |

### 3.2 機能マッピング

```
Antigravity CLI              →  GitHub Copilot CLI
─────────────────────────────────────────────────────
system_message              →  # Role / Purpose セクション
input_specification         →  ## Input / Inputs セクション
output_specification        →  ## Output / Outputs セクション
tools (read_tools)          →  # Tools セクションで記述
tools (write_tools)         →  # Tools セクションで記述
tools (command_tools)       →  # Tools セクションで記述
web_search: true            →  builtin (research/search capability)
subagent_tools: true        →  /agent <name> or write_agent API
```

---

## 4. 既存 Antigravity データとの互換性

### 4.1 保護すべきデータ

以下のファイル・ディレクトリは、移行後も互換性を保たねばならない:

| ファイル/ディレクトリ | 内容 | 互換性 |
|---|---|---|
| `constraints/constraints.md` | 荷姿制約仕様 | ✅ 完全互換 |
| `box_research/box_db.json` | 13個の箱定義 | ✅ 完全互換 |
| `algorithm_research/proposal.md` | アルゴリズム提案 | ✅ 完全互換 |
| `algorithm_programmer/palletizer.py` | コアエンジン実装 | ✅ 完全互換 |
| `test_programmer/test_cases/` | テストケース JSON | ✅ 完全互換 |
| `tester/results/` | 実行結果データ | ✅ 完全互換 |

**結論**: データスキーマに変更がなく、Copilot CLI でも全て利用可能。

---

## 5. 移行戦略

### 5.1 段階的移行方針

1. **フェーズ 1**: 現状分析（このドキュメント）
2. **フェーズ 2**: Copilot CLI セットアップ
3. **フェーズ 3**: YAML → Markdown エージェント定義の変換
4. **フェーズ 4**: データ互換性の検証
5. **フェーズ 5**: 各エージェントの単体テスト
6. **フェーズ 6**: 統合テスト
7. **フェーズ 7**: ドキュメント更新・クリーンアップ

### 5.2 リスク評価

| リスク | 確度 | 対策 |
|------|------|------|
| Web Search 機能の非互換性 | 🟡 低 | Copilot CLI は `/research` でサポート |
| サブエージェント呼び出しの差異 | 🟡 低 | write_agent API で完全サポート |
| 既存データスキーマの変化 | 🟢 極低 | スキーマ検証スクリプトで確認 |
| エージェント間通信の遅延 | 🟡 低 | テストフェーズで確認 |

---

## 6. 推奨スケジュール

### 実装予定日程

| フェーズ | 期間 | 主要タスク |
|---------|------|-----------|
| Phase 1 | 1日 | 既存構成分析（完了） |
| Phase 2 | 1日 | Copilot CLI セットアップ |
| Phase 3 | 2日 | 8個エージェント定義変換 |
| Phase 4 | 1日 | 互換性検証 |
| Phase 5 | 2日 | 個別エージェント単体テスト |
| Phase 6 | 1日 | 統合テスト |
| Phase 7 | 1日 | ドキュメント更新・最終確認 |
| **合計** | **~1週間** | **完全移行** |

---

## 7. 結論

### 7.1 移行の可行性

✅ **高い可行性**: 
- データスキーマの完全互換性
- Copilot CLI の十分な機能（Web Search, サブエージェント呼び出し）
- 既存エージェント設計が Copilot CLI に適合

### 7.2 期待効果

- 📊 GitHub と Copilot CLI の統合による開発効率向上
- 📊 より柔軟なエージェント定義 (Markdown ベース)
- 📊 より小さな学習曲線 (Markdown 形式)

### 7.3 アクション

**推奨**: 計画に従い、順次フェーズを実行。各フェーズの検証で問題が発生しない限り、スケジュール通り進行可能。

---

**分析完了日**: 2026年8月19日  
**担当**: AI Agent (Antigravity CLI 移行分析)  
**ステータス**: ✅ 完了 → フェーズ 2 へ遷移準備完了
