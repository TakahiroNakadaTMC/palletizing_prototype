# スーパーバイザーモジュール仕様書 (supervisor/)

**文書番号:** SUP-DOC-2026-001
**作成日:** 2026-08-19
**最終更新日:** 2026-11-XX
（パレット仕様を6項目独立モデル `length`/`width`/`height`/`max_x_span`/`max_y_span`/`max_height` へ刷新。
固定1200mm上限・800mm下限・軸別オーバーハング上限・670mm例外・旧設定キーは全廃止。
オーバーハングは参考警告情報へ変更。パレット底面（body底面）支持率85%判定を是正。）
**担当エージェント:** `supervisor`
**対象読者:** `orchestrator`, `algorithm-programmer`, `tester`

---

## 1. 概要

本ディレクトリは、[荷姿制約](../constraints/constraints.md) に基づき、
パレタイズ結果が物理的・幾何学的にすべての制約を満たしているかを客観的・機械的にバリデーションし、
検証レポートを発行するスーパーバイザー機能を管理します。

`supervisor/validate.py` は `algorithm_programmer` のコアモデル・エンジン（`models.py` / `palletizer.py`）を
**一切 import せず**、独立した検証ロジックとして実装されています。これはコア実装のバグや仕様変更から
独立して荷姿制約を監査できるようにするためです（親エージェントの実装とは別に、同じ入力JSONを
別ロジックで再検証します）。2026-11-05追加の上載せ支持幾何だけは、
エンジン非依存の [共通制約ヘルパー](../constraints/top_support.py) を使用します。
結果の座標・箱DBから入力を再構築し、保存されたサマリー・支持関係・合否は信用しません。
この項目は別実装ではなく共通幾何規則の再計算です。

---

## 2. モジュール構成

```text
supervisor/
├── validate.py       # 独立制約バリデーションスクリプト
├── validate_test.py  # 独立バリデーションのユニット・統合テスト
├── reports/          # 総合検証レポート出力先 (validation_report.md)
└── README.md         # 本ドキュメント
```

---

## 3. パレット仕様（6項目独立モデル）

結果JSONの `pallet` フィールドは以下6キーのみを対象とします。各値は **有限 (finite) な正の実数** である必要があり、
`bool` 値・非数値・`NaN`/`Inf`・0以下の値はすべて明示的な違反として報告された上で既定値にフォールバックします
（サイレントな黙示フォールバックは行いません。キー自体が未指定の場合のみ既定値を無言で使用します）。

| キー | 既定値 | 意味 |
|:---|---:|:---|
| `length` | 1200.0 mm | パレット本体の長辺（物理寸法。必要に応じ `width` と入替して正規化） |
| `width` | 1000.0 mm | パレット本体の短辺（物理寸法） |
| `height` | 130.0 mm | パレット本体の物理高さ（`total_height` 算出に使用） |
| `max_x_span` | 1360.0 mm | 荷姿（箱・蓋結合外形）の長辺方向許容スパン上限 |
| `max_y_span` | 1100.0 mm | 荷姿の短辺方向許容スパン上限 |
| `max_height` | 1200.0 mm | 積載貨物（カーゴ）の許容最大高さ（パレット上面からの荷物高さ） |

- **下限（800mm等）は存在しません。** 荷姿スパンは `0 < span <= max_x_span / max_y_span` であれば合格です（inclusive、上限ちょうども合格）。
- **固定1200mm上限はありません。** `max_height` はケースごとに設定された値がそのまま権威ある上限として扱われます。
- `max_y_span` が `max_x_span` を超える設定（短辺 > 長辺）は設定エラーとして報告されます。
- 旧仕様の廃止キー（`min_x_span`, `min_y_span`, `max_overhang_x_mm`, `max_overhang_y_mm`, `max_small_edge_overhang_mm` 等）は
  レガシーな結果データに残っていても **無視** され、違反にはなりません（読み取り自体を行いません）。
- `length`/`width` は物理寸法としての正規化（長辺・短辺の入替）のみ行い、既存の挙動を踏襲します。

---

## 4. 検証項目（バリデーション基準）

結果JSONの `coordinate_reference` が `combined_footprint_min_xy_top_z` の場合、検証前にXYを箱本体基準へ復元し、上面Zから底面Zを求めます。フィールドのない既存結果は従来の底面基準として扱います。

1. **積載貨物高さ制約** ($\le$ `pallet.max_height`、inclusive）
2. **長辺荷姿スパン制約** ($0 <$ X $\le$ `pallet.max_x_span`、inclusive、下限なし）
3. **短辺荷姿スパン制約** ($0 <$ Y $\le$ `pallet.max_y_span`、inclusive、下限なし）
4. **上載せ平パレット支持安定性**（同高3 mm以内、原則外周4点、TP331/TP-331は中央含む5点。
   四隅が欠ける場合だけ、接触支持領域の外周の前/奥と左/右の4辺すべてに各670 mm以上の連続支持を要求。
   四隅支持でも1箱が複数隅を覆う場合は、接触支持領域全体の外接短辺670 mm以上が必要。
   凸包面積は設定 `max_x_span × max_y_span` の65%以上、面積重心ずれはパレット中心から各設定幅の1/4未満。
   内部空間を含む凸包で評価し、実荷山外形や実接触面積を分母にしない。パレット中心が支持面凸包の内部に必要）
5. **天地固定・回転角度制約** (0° / 90° のみ、上下反転・横倒し禁止)
6. **嵌合沈み込み計算** ($Z_{upper} = Z_{lower} + H_{lower} - fitting\_depth$)
7. **空中配置禁止・底面支持率** ($\ge 85\%$、許容誤差 `1e-6`。パレット直置き（z<=EPS）の箱は、箱本体（蓋を除くbody）底面とパレット本体の矩形 `(0,0)-(pallet.length, pallet.width)` との実交差面積を支持面積として計上します。パレット外へ完全にはみ出た箱は支持面積0として扱われ、85%未満であれば空中浮遊エラーとなります)
8. **下段箱サイズ超過禁止**（直接支持する下段箱の幅・奥行きが、上段箱より両方とも1.0mmを超えて大きい段積みを禁止）
9. **3D幾何衝突・空間干渉の完全排除** (不正な食い込み 0 件)
10. **積み込み順序（Order）のトポロジカル整合性** ($order_{lower} < order_{upper}$)
11. **オーバーハング（参考警告・非違反）**（全段の箱・蓋結合外形の外接矩形とパレット本体矩形との差分を
    left/right/front/back の4方向で算出し、`report["overhang_mm"]` に構造化データとして出力します。
    いずれかの方向が0mmを超える場合は参考警告（`report["warnings"]`）として記録されますが、
    **合否判定には一切影響しません**。旧来の軸別上限値・670mm例外・廃止設定キーによる違反判定はすべて廃止されました。）
12. **荷姿センタリング**（箱・蓋外形の外接矩形中心とパレット中心が各方向0.01 mm以内で一致）

### 4.1 出力される高さ・体積情報

- `report["top_support"]`: 支持高さ・接触支持箱・露出接触領域・四隅/中央充足・必要点数・
  支持多角形・連続X/Y辺長・`opposing_edge_lengths_mm`（front/back/left/right）・
  `opposing_support_axis`（XY/空文字）・670 mm例外適用・違反。箱DBの `top_support_points` で4/5を指定できる。
  同寸法・同XY位置の上載せと均等荷重を仮定する。実耐荷重・たわみの保証ではない。
  面積・偏りは `support_polygon_area_mm2`、`support_area_ratio`、`support_centroid`、
  `centroid_offset_mm`、`reference_max_x_span_mm` / `reference_max_y_span_mm` に記録する。
  複数隅を支持する実際の箱は `multi_corner_boxes`、接触支持外接短辺は `contact_short_side_mm`。
  面積65%ちょうどは合格、重心ずれ1/4ちょうどは不合格。保存されたsummaryではなく出力座標と設定から再計算する。

- `report["physical_pallet_height"]`: 解決済み `pallet.height`（パレット本体の物理高さ）
- `report["total_height"]`: `pallet.height + 積載貨物の最高到達Z`（物理高さ込みの全体高さ）
- 体積効率等の算出には `pallet.length * pallet.width * pallet.max_height` を使用します（固定1200×1000×1200は廃止）。

### 4.2 入力不備時の挙動

- `boxes` が空リスト、または結果ファイルが存在しない・不正なJSONであっても、パレット寸法検証自体は必ず実行され、
  `report["violations"]` にパレット設定エラーが記録されます（`KeyError` 等で異常終了しません）。
- このようなケースでも `report` は高さ・体積等の数値フィールドをすべて 0 埋めで保持し、レポートランナー側で
  `KeyError` を起こさず安全に処理できます。

---

## 5. 実行方法

```bash
python3 supervisor/validate.py
```

実行すると、ターミナルに各ケースの合否サマリー（違反だけでなく参考警告も表示）が表示され、
[検証レポート](reports/validation_report.md) に詳細レポートが出力されます。

```bash
python3 -m unittest supervisor.validate_test -v
```

独立したユニット・統合テストスイートを実行します（32テスト。`test_programmer` が提供する
`outer_cover_test.json` フィクスチャが存在しない環境では `MixedLayerSearchTests` が1件スキップされます）。