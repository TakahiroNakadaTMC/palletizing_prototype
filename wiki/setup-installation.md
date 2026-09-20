---
layout: page
title: セットアップ&インストール
permalink: /wiki/setup-installation/
---

# セットアップ&インストール

本ページでは、パレタイズ試作プロジェクトを実行するための環境構築手順を説明します。

## 前提条件

### システム要件
- **OS**: Windows 11 (推奨) / macOS / Linux
- **Python**: 3.9 以上
- **Git**: 最新版推奨

### OS 別の Python インストール方法

#### Windows 11 ⭐ (推奨)
1. [Python 公式サイト](https://www.python.org/) から Python 3.12 をダウンロード
2. インストーラを実行
   - 📌 **重要**: 「Add Python to PATH」にチェックを入れる
   - 「Install for all users」を推奨（管理者権限が必要な場合がある）
3. インストール完了後、PowerShell または Command Prompt で確認
   ```powershell
   python --version
   ```

#### macOS
```bash
# Homebrew を使用する場合
brew install python@3.12

# または MacPorts を使用する場合
sudo port install python312
```

#### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip
```

## リポジトリ構成

このプロジェクトは 3 つのブランチで構成されています：

- **`main`**: プロジェクト初期構造・ドキュメント
- **`develop`**: Python 実装コード（パレタイズエンジン、テスター、可視化ツール等）
- **`gh-pages`**: Wiki ドキュメント（本サイト）

**開発作業は `develop` ブランチで行います。**

## Python 環境のセットアップ

### 1. リポジトリのクローン

**Windows 11 (PowerShell) ⭐**
```powershell
git clone https://github.com/TakahiroNakadaTMC/palletizing_prototype.git
cd palletizing_prototype
```

**macOS / Linux:**
```bash
git clone https://github.com/TakahiroNakadaTMC/palletizing_prototype.git
cd palletizing_prototype
```

### 2. develop ブランチをチェックアウト

```bash
git switch develop
```

### 3. Python 仮想環境の作成

**Windows 11:**
```powershell
python -m venv venv
```

**macOS / Linux:**
```bash
python3 -m venv venv
```

### 4. 仮想環境の有効化

**Windows 11 (PowerShell) ⭐ (推奨)**
```powershell
.\venv\Scripts\Activate.ps1
```

> **トラブル**: `Activate.ps1 が実行できない` という場合は、[トラブルシューティング](#windows-での権限エラー)を参照してください。

**Windows 11 (Command Prompt)**
```cmd
.\venv\Scripts\activate.bat
```

**macOS / Linux (bash/zsh):**
```bash
source venv/bin/activate
```

**Linux (fish shell):**
```bash
source venv/bin/activate.fish
```

有効化されると、ターミナルのプロンプトに `(venv)` が表示されます。

### 5. pip をアップグレード

```bash
pip install --upgrade pip
```

## 依存パッケージのインストール

### 標準ライブラリのみ

このプロジェクトは **外部依存パッケージを使用せず、Python 標準ライブラリのみ** で実装されています。

追加のインストール作業は不要です。

## 環境検証

セットアップが完了したことを確認するため、以下のコマンドを実行してください：

**Windows 11 (PowerShell/Command Prompt)**
```powershell
# Python バージョン確認
python --version

# 必須モジュールの確認
python -c "import json, math, dataclasses, urllib.parse; print('✓ All required modules available')"
```

**macOS / Linux (bash/zsh)**
```bash
# Python バージョン確認
python3 --version

# 必須モジュールの確認
python3 -c "import json, math, dataclasses, urllib.parse; print('✓ All required modules available')"
```

## プロジェクト構造の理解

```
palletizing_prototype/
├── algorithm_programmer/    # パレタイズエンジン実装
│   ├── cli.py              # コマンドラインインターフェース
│   ├── models.py           # データモデル (BoxSpec, PalletSpec 等)
│   ├── palletizer.py       # パレタイズ計算エンジン本体
│   └── README.md           # 詳細仕様書
├── test_programmer/        # テストケース生成
│   ├── generate_testcases.py
│   ├── test_cases/         # テストケース JSON ファイル群
│   └── README.md
├── tester/                 # テスト実行・シミュレーション
│   ├── run_tests.py        # 全テスト一括実行スクリプト
│   ├── results/            # シミュレーション結果
│   └── README.md
├── visualizer/             # 3D/2D 可視化ツール
│   ├── visualize.py
│   ├── serve_3d_viewer.py
│   └── README.md
├── supervisor/             # 制約検証
│   ├── validate.py
│   └── README.md
├── box_research/           # 箱仕様 DB
│   ├── box_db.json
│   └── README.md
├── constraints/            # 荷姿制約仕様
├── .agent/                 # エージェント定義ファイル
├── GEMINI.md               # プロジェクト全体仕様書
└── validate_copilot_setup.py  # セットアップ検証スクリプト
```

## 各コンポーネントの実行方法

### Algorithm Programmer - パレタイズエンジン実行

単一テストケースを実行：

**Windows 11 ⭐**
```powershell
python algorithm_programmer/cli.py test_programmer/test_cases/mixed_tp_same_height.json
```

**macOS / Linux:**
```bash
python3 algorithm_programmer/cli.py test_programmer/test_cases/mixed_tp_same_height.json
```

結果を JSON ファイルに保存：

**Windows 11:**
```powershell
python algorithm_programmer/cli.py test_programmer/test_cases/mixed_tp_same_height.json -o tester/results/result_mixed_tp_same_height.json
```

**macOS / Linux:**
```bash
python3 algorithm_programmer/cli.py test_programmer/test_cases/mixed_tp_same_height.json \
  -o tester/results/result_mixed_tp_same_height.json
```

### Test Programmer - テストケース生成

テストケース JSON ファイルを生成：

**Windows 11:**
```powershell
python test_programmer/generate_testcases.py
```

**macOS / Linux:**
```bash
python3 test_programmer/generate_testcases.py
```

テストケースビューアを起動（ブラウザ）：

**Windows 11:**
```powershell
python test_programmer/serve_testcase_viewer.py
# http://localhost:8083 をブラウザで開く
```

**macOS / Linux:**
```bash
python3 test_programmer/serve_testcase_viewer.py
# http://localhost:8083 を開く
```

### Tester - 全テスト一括実行

全テストケースでシミュレーション実行：

**Windows 11:**
```powershell
python tester/run_tests.py
```

**macOS / Linux:**
```bash
python3 tester/run_tests.py
```

結果は `tester/results/` に JSON ファイルとして保存されます。

### Visualizer - 3D ビューワ起動

3D 可視化ツールを起動：

**Windows 11:**
```powershell
python visualizer/serve_3d_viewer.py
# ブラウザで http://localhost:8080 を開く
```

**macOS / Linux:**
```bash
python3 visualizer/serve_3d_viewer.py
# ブラウザで http://localhost:8080 を開く
```

### Supervisor - 制約検証

制約ファイル（`constraints/constraints.md`）に基づいて荷姿を検証：

**Windows 11:**
```powershell
python supervisor/validate.py tester/results/result_mixed_tp_same_height.json
```

**macOS / Linux:**
```bash
python3 supervisor/validate.py tester/results/result_mixed_tp_same_height.json
```

### セットアップ検証スクリプト

Copilot CLI エージェント定義が正しく設定されているか検証：

**Windows 11:**
```powershell
python validate_copilot_setup.py
```

**macOS / Linux:**
```bash
python3 validate_copilot_setup.py
```

---

## トラブルシューティング

### Windows 11 での権限エラー（最も一般的） ⭐

**症状**: 仮想環境の有効化時に以下のエラーが発生
```
.\venv\Scripts\Activate.ps1 : このシステムではスクリプトの実行が無効になっているため、
ファイルを読み込むことができません。
```

**対応** (順序通りに試してください):

1. **PowerShell を管理者権限で起動**
   - スタートメニューから `PowerShell` を右クリック
   - 「管理者として実行」を選択

2. **現在の実行ポリシーを確認**
   ```powershell
   Get-ExecutionPolicy
   ```
   
   出力が `Restricted` の場合は以下を実行：
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```
   
   確認メッセージで `Y` (Yes) を入力

3. **再度 PowerShell を開き直す**
   - 現在のウィンドウを閉じる
   - PowerShell を新規に開く（必ずしも管理者権限不要）

4. **仮想環境の有効化を再実行**
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

**代替手段**: Command Prompt を使用する場合
```cmd
.\venv\Scripts\activate.bat
```

### 仮想環境が有効化されない場合

**症状**: `(venv)` がプロンプトに表示されない

**Windows 11 での対応**:
```powershell
# 正しいアクティベーションスクリプトを実行しているか確認
where python

# 仮想環境のパスが正しいか確認（venv フォルダが存在するか）
dir .\venv\Scripts\
```

**macOS / Linux での対応**:
```bash
# 正しいアクティベーションスクリプトを実行しているか確認
which python

# または which python3
which python3
```

異なるシェル（bash, zsh, fish など）を使用している場合は、適切なアクティベーションスクリプトを実行してください：

```bash
# zsh の場合
source venv/bin/activate

# fish の場合
source venv/bin/activate.fish
```

### Python が見つからない

**症状**: `python: command not found` または `'python' は内部コマンドまたは外部コマンドではありません`

**対応**:

**Windows 11:**
1. Python をまだインストールしていない場合は [公式ページ](https://www.python.org/) からダウンロード
2. インストール時に **「Add Python to PATH」にチェック** を入れたか確認
3. チェックを入れ忘れた場合：
   - Python をアンインストール → 再インストール
   - または Python のインストール場所を `PATH` に手動追加

```powershell
# Python のインストール場所を確認（例：C:\Users\username\AppData\Local\Programs\Python\Python312）
# 設定 > システム > 詳細設定 > 環境変数 から PATH に追加
```

**macOS / Linux:**
```bash
# Python 3 のバージョン確認
python3 --version

# または python コマンドが python3 にエイリアスされているか確認
python --version
```

### モジュールが見つからないエラー

**症状**: `ModuleNotFoundError: No module named '...'`

**対応**:
```powershell
# (Windows 11) 仮想環境が有効化されているか確認
# プロンプトに (venv) が表示されていることを確認

# Python のインポートパスを確認
python -c "import sys; print(sys.path)"

# 仮想環境内の Python パスを確認
python -c "import sys; print(sys.executable)"
```

### JSON ファイルの読み込みエラー

**症状**: `FileNotFoundError` または `JSONDecodeError`

**Windows 11:**
```powershell
# テストケースファイルが存在するか確認
dir test_programmer\test_cases\

# JSON ファイルの形式を検証
python -m json.tool test_programmer\test_cases\mixed_tp_same_height.json
```

**macOS / Linux:**
```bash
# テストケースファイルが存在するか確認
ls test_programmer/test_cases/

# JSON ファイルの形式を検証
python3 -m json.tool test_programmer/test_cases/mixed_tp_same_height.json > /dev/null
```

### ポート競合エラー

**症状**: `Address already in use` エラー

**Windows 11:**
```powershell
# 別のポートを指定して起動
python test_programmer/serve_testcase_viewer.py --port 8084

# または別のアプリケーション/プロセスがポートを使用していないか確認
netstat -ano | findstr :8083
# 該当 PID を確認したら、タスクマネージャーから終了
```

**macOS / Linux:**
```bash
# 別のポートを指定して起動
python3 test_programmer/serve_testcase_viewer.py --port 8084

# または既存プロセスを終了
lsof -i :8083
kill -9 <PID>  # PID は lsof コマンドの結果から確認
```

---

## 次のステップ

1. **[使用ガイド](/palletizing_prototype/wiki/user-guide.html)** で プロジェクト全体の構成と使用方法を理解
2. **[アルゴリズム説明](/palletizing_prototype/wiki/algorithm-explanation.html)** で 技術的な詳細を確認
3. **[ドキュメント](/palletizing_prototype/wiki/documentation.html)** で データフォーマットとエージェント詳細を参照

---

## サポート

質問や問題がある場合は、以下をご覧ください：

- [GitHub リポジトリ - Issues](https://github.com/TakahiroNakadaTMC/palletizing_prototype/issues)
- [プロジェクト主ドキュメント - GEMINI.md](../../../GEMINI.md)
- 各コンポーネントの詳細ドキュメント（`*/README.md`）
