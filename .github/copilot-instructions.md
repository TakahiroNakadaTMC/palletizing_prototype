# GitHub Copilot Instructions

このプロジェクトは嵌合・リブ付き空箱のパレタイズ試作です。
現行仕様は [README](../README.md) と [荷姿制約](../constraints/constraints.md) を正とします。

## 運用データ

- 品番方式だけを使用します。旧DB・旧ケース・旧結果の編集、実行、検証、閲覧は廃止済みです。
- 品番DB：`box_research/catalog/box_type_db.json`
- 共通モデルDB：`box_research/catalog/box_model_db.json`
- 蓋DB：`box_research/catalog/lid_db.json`
- スキッドDB：`box_research/catalog/skid_db.json`（KEY2、仕入先、使用パレット、荷山上限、候補品番、履歴）
- 仕入先対応表：`box_research/catalog/supplier_db.json`（仕入先の数字4桁と仕入先名）
- ケース・採用状態：`box_research/catalog/test_cases.json`
- パレットDB：`box_research/pallet_db.json`
- 移行・モデル名称変更履歴：`box_research/catalog/migration.json`
- 元CSVと移行時の対応表は資料です。運用データの自動再生成に使用しません。
- ケースの `box_list` は `part_number` と `count` を指定します。蓋は品番から自動決定します。
- ケースは版2で1つの `skid_id`（KEY2）を参照します。パレット・荷山上限はケースに重複保存せず、現在のスキッドDBから表示・計算時に解決します。
- 未登録のパレット・荷山上限があるKEY2は新規ケース作成・計算を拒否します。仮の値で補いません。
- スキッド変更は関連ケース・変更前後を確認して保存し、更新日時・変更履歴をDBに残します。使用中の候補品番は先にケースを修正しない限り削除できません。
- スキッドIDは仕入先4桁数字＋工区1桁英数字＋出荷場3桁英数字または空欄＋コース1桁英字。半角・英字大文字・先頭0保持。「仕入先コード」と呼ばず「仕入先」と表示し、対応する会社名は「仕入先名」と区別します。
- 未登録の仕入先は対応表を先に登録します。ID変更は確認後にケース参照も同時更新し、履歴を残します。仕入先名の訂正は同名の対応表・品番・スキッド・ケース・パレットへの影響を確認して一括保存します。
- 数量入力の空欄・0は不使用として保存せず、使用分のみ整数1～500を保存します。全品番不使用は保存できません。
- 品番は全仕入先を通じて一意です。箱名称の重複は許可します。
- 共通モデル名はIDと表示名を兼ねます。変更は影響確認付きの保存処理を利用します。
- DB編集では正規化・参照検証・版照合・保存失敗時の復元を迂回しません。
- 英数字は半角、半角カタカナは全角にします。記号等の扱いは既存の `normalize_id` に従います。
- LF/CRLFの違いでは内容変更と判断しません。実際の内容変更は照合エラーとして扱います。

## 実行・検証

```powershell
python .\box_research\serve_viewer.py
python .\test_programmer\serve_testcase_viewer.py
python .\tester\run_tests.py --output-dir .\tester\catalog_results\my_run
python .\supervisor\validate.py --results-dir .\tester\catalog_results\my_run --report-dir .\supervisor\catalog_reports\my_run
python .\visualizer\serve_3d_viewer.py --results-dir .\tester\catalog_results\my_run
```

- 結果・レポートの出力先は実行ごとに新規フォルダを使います。
- 採用状態は実行対象を示し、制約PASSを意味しません。
- 終了コードだけでなく実行一覧、PASS/FAIL/ERROR、投入・配置・未配置数を確認します。
- 独立検証は実行一覧と現在のDB・ケース・パレットとの整合性を確認します。
- 既存の古い結果を今回の結果として使いません。DB編集後は再計算します。
- 単一ケースは `python .\algorithm_programmer\cli.py --catalog-case othics_6 -o <出力JSON>`。
- 廃止済みのケース生成、一括ループ、旧形式への変換手順を復活させません。

## 計算と安全条件

- 物理的な段積み判定には共通モデルを使い、結果には品番・箱名称・仕入先・モデル・蓋を残します。
- 同モデル・同蓋をまとめて計算し、積み順へ入力順で品番を配分します。比率平準化は未実装です。
- TP箱の異モデル段積みを一律禁止しません。嵌合・支持・干渉条件は維持します。
- 非TP箱は同モデル・外形位置一致・適切な単一支持が必要です。
- 外嵌め蓋付きTP箱は同蓋・箱蓋外形位置一致・単一支持が必要です。異モデルも許可されます。
- 回転は0/90度のみ、天地固定。上段箱の `fitting_depth` を使います。
- 最大外形L/W/Hはケースが参照するスキッド設定以下で境界値を含みます。固定800mm下限はありません。
- はみ出しは確認情報。底面支持率85%以上、センタリング各方向0.01mm以内は必須です。
- 直接支持する下段が幅・奥行きの両方で上段より1.0mm超大きい組合せは禁止です。
- 上載せ平パレットの支持・高さ差・連続辺・中央接触条件は制約仕様に従います。
- Supervisorは計算エンジンの合否を信用せず、独立して再検証します。
- 実耐荷重・たわみ・輸送安定性を保証するものではありません。

## 開発規約

- Python 3.8以降の構文を対象に、既存の型ヒント・dataclass・命名規約を守ります。
- 関数・変数は `snake_case`、クラスは `PascalCase`、定数は `UPPER_SNAKE_CASE`。
- テストは `*_test.py`。関連する最小のテストを実行し、必要なら全体へ広げます。
- 寸法は **L × W × H**。DBでは `length` がL、`width` がWです。
- 結果の `dimensions.width/length` は回転後X/Y寸法です。保存値や座標の意味を変えません。
- 結果は `schema_version: 2`、`input_mode: "part_number"`、
  `coordinate_reference: "combined_footprint_min_xy_top_z"` を使用します。
- 結果XYは箱・蓋外接形状の最小角、Zは蓋込み上面です。
- 実荷姿の数量・品番・固定蓋・パレット条件は根拠なく変更しません。
- 不正な入力・保存失敗を黙って無視せず、利用者へ明示します。
- 仕様変更は利用者の合意を得て、関連README・指示書・テストを同期します。
