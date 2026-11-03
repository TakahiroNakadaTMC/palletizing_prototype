---
description: "箱仕様の調査、箱DBの追加・更新、箱と蓋の互換性確認時に使用します。"
---

# 箱仕様調査の指針
## パレタイズ対象となる箱の仕様調査・データベース構築

### ロール・責務
- パレタイズ対象となる箱（TP規格箱、オリコン、通い箱等）の寸法・嵌合深さ・上縁幅を調査・整理
- 空箱を前提としたデータベース（box_db.json）を構築
- 各箱型番の外寸（L × W × H：長手方向・短手方向・高さ）、嵌合深さ、上縁幅を正確に把握
- 箱DBでは `length` を長手方向L、`width` を短手方向Wとして記録する
- 現行の箱DB形式に従い、保存形式や既存値を無断で変更しない

### 主要入力ファイル
- `constraints/constraints.md` - 荷姿制約（参考）
- `box_research/box_db.json` - 現行の箱仕様とDB形式
- `box_research/lid_db.json` - 箱に登録された互換蓋IDの参照先

### 主要出力ファイル
- `box_research/box_db.json` - 箱仕様データベース（id, length, width, height, fitting_depth, rib_thickness〔上縁幅〕, module_ratio等）
- `box_research/README.md` - 調査サマリー・各箱の特徴説明

### データ形式（box_db.json）
各箱エントリ：
```json
{
  "id": "TP-331",
  "name": "TP-331",
  "type": "TP",
  "length": 335,
  "width": 335,
  "height": 102.5,
  "fitting_depth": 10,
  "rib_thickness": 16,
  "module_ratio": "1x1",
  "description": "TP-330系 1型 基準モジュール浅型 (内寸300x300/有効内寸291x291, 側面厚22.0mm)",
  "compatible_lids": [
    "TP330フタ",
    "サンボックス330フタ"
  ]
}
```

`compatible_lids` に登録する蓋IDは、すべて `box_research/lid_db.json` に存在することを確認する。

### 利用可能なツール
- ファイル読み書き（box_research/ ディレクトリ）
- Webサーチ機能（JIS規格、サンコー等製造メーカー仕様の検索）
- シェルコマンド実行

### 行動指針
1. JIS、サンコー、日本ロジスティックシステム協会等の公開情報から箱寸法・嵌合深さを調査
2. 各箱型番の正確な外寸・嵌合深さ・上縁幅を記録
3. TP規格箱の場合、モジュール比率は現行箱DBの値を確認して記録する
4. 調査結果の情報源と不確実性を `box_research/README.md` に記録
