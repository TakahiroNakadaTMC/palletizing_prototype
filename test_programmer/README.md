# テストケース仕様書 (test_programmer/)

**文書番号:** TP-DOC-2026-001  
**作成日:** 2026-08-19  
**担当エージェント:** `test-programmer`  
**対象読者:** `tester`, `algorithm-programmer`, `supervisor`, `orchestrator`  

---

## 1. 概要

本ディレクトリは、パレタイズアルゴリズムの評価・シミュレーションに使用するテストデータ生成スクリプトおよびテストケースJSON群を管理します。

[`box_research/box_db.json`](file:///home/tmc1475337/Workspaces/palletizing_prototype/box_research/box_db.json) で承認された13種類のTP規格箱（基準335系、1.5倍340系、2倍360系、大型460系、ハーフ131系、および浅型/標準/深型の各高さ体系）をもとに、単載・同高混載・異高モジュール混載・境界値テストを設計しています。既存13件の蓋なしケースを維持し、同じ構成の標準蓋付き派生ケース13件を加え、生成後は計26件になります。

---

## 2. テストケース一覧

| 分類 | テストケース名 | 対象箱型番 | 箱数 | 主な検証目的 |
| :--- | :--- | :--- | :---: | :--- |
| **単載** | [`single_tp332.json`](file:///home/tmc1475337/Workspaces/palletizing_prototype/test_programmer/test_cases/single_tp332.json) | TP-332 (335x335x195) | 60 | 基準モジュール単載パターンの最大充填（ブロック/レンガ） |
| **単載** | [`single_tp342.json`](file:///home/tmc1475337/Workspaces/palletizing_prototype/test_programmer/test_cases/single_tp342.json) | TP-342 (503x335x195) | 40 | 1.5モジュール単載パターンの探索 |
| **単載** | [`single_tp362.json`](file:///home/tmc1475337/Workspaces/palletizing_prototype/test_programmer/test_cases/single_tp362.json) | TP-362 (670x335x195) | 30 | 2倍モジュール単載（長辺1340mmフィット＆短辺制約） |
| **単載** | [`single_tp462.json`](file:///home/tmc1475337/Workspaces/palletizing_prototype/test_programmer/test_cases/single_tp462.json) | TP-462 (670x503x195) | 24 | 大型モジュール単載パターンの安定配置 |
| **単載** | [`single_tp131.json`](file:///home/tmc1475337/Workspaces/palletizing_prototype/test_programmer/test_cases/single_tp131.json) | TP-131 (335x168x103) | 120 | ハーフモジュール小箱の大量充填 |
| **単載** | [`single_tp331.json`](file:///home/tmc1475337/Workspaces/palletizing_prototype/test_programmer/test_cases/single_tp331.json) | TP-331 (335x335x103) | 80 | 浅型基準箱の多段積載（最大11段） |
| **混載** | [`mixed_tp_same_height.json`](file:///home/tmc1475337/Workspaces/palletizing_prototype/test_programmer/test_cases/mixed_tp_same_height.json) | TP-332, 342, 362, 462 | 42 | 同一高さ（H=195mm）のモジュール平面組み合わせ混載 |
| **混載** | [`mixed_tp_modular_stack.json`](file:///home/tmc1475337/Workspaces/palletizing_prototype/test_programmer/test_cases/mixed_tp_modular_stack.json) | TP-331, 332, 362, 462 | 58 | TP-330系2個の上にTP-360系を載せる跨ぎ嵌合段積み |
| **混載** | [`mixed_tp_different_heights.json`](file:///home/tmc1475337/Workspaces/palletizing_prototype/test_programmer/test_cases/mixed_tp_different_heights.json) | 9種類のTP箱 (高103/149/195/288) | 74 | 4段階の異高が混在する高度な混載・嵌合Z追従 |
| **混載** | [`mixed_tp_large_volume.json`](file:///home/tmc1475337/Workspaces/palletizing_prototype/test_programmer/test_cases/mixed_tp_large_volume.json) | 全13種類のTP箱 (各10個) | 130 | 大量投入によるパレット最大積載高1200mm上限充填 |
| **境界値** | [`boundary_height_limit.json`](file:///home/tmc1475337/Workspaces/palletizing_prototype/test_programmer/test_cases/boundary_height_limit.json) | TP-333, 343, 363, 463 (高288) | 48 | 深型のみで4段積載（総高1122mm <= 1200mm）の境界値 |
| **境界値** | [`boundary_overhang_long_side.json`](file:///home/tmc1475337/Workspaces/palletizing_prototype/test_programmer/test_cases/boundary_overhang_long_side.json) | TP-362, 363 (長辺670) | 30 | 長辺荷姿1340mm（<1360mm許容枠）の境界値 |
| **境界値** | [`boundary_min_short_side.json`](file:///home/tmc1475337/Workspaces/palletizing_prototype/test_programmer/test_cases/boundary_min_short_side.json) | TP-342, 332 | 32 | 短辺荷姿が800mm以上1000mm以下の制約を満たすかの検証 |

---

## 3. テストデータの再生成方法

箱DB（`box_research/box_db.json`）を更新した際は、以下のスクリプトを実行することでテストケースJSONを一括再生成できます。

```bash
python3 test_programmer/generate_testcases.py
```

---

## 4. テストパターン承認・編集ビューア

テストケースの投入箱リスト（荷山構成）を一覧確認し、個別採用/解除・投入数量の変更・新規パターンの作成・一括保存を行えるWebビューワを提供しています。

```bash
python3 test_programmer/serve_testcase_viewer.py
```
ブラウザで `http://localhost:8083` を開いてご利用いただけます。

---

## 5. Phase 3: 蓋選択機能 (Lid Selection Feature)

### 5.1 概要

Phase 3-1 では、テストケースに **箱ごとの蓋（Lid）選択機能** を統合しました。各テストケース内の **個別の箱** に対して蓋を指定できるようになり、パレタイズシミュレーション時に箱ごとに異なる蓋を検証できます。

**重要**: 蓋選択は **テストケースレベル** ではなく **箱レベル** で行われます。同一テストケース内の複数の箱に対して、それぞれ異なる蓋を割り当てることが可能です。

### 5.2 テストケースJSONスキーマ（Phase 3-1から変更）

すべてのテストケースJSONで、`box_list` 配列内の **各箱に** `"lid_id"` フィールドが追加されました：

#### 変更前（Phase 3）
```json
{
  "name": "single_tp332",
  "description": "...",
  "pallet": {...},
  "box_list": [
    {"box_id": "TP-332", "count": 60}
  ],
  "lid_id": "LID-010"              // ← テストケースレベル（全箱共通）
}
```

#### 変更後（Phase 3-1）✅
```json
{
  "name": "single_tp332",
  "description": "...",
  "pallet": {...},
  "box_list": [
    {
      "box_id": "TP-332",
      "count": 60,
      "lid_id": "LID-010"          // ← 各箱レベル（箱ごとに異なる蓋を指定可能）
    }
  ]
}
```

#### 混載テストケースの例
```json
{
  "name": "mixed_tp_same_height",
  "box_list": [
    {"box_id": "TP-332", "count": 16, "lid_id": "LID-010"},  // TP-332は蓋なし
    {"box_id": "TP-342", "count": 12, "lid_id": "LID-003"},  // TP-342は蓋LID-003
    {"box_id": "TP-362", "count": 8, "lid_id": "LID-010"},   // TP-362は蓋なし
    {"box_id": "TP-462", "count": 6, "lid_id": "LID-002"}    // TP-462は蓋LID-002
  ]
}
```

### 5.3 UI：箱ごとの蓋選択

#### testcase_viewer.html: 修正内容

**追加: 各箱行に蓋選択ドロップダウン**

モーダル内の投入箱リストが、各箱ごとに4列で表示されます：
1. **箱型番セレクト** （例: TP-332）
2. **投入数量** （例: 60）
3. **蓋選択ドロップダウン（NEW）** （例: 蓋なし / LID-001 / LID-002 / ...）
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
      <option value="LID-010">蓋なし</option>
      <option value="LID-001">クリア蓋 TP-330系用</option>
      <option value="LID-002">クリア蓋 TP-340系用</option>
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
- `lidId` (string, default: `'LID-010'`): 蓋ID

**処理内容**:
- Box行に **3番目の列** として蓋セレクトボックスを追加
- **選択された箱の `compatible_lids` に含まれる蓋のみ** を表示
- 箱型番が変更されたら、蓋ドロップダウンも自動更新

**重要**: 各箱型番の対応蓋は `box_research/box_db.json` の `"compatible_lids"` フィールドで管理されています：

例:
```json
"TP-332": {
  "id": "TP-332",
  ...
  "compatible_lids": ["LID-001", "LID-002", "LID-010"]  // この蓋のみ表示
}
```

**UI動作**:
1. 最初に箱を選択 → その箱の対応蓋のみドロップダウンに表示
2. 箱型番を変更 → 新しい箱の対応蓋に自動更新

```javascript
function addBoxRow(selectedId = '', count = 10, lidId = 'LID-010') {
  // ...
  // 選択された箱の対応蓋リストを取得
  const selectedBox = masterBoxDB[selectedId];
  const compatibleLids = selectedBox?.compatible_lids || ['LID-010'];
  
  // compatibleLids に含まれる蓋のみをドロップダウンに追加
  const lidOptions = [];
  compatibleLids.forEach(id => {
    const lid = lidDB[id] || { name: id };
    lidOptions.push(`<option value="${id}" ...>${lid.name}</option>`);
  });
  
  // 箱型番変更イベント: 対応蓋を自動更新
  row.querySelector('.box-id-select').addEventListener('change', (e) => {
    const newBoxId = e.target.value;
    const newBox = masterBoxDB[newBoxId];
    const newCompatibleLids = newBox?.compatible_lids || ['LID-010'];
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
      addBoxRow(b.box_id, b.count, b.lid_id || 'LID-010');  // ← 蓋を復元
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
    const lid = r.querySelector('.box-lid-select').value || 'LID-010';  // ← 各行から蓋を取得
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
```
GET /api/lids HTTP/1.1
```

**レスポンス**:
```json
{
  "LID-001": {
    "id": "LID-001",
    "name": "クリア蓋 TP-330系用",
    "type": "TP",
    "width": 335,
    "length": 335,
    "thickness": 15,
    "fit_type": "外嵌め",
    "description": "TP-330系1型対応（TP-331, TP-332, TP-333用）"
  },
  "LID-010": {
    "id": "LID-010",
    "name": "蓋無",
    "type": "NONE",
    "description": "蓋を使用しない荷姿（デフォルト）"
  }
}
```

**実装** (`serve_testcase_viewer.py`):
- `box_research/lid_db.json` をサーバーから読み込んで返す
- ファイルが存在しない場合は空オブジェクト `{}` を返す

### 5.5 デフォルト動作

#### 既存テストケース（自動更新）

`test_programmer/test_cases/` の全13ファイル:
- `single_tp*.json` (6ファイル)
- `mixed_tp_*.json` (4ファイル)
- `boundary_*.json` (3ファイル)

すべて **箱リスト内の各箱に** `"lid_id": "LID-010"` （蓋無）がデフォルト値として自動設定されました。

#### 新規テストケース生成

`generate_testcases.py` を実行して新しいテストケースを生成する場合、**自動的に各箱に** `"lid_id": "LID-010"` が付与されます：

```bash
python3 test_programmer/generate_testcases.py
```

結果例（既存13件＋標準蓋付き派生13件）:
```
✓ 生成: single_tp332.json ...
✓ 生成: mixed_tp_modular_stack.json ...
...
✓ 生成: single_tp332_with_lids.json ...
✓ 生成: mixed_tp_modular_stack_with_lids.json ...
✨ 合計 26 件のテストケースJSONを生成しました
```

#### ユーザーによる蓋変更

testcase_viewer.html で編集モーダルを開き、**各箱行の蓋ドロップダウン** から別の蓋を選択することで、箱ごとに蓋を変更できます。

手順:
1. カード編集アイコンをクリック
2. 修正モーダルが開く
3. 各箱行の **蓋ドロップダウン** から選択
4. 「保存する」をクリック
5. テストケースJSON に反映

### 5.6 標準蓋付き派生ケース（Phase 3-2 Stage 2）

`generate_testcases.py` は既存ケースを書き換えず、各ケースに対応する `*_with_lids.json` を追加生成します。単載では箱種に対応する標準蓋、混載では各箱種に対応する標準蓋をそれぞれ割り当てます。結果には蓋ID・厚さ・回転後の蓋寸法・嵌め方が記録され、外嵌め蓋は荷姿の幅・奥行き制約にも含めます。

### 5.7 ファイル構成（Phase 3-1更新）

```
test_programmer/
├── testcase_viewer.html           # ← addBoxRow() に lidId パラメータ追加
├── serve_testcase_viewer.py       # ← 既存、/api/lids エンドポイント使用
├── generate_testcases.py          # ← 全13テストケースで各箱に lid_id 付与
├── test_cases/
│   ├── single_tp131.json          # ← "lid_id": "LID-010" を各箱に追加
│   ├── single_tp331.json
│   ├── single_tp332.json
│   ├── single_tp342.json
│   ├── single_tp362.json
│   ├── single_tp462.json
│   ├── mixed_tp_same_height.json
│   ├── mixed_tp_modular_stack.json
│   ├── mixed_tp_different_heights.json
│   ├── mixed_tp_large_volume.json
│   ├── boundary_height_limit.json
│   ├── boundary_min_short_side.json
│   └── boundary_overhang_long_side.json
└── README.md
```

### 5.8 使用方法

1. **サーバー起動**:
   ```bash
   python3 test_programmer/serve_testcase_viewer.py
   ```

2. **ブラウザでアクセス**:
   ```
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

### 5.8 エラーハンドリング

#### API 通信失敗時

- `/api/lids` エンドポイントにアクセス不可の場合、console にwarning を出力し、`lidDB = {}` で続行
- UI は「蓋なし」オプションのみを表示

#### 蓋DB ファイル不存在時

- `box_research/lid_db.json` が存在しない場合、サーバーは空オブジェクト `{}` を返す
- UI は「蓋なし」のみで動作

---

**Phase 3-1 完了日**: 2026-10-05  
**実装者**: orchestrator エージェント  
**変更内容**: テストケーススキーマを箱レベルの蓋選択に統一
