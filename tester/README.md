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
├── catalog_results/ # 品番方式結果JSONの生成先 (Git管理外)
└── README.md        # 本ドキュメント
```

---

## 3. テスト実行方法

### 品番方式（既定動作）

```powershell
python .\tester\run_tests.py
python .\tester\run_tests.py --output-dir .\tester\catalog_results\review_phase6
```

[品番ケース一式](../box_research/catalog/test_cases.json) の `approval_state` が
trueのケースだけを、読み込み時点の同じDB・ケース一式で計算します。
旧ケースの採否は使いません。`--output-dir` 省略時は時刻名の新規フォルダを自動作成します。
既存フォルダは再利用しません。結果は常に新規フォルダへ保存されます。
`tester/catalog_results/` は生成物としてGit管理外です。

各 `result_<ケース名>.json` と `run_manifest.json`（今回の実行一覧）を保存します。
実行一覧はケース別のPASS／FAIL／ERROR、配置／投入／未配置数、違反、実行時間、
使用したDB一式の照合値を記録します。実行エラーのケースには今回の結果ファイルを作りません。
ケースのKEY2から現在のスキッドDBのパレット・荷山上限を読み取ります。
設定未登録のケースはERRORとして一覧へ記録し、他のケースの実行は続けます。
採用状態を自動では変更しません。
FAILとERRORは区別し、どちらかがあれば終了コード1、両方なければ0です。
未配置は制約FAILとは別であり、未配置数が0かどうかも確認してください。
エラーケースの箱数は算出できないため、実行一覧の数量合計には含みません。

```powershell
python .\supervisor\validate.py --results-dir .\tester\catalog_results\review_phase6 --report-dir .\supervisor\catalog_reports\review_phase6
```

検証は実行一覧を使い、現在の採用済み全件がそろっていることも確認します。
DBや品番ケースを変更した場合は、新規結果フォルダへ再計算してから検証してください。
今回の[第5段階結果](catalog_results/phase5_verified/)は150件、
148件PASS／2件FAIL、投入3132箱／配置2588箱／未配置544箱、実行エラー0件です。
正式な独立検証も全件で計算判定と一致しました。
結果項目は [計算モジュールの説明](../algorithm_programmer/README.md#品番方式の計算第4段階) を参照してください。

旧方式ランナーは廃止されました。`tester/run_tests.py` は品番方式のみを実行します。
