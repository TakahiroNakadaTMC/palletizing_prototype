# GitHub Copilot サブエージェント

このディレクトリには、パレタイズプロトタイププロジェクト用の GitHub Copilot CLI サブエージェント定義が格納されています。各 `.agent.md` ファイルは YAML frontmatter で構成され、CLI からサブエージェントとして認識・呼び出しされます。

このディレクトリの定義は、各ロールの行動指針の**正（source of truth）**です。VS Code Copilot Chat 用の `.github/prompts/*.prompt.md` や、常時自動読込される `.github/instructions/*.instructions.md` は、ここでの定義を踏まえて作成・同期してください。

## Frontmatter 構成

各エージェントファイルは以下のYAML frontmatterを持ちます（[Custom agents configuration](https://docs.github.com/en/copilot/reference/custom-agents-configuration) 準拠）：

```yaml
---
name: <agent-name>
description: <役割の簡潔な説明（日本語）>
---
```

- `name`: 任意。省略時はファイル名が使用される
- `description`: **必須**。エージェント選択時に表示される説明
- `argument-hint` は `.agent.md` の仕様には存在しない（VS Code の `.prompt.md` 専用プロパティ）ため使用しない

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

2026-09-22 - `.github/prompts/*.prompt.md` から複製した際に残っていた不正な `argument-hint` frontmatterを削除し、`.agent.md` として正式なフォーマットに修正。
