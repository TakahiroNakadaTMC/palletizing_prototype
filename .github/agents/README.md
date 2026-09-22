# GitHub Copilot サブエージェント

このディレクトリには、パレタイズプロトタイププロジェクト用の GitHub Copilot CLI サブエージェント定義が格納されています。各 `.agent.md` ファイルは YAML frontmatter で構成され、CLI からサブエージェントとして認識・呼び出しされます。

このディレクトリの定義は、各ロールの行動指針の**正（source of truth）**です。VS Code Copilot Chat 用の `.github/prompts/*.prompt.md` や、常時自動読込される `.github/instructions/*.instructions.md` は、ここでの定義を踏まえて作成・同期してください。

## Frontmatter 構成

各エージェントファイルは以下のYAML frontmatterを持ちます（[Custom agents configuration](https://docs.github.com/en/copilot/reference/custom-agents-configuration) 準拠）：

```yaml
---
name: <agent-name>
description: <役割の簡潔な説明（日本語）>
tools: [<各エージェントに必要なツールのみ>]
model: <各エージェントに最適なモデル>
---
```

- `name`: 任意。省略時はファイル名が使用される
- `description`: **必須**。エージェント選択時に表示される説明
- `tools`: 任意。省略時は全ツールが有効になるため、各エージェントの責務に応じて最小権限で明示的に指定する
- `model`: 任意。省略時はセッションのデフォルトモデルを継承するため、各エージェントのタスク特性に応じて明示的に指定する
- `argument-hint` は `.agent.md` の仕様には存在しない（VS Code の `.prompt.md` 専用プロパティ）ため使用しない

## ツール割り当て（`tools`）

各エージェントの責務に基づき、以下の最小権限でツールを割り当てている。

| エージェント | `tools` | 割り当て理由 |
|---|---|---|
| `orchestrator` | `read`, `edit`, `search`, `execute`, `agent`, `todo` | 全ディレクトリ監視、README更新、他サブエージェント呼び出し（`agent`）、進捗管理（`todo`）が責務 |
| `box-research` | `read`, `edit`, `search`, `web`, `execute` | JIS/メーカー仕様のWeb調査（`web`）＋`box_research/`へのDB書き込みが責務 |
| `algorithm-research` | `read`, `edit`, `search`, `web`, `execute` | 論文・OSS実装のWeb調査（`web`）＋`algorithm_research/proposal.md`作成が責務 |
| `test-programmer` | `read`, `edit`, `search`, `execute` | `constraints/`・`box_research/`読込＋`test_programmer/`へのテストケース生成 |
| `algorithm-programmer` | `read`, `edit`, `search`, `execute` | `algorithm_programmer/`実装・デバッグ実行 |
| `visualizer` | `read`, `edit`, `search`, `execute` | 結果JSON読込＋`visualizer/`へのHTML生成・動作確認 |
| `tester` | `read`, `edit`, `search`, `execute` | テストケース実行・`tester/results/`書き込み |
| `supervisor` | `read`, `edit`, `search`, `execute` | 制約検証スクリプト実行・`supervisor/reports/`書き込み |

- `web`（外部調査）は `box-research` / `algorithm-research` のみに付与
- `agent`（他エージェント呼び出し）・`todo`（タスク管理）は統括役の `orchestrator` のみに付与

## モデル割り当て（`model`）

タスクの複雑さに応じて、各エージェントに以下のモデルを割り当てている。

| エージェント | `model` | 割り当て理由 |
|---|---|---|
| `orchestrator` | `claude-sonnet-5` | 全体統括・計画立案・複数エージェントへの指示判断など高度な汎用推論が必要 |
| `box-research` | `gpt-5.4-mini` | JIS/メーカー仕様の定型調査とJSON DB化。構造化された比較的軽量なタスク |
| `algorithm-research` | `claude-opus-5` | 複数アルゴリズム候補の比較検討・数理モデル設計など、最も高度な推論が必要 |
| `test-programmer` | `gpt-5.4-mini` | パターン化されたテストケース（単載/混載/境界値）の生成。定型作業 |
| `algorithm-programmer` | `gpt-5.3-codex` | パレタイズエンジンのコア実装（コーディング特化モデル） |
| `visualizer` | `gpt-5.3-codex` | 3D/2D可視化ツール（Three.js/Plotly）の実装（コーディング特化モデル） |
| `tester` | `gemini-3.5-flash` | テスト実行・結果収集という機械的作業。軽量・高速モデルで十分 |
| `supervisor` | `claude-sonnet-5` | 9項目の制約を厳格に検証する品質ゲート。高い精度と一貫性が必要 |

## 利用可能なエージェント

### 1. orchestrator
**ファイル:** `orchestrator.agent.md`
**説明:** ループエンジニアリング全体の進行管理・次工程判定・自律サイクルの統括

プロジェクト全体の進捗を管理し、次のフェーズを判断し、自律的なエンジニアリングループを調整する。

### 2. algorithm-programmer
**ファイル:** `algorithm-programmer.agent.md`
**説明:** パレタイズアルゴリズムの実装・改善と制約充足の検証

パレタイズアルゴリズムを実装・改善し、制約充足を検証する。

### 3. algorithm-research
**ファイル:** `algorithm-research.agent.md`
**説明:** パレタイズアルゴリズム候補調査・比較・最適方式の提案

アルゴリズム候補を調査・比較し、最適な方式を提案する。

### 4. box-research
**ファイル:** `box-research.agent.md`
**説明:** パレタイズ対象箱の仕様調査・データベース構築

パレタイズ対象箱の仕様を調査し、データベースを構築する。

### 5. supervisor
**ファイル:** `supervisor.agent.md`
**説明:** パレタイズ結果の制約違反検証・品質監視・改善指示

パレタイズ結果の制約違反を検証し、品質を監視し、改善指示を出す。

### 6. test-programmer
**ファイル:** `test-programmer.agent.md`
**説明:** テストケース設計・テストデータ生成・投入パターン作成

テストケースを設計し、様々な投入パターンのテストデータを生成する。

### 7. tester
**ファイル:** `tester.agent.md`
**説明:** テストケース実行・シミュレーション・結果収集・エラー報告

テストケースを実行し、シミュレーションを行い、結果を収集・エラーを報告する。

### 8. visualizer
**ファイル:** `visualizer.agent.md`
**説明:** パレタイズ結果の3D/2D可視化・ビューアツール開発

パレタイズ結果の3D/2D可視化ツールを開発する。

## 使い方

GitHub Copilot CLI で以下のいずれかの方法により呼び出せます：

1. **`/agent` コマンドで選択**
   ```
   /agent orchestrator
   ```

2. **`@<name>` によるメンション呼び出し**
   ```
   @box-research TP-461系の箱仕様を調査してください
   ```

## 最終更新

2026-09-22 - 各エージェントのタスク特性に基づき、frontmatterに `model` を割り当て。
2026-09-22 - 各エージェントの責務に基づき、frontmatterに `tools` を最小権限で割り当て。
2026-09-22 - `.github/prompts/*.prompt.md` から複製した際に残っていた不正な `argument-hint` frontmatterを削除し、`.agent.md` として正式なフォーマットに修正。
