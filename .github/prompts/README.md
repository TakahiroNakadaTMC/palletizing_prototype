# GitHub Copilot Prompts

This directory contains custom GitHub Copilot prompts for the palletizing prototype project. Each `.prompt.md` file is configured with YAML frontmatter to enable recognition as a slash command in VS Code.

## Frontmatter Structure

Each prompt file starts with YAML frontmatter containing:

```yaml
---
name: <command-name>
description: <brief description in Japanese>
argument-hint: <optional arguments hint>
---
```

## Available Prompts

### 1. orchestrator
**File:** `orchestrator.prompt.md`  
**Name:** orchestrator  
**Description:** ループエンジニアリング全体の進行管理・次工程判定・自律サイクルの統括  
**Argument Hint:** 次のタスクや確認したい進捗状況  

Manages overall project progress, determines next phases, and coordinates the autonomous engineering loop.

### 2. algorithm-programmer
**File:** `algorithm-programmer.prompt.md`  
**Name:** algorithm-programmer  
**Description:** パレタイズアルゴリズムの実装・改善と制約充足の検証  
**Argument Hint:** 修正対象の制約項目やテスト失敗内容  

Implements and improves the palletization algorithm, validates constraint satisfaction.

### 3. algorithm-research
**File:** `algorithm-research.prompt.md`  
**Name:** algorithm-research  
**Description:** パレタイズアルゴリズム候補調査・比較・最適方式の提案  
**Argument Hint:** 調査対象のアルゴリズム分野や特定制約の検討観点  

Researches algorithm candidates, compares approaches, and proposes optimal methods.

### 4. box-research
**File:** `box-research.prompt.md`  
**Name:** box-research  
**Description:** パレタイズ対象箱の仕様調査・データベース構築  
**Argument Hint:** 調査対象の箱型番や追加メタデータ項目  

Surveys box specifications and constructs the database of palletization targets.

### 5. supervisor
**File:** `supervisor.prompt.md`  
**Name:** supervisor  
**Description:** パレタイズ結果の制約違反検証・品質監視・改善指示  
**Argument Hint:** 検証対象の結果データファイルパスや特定チェック項目  

Validates constraint violations in palletization results and provides improvement guidance.

### 6. test-programmer
**File:** `test-programmer.prompt.md`  
**Name:** test-programmer  
**Description:** テストケース設計・テストデータ生成・投入パターン作成  
**Argument Hint:** 追加するテストパターンや特定シナリオの要件  

Designs test cases and generates test data with various input patterns.

### 7. tester
**File:** `tester.prompt.md`  
**Name:** tester  
**Description:** テストケース実行・シミュレーション・結果収集・エラー報告  
**Argument Hint:** 実行対象のテストケースやベンチマーク測定項目  

Executes test cases, runs simulations, collects results, and reports errors.

### 8. visualizer
**File:** `visualizer.prompt.md`  
**Name:** visualizer  
**Description:** パレタイズ結果の3D/2D可視化・ビューアツール開発  
**Argument Hint:** 可視化対象のデータファイルやレンダリング要件  

Develops 3D/2D visualization tools for palletization results.

## Usage

To use these prompts in GitHub Copilot (VS Code):

1. Ensure you have GitHub Copilot extension installed
2. Open a file in the project workspace
3. Type `/` followed by the prompt name (e.g., `/orchestrator`)
4. Select the desired prompt from the suggestion list
5. Provide any required arguments based on the `argument-hint`

## Frontmatter Format

All prompt files in this directory follow this structure:

- **Lines 1-5:** YAML frontmatter enclosed in `---` delimiters
- **Line 6:** Blank line (separator)
- **Line 7+:** Original Markdown content for the prompt

## Last Updated

2026-09-20 - Added YAML frontmatter to all 8 prompt files for GitHub Copilot recognition.
