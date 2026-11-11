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
├── results/         # パレタイズ結果JSONの生成先 (Git管理外)
└── README.md        # 本ドキュメント
```

---

## 3. テスト実行方法

### 品番方式（第4段階・明示指定）

```powershell
python .\tester\run_tests.py --catalog --output-dir .\tester\catalog_results\review_phase4
```

[品番ケース一式](../box_research/catalog/test_cases.json) の `approval_state` が
trueのケースだけを、読み込み時点の同じDB・ケース一式で計算します。
旧ケースの採否は使いません。`--output-dir` は毎回新しいフォルダを指定してください。
既存フォルダや旧 `tester/results/` 配下への保存は拒否し、古い結果との混在を防ぎます。
`tester/catalog_results/` は生成物としてGit管理外です。

各 `result_<ケース名>.json` と `run_manifest.json`（今回の実行一覧）を保存します。
実行一覧はケース別のPASS／FAIL／ERROR、配置／投入／未配置数、違反、実行時間、
使用したDB一式の照合値を記録します。実行エラーのケースには今回の結果ファイルを作りません。
FAILとERRORは区別し、どちらかがあれば終了コード1、両方なければ0です。
未配置は制約FAILとは別であり、未配置数が0かどうかも確認してください。
エラーケースの箱数は算出できないため、実行一覧の数量合計には含みません。

第5段階で新結果の独立検証と3D表示に対応しました。

```powershell
python .\supervisor\validate.py --catalog-results .\tester\catalog_results\review_phase4 --report-dir .\supervisor\catalog_reports\review_phase4
python .\visualizer\serve_3d_viewer.py --results-dir .\tester\catalog_results\review_phase4
```

検証は実行一覧を使い、現在の採用済み全件がそろっていることも確認します。
DBや品番ケースを変更した場合は、新規結果フォルダへ再計算してから検証してください。
今回の[第5段階結果](catalog_results/phase5_verified/)は150件、
148件PASS／2件FAIL、投入3132箱／配置2588箱／未配置544箱、実行エラー0件です。
正式な独立検証も全件で計算判定と一致しました。
結果項目は [計算モジュールの説明](../algorithm_programmer/README.md#品番方式の計算第4段階) を参照してください。

### 旧方式（既定動作を維持）

```bash
# 全テストケースの一括実行
python3 tester/run_tests.py
```

`test_programmer/test_case_approval.json` の採否状態を参照し、`true` のテストケースのみ実行します。採否状態に登録されていないケースは実行対象外です。supervisor も同じ状態を使い、採用済みケースの結果だけを検証します。

実行が完了すると、`tester/results/` 配下に各テストケースのシミュレーション結果（配置座標、回転、積み順、支持関係、荷姿サマリー）が出力されます。
これらは `visualizer`（3Dビューワ）および `supervisor`（制約バリデータ）の入力として使用されます。
結果JSONは再生成可能な出力としてGit管理対象外です。新しいチェックアウト環境では、ビューワや制約バリデータを実行する前にテストを実行して結果を生成してください。
