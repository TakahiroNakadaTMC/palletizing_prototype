---
layout: page
title: セットアップ&インストール
---

# セットアップ&インストール

本ページでは、パレタイズ試作プロジェクトを実行するための環境構築手順を説明します。

## 前提条件

以下のソフトウェアがインストール済みであることを前提としています：

- OS: macOS, Linux, または Windows (WSL2 推奨)
- Git
- Python 3.8 以上

## Python 環境のセットアップ

### 1. リポジトリのクローン

```bash
git clone https://github.com/TakahiroNakadaTMC/palletizing_prototype.git
cd palletizing_prototype
```

### 2. Python 仮想環境の作成

```bash
python3 -m venv venv
```

### 3. 仮想環境の有効化

**macOS / Linux:**
```bash
source venv/bin/activate
```

**Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
```

## 依存パッケージのインストール

### 必須パッケージのインストール

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 開発用パッケージのインストール（オプション）

```bash
pip install -r requirements-dev.txt
```

## 初期設定

### 環境変数の設定

プロジェクトルートに `.env` ファイルを作成し、以下の環境変数を設定してください：

```env
# Example environment variables
PROJECT_NAME=palletizing_prototype
LOG_LEVEL=INFO
```

### 設定ファイルの確認

各サブエージェント用の設定ファイルが `.agent/` ディレクトリに配置されていることを確認してください。

---

## トラブルシューティング

### 仮想環境が有効化されない場合

- `which python` コマンドで仮想環境のパスが表示されるか確認してください
- 異なるシェル（bash, zsh, fish など）を使用している場合は、適切なアクティベーションスクリプトを実行してください

### パッケージのインストールが失敗する場合

- `pip --version` でバージョンを確認し、必要に応じてアップグレードしてください
- `pip install --upgrade pip setuptools wheel` で基本ツールを更新してください
- ネットワーク接続を確認してください

---

**次のステップ**: [使用ガイド](/palletizing_prototype/wiki/user-guide.html)を参照してプロジェクト構成を理解してください。
