# Copilot CLI エージェント利用ガイド

## 概要

このプロジェクトは GitHub Copilot CLI を使用して、複数の AI エージェントが協働して箱パレタイズアルゴリズムを開発します。

各エージェントは専門分野を持ち、`GEMINI.md` に定義されたフェーズと実行フロー に従って段階的に進行します。

---

## エージェント一覧と呼び出し方法

### 1. Orchestrator（全体統括管理者）
```bash
cd /path/to/palletizing_prototype
gh copilot agent --name orchestrator
```
ユーザーの要望をもとに全体計画を立案し、各サブエージェントに指示を出します。

### 2. Box Research（箱仕様調査）
```bash
gh copilot agent --name box-research
```
パレタイズ対象の箱（TP規格・非TP箱）の寸法・嵌合深さ・リブ厚みを調査・DB化します。
→ 出力: `box_research/box_db.json`

### 3. Algorithm Research（アルゴリズム調査）
```bash
gh copilot agent --name algorithm-research
```
TP嵌合・リブ構造を考慮したパレタイズアルゴリズムの方式を提案します。
→ 出力: `algorithm_research/proposal.md`

### 4. Algorithm Programmer（パレタイズエンジン実装）
```bash
gh copilot agent --name algorithm-programmer
```
Proposal に基づきパレタイズアルゴリズムを Python で実装、テストして改善します。
→ 出力: `algorithm_programmer/palletizer.py`, `models.py`, `README.md`

### 5. Test Programmer（テストデータ生成）
```bash
gh copilot agent --name test-programmer
```
Box DB をもとに、多様なテストケース（単載・混載・境界値）を生成します。
→ 出力: `test_programmer/test_cases/` JSON群

### 6. Tester（シミュレーション実行）
```bash
gh copilot agent --name tester
```
全テストケースでパレタイズアルゴリズムを実行、結果を収集・レポート化します。
→ 出力: `tester/results/`, `test_summary.md`

### 7. Visualizer（3D/2D可視化）
```bash
gh copilot agent --name visualizer
```
パレタイズ結果を 3D/2D で可視化し、ブラウザで確認できるツールを開発します。
→ 出力: `visualizer/visualize.py`, `viewer_template.html`, 可視化ビューワ

### 8. Supervisor（制約バリデーション）
```bash
gh copilot agent --name supervisor
```
`constraints/constraints.md` に基づき、パレタイズ結果の制約違反を厳格に検証します。
→ 出力: `supervisor/validate.py`, `validation_summary.md`

---

## エージェント実行フロー

推奨される実行順序：

```
1. Orchestrator
   ↓
2. Box Research & Algorithm Research （並列実行可）
   ↓
3. Algorithm Programmer
   ↓
4. Test Programmer & Tester （並列実行可）
   ↓
5. Visualizer & Supervisor （並列実行可）
   ↓
   Supervisor FAIL の場合 → Algorithm Programmer へフィードバック（フェーズ3 へ戻る）
   Supervisor PASS の場合 → 完成
```

---

## GEMINI.md との対応関係

- **フェーズ1（要件定義・データ整備）** → Box Research, Algorithm Research
- **フェーズ2（実装・ツール作成）** → Algorithm Programmer, Test Programmer, Visualizer
- **フェーズ3（実行・検証・改善）** → Tester, Supervisor, Algorithm Programmer (フィードバック)

---

## トラブルシューティング

### Copilot CLI のインストール確認
```bash
gh --version
```

### エージェント定義の確認
```bash
ls -la .github/instructions/*.instructions.md
```

### ログ確認
Copilot CLI は自動的にセッション情報を記録します。
詳細情報は CLI の `/session` コマンドで確認できます。

---

## 注意事項

- 各エージェントの `input_files` / `output_files` を厳密に守る
- Orchestrator が各エージェント成果物を検収し、不備があれば修正を依頼
- Constraints 違反がないか定期的に Supervisor に確認させる
- 既存テストケース・データスキーマとの互換性を常に意識する

---

## 参考資料

- `GEMINI.md` - プロジェクト全体構成・フェーズ・エージェント役割定義
- `constraints/constraints.md` - 荷姿制約仕様（全エージェント必読）
- `box_research/box_db.json` - 箱仕様データベーススキーマ
- `.github/instructions/` - 各エージェント詳細ドキュメント
