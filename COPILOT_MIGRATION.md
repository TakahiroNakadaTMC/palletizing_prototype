# GitHub Copilot CLI への切り替え手順書

このドキュメントは、Google Antigravity CLI から GitHub Copilot CLI への移行手順をまとめています。

---

## 1. 前提条件

- GitHub CLI v2.100.0 以上がインストール済み
- GitHub Copilot CLI v1.0.83 以上がインストール済み
- GitHub 認証済み (`gh auth login` で完了)
- このプロジェクトの `.github/instructions/` ディレクトリが配置済み

---

## 2. 簡単な起動方法

### CLI インタラクティブモードで実行

```bash
cd path/to/palletizing_prototype
gh copilot
```

これで Copilot CLI が起動し、エージェント選択メニューが表示されます。

### エージェント指定で実行（推奨方法）

```bash
# Orchestrator を起動
/agent orchestrator

# メッセージを入力（例）
@orchestrator すべてのサブエージェントに、現在のプロジェクトの進捗を確認してください
```

---

## 3. エージェント実行の例

### 例1: Box Research を実行
```bash
/agent box-research

# ユーザー: 
# 「GEMINI.md に定義されたパレット (1200x1000mm) の制約に合わせて、
#  箱_db.json の内容を確認し、モジュール比率が正しくマッピングされているか
#  検証してください」
```

### 例2: Algorithm Programmer のコード改善
```bash
/agent algorithm-programmer

# ユーザー:
# 「supervisor から『長辺荷姿が 1360mm を超えている』との指摘がありました。
#  algorithm_programmer/palletizer.py を修正し、長辺制約を遵守させてください」
```

### 例3: Orchestrator で複数タスクを統括
```bash
/agent orchestrator

# ユーザー:
# 「以下の順序でタスクを実行してください：
#  1. box-research に box_db.json の確認を指示
#  2. algorithm-research に最適なアルゴリズム方式を提案させる
#  3. algorithm-programmer に実装を指示
#  進捗報告をお願いします」
```

---

## 4. Copilot CLI のお役立ちコマンド

| コマンド | 説明 |
|--------|------|
| `/help` | 全コマンドのヘルプ表示 |
| `/agent <name>` | 指定エージェントを実行 |
| `/tasks` | 実行中・完了したタスク一覧 |
| `/session` | 現在のセッション情報表示 |
| `/resume` | 前回のセッションに戻る |
| `/model` | AI モデル選択（デフォルト自動） |
| `/autopilot` | 自動パイロット モード ON/OFF |
| `/fleet` | フリート モード（並列実行）ON/OFF |
| `/diff` | 変更ファイルの確認 |
| `/pr` - プルリクエスト操作 | |
| `/clear` | セッションをクリア |

---

## 5. よくある使用パターン

### パターン A: 段階的な開発

1. **Box Research フェーズ**
   ```bash
   /agent box-research
   # → 箱仕様確認・box_db.json 更新
   ```

2. **Algorithm Research フェーズ**
   ```bash
   /agent algorithm-research
   # → アルゴリズム方式提案書作成
   ```

3. **Algorithm Programmer フェーズ**
   ```bash
   /agent algorithm-programmer
   # → palletizer.py 実装
   ```

### パターン B: テスト・検証ループ

1. Test Programmer でテストケース生成
2. Tester でシミュレーション実行
3. Supervisor で制約検証
4. NG なら Algorithm Programmer にフィードバック（フェーズ2へ）

### パターン C: 全エージェント統括（Orchestrator推奨）

```bash
/agent orchestrator

# ユーザー:
# 「フェーズ1～3を順序良く実行し、最終レポートを作成してください。
#  各エージェントの成果物が GEMINI.md の仕様を満たしているか確認も併せてお願いします」
```

---

## 6. トラブルシューティング

### 問題1: エージェントが認識されない

**原因**: `.github/instructions/` ファイルが見つからない

**対策**:
```bash
ls -la .github/instructions/
# 出力確認: orchestrator.instructions.md, box-research.instructions.md, ... が存在するか
```

### 問題2: ファイルアクセスエラー

**原因**: パーミッション不足 または 入出力パスが不正

**対策**:
1. `cd` で正しいプロジェクトディレクトリにいることを確認
2. `.github/copilot-instructions.md` の入出力ファイル指定を確認
3. 必要に応じて `/permissions` コマンドで権限設定

### 問題3: Web検索が動作しない

**原因**: Network 制限 または Copilot CLI 設定不足

**対策**:
- `/env` コマンドで Copilot CLI 環境を確認
- Network 接続を確認
- 必要に応じて手動でWeb検索情報を提供

---

## 7. GEMINI.md との対応

- **フェーズ1（要件定義・データ整備）** → Box Research + Algorithm Research
- **フェーズ2（実装・ツール作成）** → Algorithm Programmer + Test Programmer + Visualizer
- **フェーズ3（実行・検証・改善）** → Tester + Supervisor → Feedback Loop

詳細は `GEMINI.md` の「4. エージェント実行フロー」を参照してください。

---

## 8. 旧 Antigravity CLI との違い

| 項目 | Antigravity | Copilot CLI |
|-----|-----------|-----------|
| 定義ファイル位置 | `.agent/*.yaml` | `.github/instructions/*.instructions.md` |
| 定義形式 | YAML | Markdown |
| 起動方法 | antigravity agent ... | gh copilot / /agent ... |
| エージェント制御 | `subagent_tools` | `/agent`, `/tasks`, `/fleet` |
| Web検索 | `web_search: true` | Copilot CLI 組み込み |
| 出力ファイル形式 | 同様（JSON / MD） | 同様 |

---

## 9. 推奨される切り替え手順

### ステップ1: 動作確認（フェーズ5）
各エージェントを 1 つずつ実行して動作確認

### ステップ2: 統合テスト（フェーズ6）
複数エージェント連携（orchestrator → sub-agents）をテスト

### ステップ3: 既存テストケース実行（フェーズ7）
`test_programmer/test_cases/` の既存テストをすべて再実行

### ステップ4: ドキュメント更新
GEMINI.md・README.md に Copilot CLI 利用方法を追記

### ステップ5: .agent ディレクトリのアーカイブ
不要なら削除、またはバックアップとして保持

---

## 10. 参考資料

- **このプロジェクト内**:
  - `GEMINI.md` - プロジェクト全体構成
  - `.github/copilot-instructions.md` - エージェント利用ガイド
  - `.github/instructions/*.instructions.md` - 各エージェント詳細定義
  - `constraints/constraints.md` - 荷姿制約仕様

- **外部ドキュメント**:
  - [GitHub Copilot CLI Documentation](https://docs.github.com/copilot/how-tos/use-copilot-agents/use-copilot-cli)
  - [GitHub CLI Manual](https://cli.github.com/manual)

---

## 11. サポート・フィードバック

問題が発生した場合:
1. Copilot CLI の `/session` コマンドでセッション ID 確認
2. `/feedback` コマンドでフィードバック送信
3. 本プロジェクトのドキュメント に記録・共有

---

**更新日**: 2026-09-11  
**対応 Copilot CLI バージョン**: v1.0.83+  
**対応 GitHub CLI バージョン**: v2.100.0+
