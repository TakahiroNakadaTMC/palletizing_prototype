# テスターモジュール仕様書 (tester/)

**文書番号:** TST-DOC-2026-001  
**作成日:** 2026-08-19  
**担当エージェント:** `tester`  
**対象読者:** `orchestrator`, `algorithm-programmer`, `supervisor`  

---

## 1. 概要

本ディレクトリは、パレタイズアルゴリズムの自動テスト実行、シミュレーション結果データ、および実行ログの管理を行います。

---

## 2. 構成

```text
tester/
├── run_tests.py     # 全テストケース自動一括実行スクリプト
├── results/         # パレタイズ結果JSONデータ群 (result_*.json)
└── README.md        # 本ドキュメント
```

---

## 3. テスト実行方法

```bash
# 全テストケースの一括実行
python3 tester/run_tests.py
```

実行が完了すると、`tester/results/` 配下に各テストケースのシミュレーション結果（配置座標、回転、積み順、支持関係、荷姿サマリー）が出力されます。
これらは `visualizer`（3Dビューワ）および `supervisor`（制約バリデータ）の入力として使用されます。
