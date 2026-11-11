# テストケース仕様書 (test_programmer/)

<!-- markdownlint-configure-file { "MD013": { "tables": false } } -->

**文書番号:** TP-DOC-2026-001  
**作成日:** 2026-08-19  
**担当エージェント:** `test-programmer`  
**対象読者:** `tester`, `algorithm-programmer`, `supervisor`, `orchestrator`  

---

## 1. 概要

本ディレクトリは、パレタイズアルゴリズムの評価・シミュレーションに使用するテストデータ生成スクリプトおよびテストケースJSON群を管理します。

### 品番方式のケース編集（第3段階・切替準備用）

`python .\test_programmer\serve_testcase_viewer.py` で起動し、
従来画面の上部リンク「品番方式のケース編集（品番方式CLI対応）」を開いてください。
既定URLは `http://localhost:8083/catalog_cases.html` です。
新DBの編集も同じポートの `http://localhost:8083/catalog_viewer.html` から利用できます。

- 仕入先→品番→数量で入力し、箱名称・共通箱モデル・固定蓋を自動表示します。
  蓋は品番DBで決まり、ケースでは変更できません。
- パレットは仕入先に対応する型番と標準パレットから選びます。
- 元の150ケース・200箱行から数量・説明・パレット条件・採用状態を維持したコピーを作成済みです。
  複数候補だった80行は合意済みの第一候補を使用し、編集画面で移行時の候補を確認できます。
- 「入力を確定」は画面内の編集です。上部の「品番方式の変更をまとめて保存」でファイルに保存します。
- 新規ケースは不採用で作成します。採用・解除は次回の品番方式一括実行に反映します。旧方式の実行対象は変更しません。

保存先は [準備用ケース](../box_research/catalog/test_cases.json) です。
既存の [計算用ケース](test_cases/) と [採用状態](test_case_approval.json) は変更していません。
第4段階でCLI・一括実行へ接続しました。保存済みケースの単発実行は
`python .\algorithm_programmer\cli.py --catalog-case othics_6 -o .\tester\catalog_results\othics_6.json`、
採用済み一括実行は
`python .\tester\run_tests.py --catalog --output-dir .\tester\catalog_results\review_phase4` です。
ケース一覧をまとめたJSON自体をCLIの位置引数へ渡すのではなく、`--catalog-case` で1件を選択してください。
第5段階で新結果を直接読むSupervisor・3D表示にも対応しました。
検証は `--catalog-results`、表示は `--results-dir` で品番方式の結果フォルダを指定します。
保存後は古い結果を現在のDBで読み替えず、新しいフォルダへ再計算してください。
詳細は[第4段階の計算説明](../algorithm_programmer/README.md#品番方式の計算第4段階)を参照してください。
画面・保存API・検証方法の詳細は[箱DBの第3段階ガイド](../box_research/README.md#db品番ケース編集画面第3段階計算への切替前)を参照してください。
第4段階は画面操作・割当ての確認後に合意を受けて実装しました。

実荷姿に基づく基準テストケースは30件で、全件が採用状態です。内訳はアイシン11件、
アーレスティ2件、アート金属1件、グゼー1件、ニッタン2件、NOK2件、
オティックス9件、ROKI2件です。投入要求数は合計625箱です。

2026-11-09: ユーザー依頼により、各基準ケースの箱数を箱種ごとに -20%、-10%、+10%、+20% した
評価用ケースを追加しました。名称は基準ケース名に `_m20`、`_m10`、`_p10`、`_p20` を付け、
各箱種の数量は四捨五入（0.5は切り上げ）、最小1箱としています。
派生ケースは120件で、各変動幅の投入要求数は順に498箱、568箱、689箱、752箱です。
基準30件を含む全150件を採用状態にしています。派生ケースは実荷姿の記録ではなく、
数量変動に対するアルゴリズム評価用です。

これらは実際の荷姿パターンに基づくケースです。箱の投入数量、蓋指定、
`pallet_id` とケース固有の荷姿上限（`max_x_span,max_y_span,max_height`）を保持しています。
パレット本体L/W/Hは参照先のパレットDBから実行時に取得します。
採用状態は一括実行の対象であることを示し、
配置結果の制約検証PASSを意味しません。

2026-11-05: パレットDB連携を追加しました。既存ケースにはケース名に基づく仕入先名を登録し、
仕入先とパレット寸法が一致する実型番を22件に、標準パレットを8件に設定しました。
箱の数量、蓋、パレットの寸法値・上限値、採用状態は変更していません。

2026-11-05: ユーザー確認に基づき、`othics_9` の荷山最大Xを1110 mmから1135 mmへ訂正しました。
箱型番・投入数34箱・蓋・他のパレット条件・全30件の採用状態は変更していません。

---

## 2. 基準テストケース一覧

以下は実荷姿に基づく基準ケース30件の一覧です。数量変動評価ケース120件は
同じ `test_cases/` ディレクトリに保存され、基準名と変動幅の接尾辞で識別できます。

| テストケース | 荷姿名 | 対象箱型番 | 箱数 |
| :--- | :--- | :--- | :---: |
| [aisin.json](./test_cases/aisin.json) | アイシン西尾　インマニHV | SPZ46405 | 11 |
| [aisin_2.json](./test_cases/aisin_2.json) | アイシン小川　HVダンパー | TP331 | 63 |
| [aisin_3.json](./test_cases/aisin_3.json) | アイシン西尾　ｵｲﾙﾎﾟﾝﾌﾟ | TP342 | 12 |
| [aisin_4.json](./test_cases/aisin_4.json) | アイシン半田　混載 | SPG34229、SPG34230、SP342 | 30 |
| [aisin_5.json](./test_cases/aisin_5.json) | AKK刈谷 | TP331 | 10 |
| [aisin_6.json](./test_cases/aisin_6.json) | TCC NO1 | SPZ36408 | 23 |
| [aisin_7.json](./test_cases/aisin_7.json) | TCC No2 | SPZ36406 | 17 |
| [aisin_8.json](./test_cases/aisin_8.json) | アイシン化工　インマニ | SPZ46404 | 4 |
| [aisin_9.json](./test_cases/aisin_9.json) | TCC No1 1.5L | SPZ36404 | 8 |
| [aisin_10.json](./test_cases/aisin_10.json) | TCC No2 コンベ | SPZ36403 | 4 |
| [aisin_11.json](./test_cases/aisin_11.json) | TCC No2 HV | SPZ36403 | 15 |
| [arresuthi.json](./test_cases/arresuthi.json) | アーレスティ　コンベ | SP4625 | 6 |
| [arresuthi_2.json](./test_cases/arresuthi_2.json) | アーレスティ　HV | SP4625 | 11 |
| [art.json](./test_cases/art.json) | アート金属　ピストン | NPAP5 | 44 |
| [guze.json](./test_cases/guze.json) | グゼー | STP342B | 18 |
| [nittan.json](./test_cases/nittan.json) | EXバルブ | NPH010 | 8 |
| [nittan_2.json](./test_cases/nittan_2.json) | EXバルブ | NPH010 | 9 |
| [nok.json](./test_cases/nok.json) | NOK混載 | NP000002、NP000003、TP131、TP331 | 33 |
| [nok_2.json](./test_cases/nok_2.json) | ダンパープーリ | NP000008 | 31 |
| [othics.json](./test_cases/othics.json) | オティックス　ｴﾝﾄﾞｷｬｯﾌﾟ | TP131 | 4 |
| [othics_2.json](./test_cases/othics_2.json) | ローラーロッカー | TP3415、NP262D、TP331 | 28 |
| [othics_3.json](./test_cases/othics_3.json) | バランサー | NP20B | 15 |
| [othics_4.json](./test_cases/othics_4.json) | ドライブギア | SP3315B | 5 |
| [othics_5.json](./test_cases/othics_5.json) | ﾊｳｼﾞﾝｸﾞ　1.5L | NP20B | 42 |
| [othics_6.json](./test_cases/othics_6.json) | ハウジング　2.0L | NP22C、NPP24 | 30 |
| [othics_7.json](./test_cases/othics_7.json) | ハウジング　2.0L | NP22C、NPP24 | 29 |
| [othics_8.json](./test_cases/othics_8.json) | ハウジング　2.0L | NP22C、NPP24 | 35 |
| [othics_9.json](./test_cases/othics_9.json) | ハウジング　1.5L | NP20B | 34 |
| [roki.json](./test_cases/roki.json) | ROKI | TP3415 | 28 |
| [roki_2.json](./test_cases/roki_2.json) | ROKI | TP3415 | 18 |

### 数量変動評価ケース

各基準ケースに対し、箱種ごとの `count` を倍率で変えた4ケースを作成しています。
パレット条件、箱種、蓋指定、その他のケース情報は基準ケースから引き継いでいます。

| 接尾辞 | 変動 | 例 |
| :--- | :---: | :--- |
| `_m20` | -20% | `aisin_5_m20.json` |
| `_m10` | -10% | `aisin_5_m10.json` |
| `_p10` | +10% | `aisin_5_p10.json` |
| `_p20` | +20% | `aisin_5_p20.json` |

数量は箱種ごとに独立して四捨五入し、0.5は切り上げ、最小値を1箱とします。
このため、小数量の箱種では指定率と実際の増減率が一致しない場合があります。
派生ケースも `test_case_approval.json` で採用済みのため、一括実行の対象です。

---

## 3. テストデータの再生成方法

現行のテストケース30件は実際の荷姿パターンに基づいて管理しており、
`generate_testcases.py` はこの一覧を再生成するスクリプトではありません。
同スクリプトは旧TP規格テスト群と蓋付き派生ケースを生成するため、
実行すると現行ケースと異なるファイルを作成・上書きする可能性があります。
現行ケースの一括再生成には使用しないでください。

ケースを編集・追加する場合はテストケースビューアを使用し、ケースJSONと採用状態を保存してください。

---

## 4. テストパターン承認・編集ビューア

テストケースの投入箱リスト（荷山構成）を一覧確認し、個別採用/解除・投入数量の変更・新規パターンの作成・一括保存を行えるWebビューワを提供しています。

```bash
python3 test_programmer/serve_testcase_viewer.py
```

WindowsのPowerShellでは、プロジェクトルートで次を実行してください。
追加インストールや環境変数の設定は不要です。

```powershell
py .\test_programmer\serve_testcase_viewer.py
```

直接起動と `py -m test_programmer.serve_testcase_viewer` の両方に対応します。
直接起動時はスクリプト自身の場所からプロジェクトルートを求めるため、
作業フォルダーが異なる場合もスクリプトの絶対パスで起動できます。

ブラウザで `http://localhost:8083` を開いてご利用いただけます。
ポート使用中は8084～8092を試すため、コンソールに表示されたURLを確認してください。
終了するにはPowerShellで `Ctrl+C` を押します。

採否状態は `test_case_approval.json` に共有保存され、初期登録済みケースは採用、新規ケースは未採用になります。ビューアで採否を変更した後、「テストケース一括保存」を押すとケースと採否状態が保存されます。テストランナーは採用ケースだけを実行します。ビューアでケースを削除して一括保存すると、対応するケースJSONも削除されますが、過去の実行結果JSONは履歴として残ります。

2026-11更新: 作成/編集モーダルでは仕入先とパレット型番を選びます。
型番候補にはL×W×Hを表示し、本体寸法は選択された `pallet_id` から実行時に取得します。
本体寸法は画面で個別編集できず、ケースJSONにも重複保存しません。実行結果には検証用の寸法スナップショットを記録します。
ケースごとに編集できるのは
`max_x_span`、`max_y_span`、`max_height` で、既定値は `1360,1100,1200`、
各値は正の有限数、かつ `max_x_span >= max_y_span` を必須とします。
保存時は旧キー（`min_x_span`,`min_y_span`,`max_overhang_x_mm`,`max_overhang_y_mm`,`max_small_edge_overhang_mm`）を除去し、
旧形式に残る本体L/W/Hも除去し、`pallet` は荷姿上限3項目のみを保存します。

2026-11-05更新: パレット設定の前に仕入先、続けてパレット型番を選択できます。
型番候補にはL×W×Hを表示し、選択した `pallet_id` から実行時に本体寸法を解決します。
型番未登録時の「標準パレット（型番未指定）」（1200×1000×130 mm）は編集不可の共通候補です。
個別寸法入力はなく、型番または標準パレットの選択が必須です。
`max_x_span`、`max_y_span`、`max_height` はそのケースの値を維持します。
ケースJSONには仕入先を `supplier_name`、DBから選んだ仕様を `pallet_id` として保存します。

### 保存前チェックの役割（2026-11-06）

- **画面側**は入力ミスをその場で知らせます。
- **サーバー側**も保存直前に最終確認します。箱・蓋IDの存在、
  箱と実蓋の互換性、数量（1～500の整数）、説明、パレットの存在、
  仕入先との対応、荷姿上限を確認します。`type: "NONE"` の蓋は全箱で選択できます。
- DBの形式・互換蓋の参照・パレット仕様のチェックは
  [共通チェック処理](../box_research/database_validation.py)を使用します。
  別のDBサーバーを起動する必要はありません。
- 内容が不正な場合はケース名・箱行などを含む理由を返し、
  一括保存対象のケース・削除対象・採否状態を書き換える前に処理を止めます。
  通信・ディスク障害時の複数ファイル保存を一括で元に戻す機能を追加したものではありません。
- DBを編集するときのチェック（使用中データの削除防止など）は、
  引き続きDB編集サーバーが担当します。DBやケースの保存形式は変更しません。

関連する回帰テスト:

```powershell
py -m unittest box_research.database_validation_test box_research.serve_viewer_test test_programmer.serve_testcase_viewer_test algorithm_programmer.cli_test -q
```

---

## 5. Phase 3: 蓋選択機能 (Lid Selection Feature)

一覧の「投入箱内訳」には、箱型番・数量とともに
「蓋なし」「蓋あり・内嵌め」「蓋あり・外嵌め」などを同じスタイルの文字で表示します。
各投入行を個別に表示し、ツールチップには寸法・蓋ID・蓋名称を併記します。
蓋ID省略時は既定の無蓋を参照し、未知の蓋IDや蓋DB未取得の場合は「蓋情報不明」、
嵌め方未登録の場合は「蓋あり・嵌め方未設定」と表示します。蓋の実際の色情報は使用しません。

作成・編集画面の蓋選択肢は「蓋名称（外嵌め／内嵌め／なし）」形式で表示します。
嵌め方は蓋DBの `fit_type` を参照し、未登録の場合は「嵌め方未設定」と表示します。
箱型番を変更した場合も同じ表記で更新します。
保存される値は従来どおり `lid_id` のみで、テストケース形式や配置計算は変更しません。

### 5.1 概要

Phase 3-1 では、テストケースに **箱ごとの蓋（Lid）選択機能** を統合しました。各テストケース内の **個別の箱** に対して蓋を指定できるようになり、パレタイズシミュレーション時に箱ごとに異なる蓋を検証できます。

**重要**: 蓋選択は **テストケースレベル** ではなく **箱レベル** で行われます。同一テストケース内の複数の箱に対して、それぞれ異なる蓋を割り当てることが可能です。

### 5.2 テストケースJSONスキーマ（Phase 3-1から変更）

すべてのテストケースJSONで、`box_list` 配列内の **各箱に** `"lid_id"` フィールドが追加されました：

#### 変更前（Phase 3）

```json
{
  "name": "example_single_case",
  "description": "...",
  "pallet": {...},
  "box_list": [
    {"box_id": "TP-332", "count": 10}
  ],
  "lid_id": "無蓋"                 // ← テストケースレベル（全箱共通）
}
```

#### 変更後（Phase 3-1）✅

```json
{
  "name": "example_single_case",
  "description": "...",
  "pallet": {...},
  "box_list": [
    {
      "box_id": "TP-332",
      "count": 10,
      "lid_id": "無蓋"             // ← 各箱レベル（箱ごとに異なる蓋を指定可能）
    }
  ]
}
```

#### 混載テストケースの例

```json
{
  "name": "example_mixed_case",
  "box_list": [
    {"box_id": "TP-332", "count": 4, "lid_id": "TP330フタ"},
    {"box_id": "TP-342", "count": 4, "lid_id": "TP34蓋(IC)"},
    {"box_id": "TP-362", "count": 4, "lid_id": "TP360フタ"},
    {"box_id": "TP-462", "count": 4, "lid_id": "TP460フタ"}
  ]
}
```

### 5.3 UI：箱ごとの蓋選択

#### testcase_viewer.html: 画面構成

#### 各箱行に蓋選択ドロップダウン

モーダル内の投入箱リストが、各箱ごとに4列で表示されます：

1. **箱型番セレクト** （例: TP-332）
2. **投入数量** （例: 60）
3. **蓋選択ドロップダウン** （例: 無蓋 / TP330フタ / TP340フタ / ...）
4. **削除ボタン**

```html
<div class="box-input-row flex items-center gap-2 bg-slate-50 p-2 rounded-lg ...">
  <div class="flex-1 min-w-max">
    <select class="box-id-select ...">
      <option value="TP-332">TP-332</option>
      ...
    </select>
  </div>
  <div class="w-20">
    <input type="number" class="box-count-input ..." value="60" />
  </div>
  <!-- NEW: Lid selector column -->
  <div class="w-32">
    <select class="box-lid-select ...">
      <option value="無蓋">蓋なし</option>
      <option value="TP330フタ">TP-330系用</option>
      <option value="TP340フタ">TP-340系用</option>
      ...
    </select>
  </div>
  <button type="button" class="btn-remove-row ...">
    <i data-lucide="trash"></i>
  </button>
</div>
```

#### JavaScript 関数の修正

##### `addBoxRow(selectedId, count, lidId)` (修正)

**パラメータ**:

- `selectedId` (string, default: `''`): 箱型番（例: `'TP-332'`）
- `count` (number, default: `10`): 投入数量
- `lidId` (string, default: `'無蓋'`): 蓋ID

**処理内容**:

- Box行に **3番目の列** として蓋セレクトボックスを追加
- **選択された箱の `compatible_lids` に含まれる実蓋** と、全箱共通の無蓋を表示
- 箱型番が変更されたら、蓋ドロップダウンも自動更新

**重要**: 各箱型番の対応蓋は `box_research/box_db.json` の `"compatible_lids"` フィールドで管理されています：

例:

```json
"TP-332": {
  "id": "TP-332",
  ...
  "compatible_lids": ["TP330フタ", "サンボックス330フタ"]  // 箱に対応する実蓋
}
```

**UI動作**:

1. 最初に箱を選択 → その箱の対応蓋のみドロップダウンに表示
2. 箱型番を変更 → 新しい箱の対応蓋に自動更新

```javascript
function addBoxRow(selectedId = '', count = 10, lidId = '無蓋') {
  // ...
  // 選択された箱の対応蓋リストを取得
  const selectedBox = masterBoxDB[selectedId];
  const noLidId = Object.keys(lidDB).find(id => lidDB[id].type === 'NONE');
  const compatibleLids = [...(selectedBox?.compatible_lids || []), noLidId];
  
  // 対応する実蓋と全箱共通の無蓋をドロップダウンに追加
  const lidOptions = [];
  compatibleLids.forEach(id => {
    const lid = lidDB[id] || { name: id };
    lidOptions.push(`<option value="${id}" ...>${lid.name}</option>`);
  });
  
  // 箱型番変更イベント: 対応蓋を自動更新
  row.querySelector('.box-id-select').addEventListener('change', (e) => {
    const newBoxId = e.target.value;
    const newBox = masterBoxDB[newBoxId];
    const noLidId = Object.keys(lidDB).find(id => lidDB[id].type === 'NONE');
    const newCompatibleLids = [...(newBox?.compatible_lids || []), noLidId];
    // 蓋ドロップダウンを newCompatibleLids で再構築
    // ...
  });
}
```

##### `openModal()` (修正)

既存テストケースを編集モーダルで開く場合、各箱の蓋情報を復元します：

```javascript
function openModal(tcName = null) {
  // ...
  if (tcName && testCasesData[tcName]) {
    const tc = testCasesData[tcName];
    (tc.box_list || []).forEach(b => {
      addBoxRow(b.box_id, b.count, b.lid_id || '無蓋');  // ← 蓋を復元
    });
  }
  // ...
}
```

##### フォーム送信ハンドラ (修正)

保存時に、各箱ごとに選択された蓋を JSON に含める：

```javascript
document.getElementById('form-testcase').addEventListener('submit', (e) => {
  e.preventDefault();
  const boxRows = document.querySelectorAll('.box-input-row');
  const boxList = [];
  boxRows.forEach(r => {
    const bid = r.querySelector('.box-id-select').value;
    const cnt = parseInt(r.querySelector('.box-count-input').value) || 1;
    const lid = r.querySelector('.box-lid-select').value || '無蓋';  // ← 各行から蓋を取得
    if (bid && cnt > 0) {
      boxList.push({ box_id: bid, count: cnt, lid_id: lid });  // ← 各箱に蓋を含める
    }
  });
  const tcObj = {
    name: name,
    description: desc,
    pallet: PALLET_SPEC,
    box_list: boxList  // ← テストケースレベルの lid_id は削除
  };
  // ... 保存処理
});
```

### 5.4 蓋DB API エンドポイント

#### `/api/lids` (GET)

蓋データベースをJSON形式で返却します。

**リクエスト**:

```http
GET /api/lids HTTP/1.1
```

**レスポンス**:

```json
{
  "TP330フタ": {
    "id": "TP330フタ",
    "name": "クリア蓋 TP-330系用",
    "type": "TP",
    "width": 335,
    "length": 335,
    "thickness": 15,
    "fit_type": "外嵌め",
    "description": "TP-330系1型対応（TP-331, TP-332, TP-333用）"
  },
  "無蓋": {
    "id": "無蓋",
    "name": "蓋無",
    "type": "NONE",
    "description": "蓋を使用しない荷姿（デフォルト）"
  }
}
```

**実装** (`serve_testcase_viewer.py`):

- `box_research/lid_db.json` をサーバーから読み込んで返す
- ファイルが存在しない場合は空オブジェクト `{}` を返す

### 5.5 現行テストケースの蓋指定

#### 現行テストケースの蓋指定

現行30件では、各箱行に実際の投入パターンに応じた `lid_id` を保存しています。
蓋なしの場合も、蓋DBの「無蓋」IDを指定します。
このデータは箱DBの `compatible_lids` をもとに確認されます。

#### ユーザーによる蓋変更

`testcase_viewer.html` で編集モーダルを開き、**各箱行の蓋ドロップダウン** から別の蓋を選択することで、箱ごとに蓋を変更できます。

手順:

1. カード編集アイコンをクリック
2. 修正モーダルが開く
3. 各箱行の **蓋ドロップダウン** から選択
4. 「保存する」をクリック
5. テストケースJSON に反映

### 5.6 旧テストケース生成処理について

`generate_testcases.py` には旧TP規格テスト群と `*_with_lids.json` の生成処理が残っています。
これは現行の実荷姿ケース30件とは別の旧生成仕様であり、現在のケース一覧を再現しません。
現行ケースの管理・実行対象の選択にはテストケースビューアと `test_case_approval.json` を使用してください。

### 5.7 関連ファイル（現行）

```text
test_programmer/
├── test_cases/                  # 現行30ケースのJSON
├── test_case_approval.json      # ケースごとの採用状態
├── testcase_viewer.html         # ケース編集ビューア
├── serve_testcase_viewer.py     # ケースの確認・編集・採否管理
├── generate_testcases.py       # 旧TP規格テスト群の生成スクリプト
└── README.md
```

### 5.8 使用方法

1. **サーバー起動**:

    ```bash
    python3 test_programmer/serve_testcase_viewer.py
    ```

2. **ブラウザでアクセス**:

    ```text
    http://localhost:8083
    ```

3. **テストケース作成（新規）**:
   - 「新規テストパターン」ボタンをクリック
   - モーダルで投入箱を追加
   - **各箱行の蓋ドロップダウンから蓋を選択**
   - 「保存する」をクリック

4. **テストケース編集（既存）**:
   - 編集アイコンをクリック
   - 蓋が復元され、新しい蓋を選択可能
   - 「保存する」をクリック

5. **JSON確認**:
   - テストケースが保存され、各箱に `"lid_id"` が記録される

### 5.9 エラーハンドリング

#### API 通信失敗時

- `/api/lids` の通信・JSON読み込みで例外が起きた場合はconsoleにwarningを出力し、
  `lidDB = {}` で画面の処理を続行します。HTTPエラー時も蓋情報は取得できません。
- 蓋情報がない場合、「蓋なし」を正常に選択・保存できる状態にはなりません。
  画面の保存前チェックで登録済みの蓋を要求するため、ケースを保存できません。
  サーバーと蓋DBの状態を確認し、復旧後に画面を再読み込みしてください。

#### 蓋DB ファイル不存在時

- `box_research/lid_db.json` が存在しない場合、サーバーは空オブジェクト `{}` を返す
- 「蓋なし」も蓋DBの `type: "NONE"` のレコードを使用するため、
  空の蓋DBではケースを保存できません。
  サーバー側でもDBの読み込み・検証に失敗した場合は保存を拒否します。
- 正しい蓋DBを復元してから画面を再読み込みしてください。

---

**Phase 3-1 完了日**: 2026-10-05  
**実装者**: orchestrator エージェント  
**変更内容**: テストケーススキーマを箱レベルの蓋選択に統一

---

## 6. 過去の運用メモ（2026-10-06、履歴）

- 当時の採否は共有ファイル `test_case_approval.json` で管理し、26ケースを採用済みとしていました。これは現行の30ケース構成ではありません。
- 採否変更はビューアで「テストケース一括保存」した時に共有され、テストランナーと supervisor は採用済みケースだけを対象にする。
- 「不採用」は実行対象外にする状態であり、ケースJSONの削除とは別操作。ケースをビューアから削除して一括保存した場合だけJSONを削除する。過去の結果JSONは履歴として残る。
- ケースID・ファイル名はASCIIのまま維持する。既存ケースの名前変更は未実装・保留中。日本語名が必要になった場合は、内部IDと分けた表示名フィールドを追加する。
- 当時の26ケースに対するテストランナーと独立バリデータの実行では、全件PASSでした。ただしPASSは投入要求数の全数配置を意味せず、当時の結果では要求1536箱に対して980箱配置、556箱未配置（14ケース）でした。この結果は現行30ケースの評価結果ではありません。
