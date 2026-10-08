# スーパーバイザーモジュール仕様書 (supervisor/)

**文書番号:** SUP-DOC-2026-001  
**作成日:** 2026-08-19  
**最終更新日:** 2026-09-23（下段オーバーサイズ制約チェックを追加）  
**担当エージェント:** `supervisor`  
**対象読者:** `orchestrator`, `algorithm-programmer`, `tester`  

---

## 1. 概要

本ディレクトリは、[`constraints/constraints.md`](file:///home/tmc1475337/Workspaces/palletizing_prototype/constraints/constraints.md) に定義された荷姿制約に基づき、パレタイズ結果が物理的・幾何学的にすべての制約を満たしているかを客観的・機械的にバリデーションし、検証レポートを発行するスーパーバイザー機能を管理します。

---

## 2. モジュール構成

```text
supervisor/
├── validate.py      # 独立制約バリデーションスクリプト
├── reports/         # 総合検証レポート出力先 (validation_report.md)
└── README.md        # 本ドキュメント
```

---

## 3. 検証項目（バリデーション基準）

1. **最大積載高さ制約** ($\le 1200\text{ mm}$)
2. **長辺荷姿スパン制約** ($800\text{ mm} \le X < 1360\text{ mm}$)
3. **短辺荷姿スパン制約** ($800\text{ mm} \le Y < 1100\text{ mm}$)
4. **最高層四隅高さ一致** (各コーナーの誤差 3.0mm 以内)
5. **天地固定・回転角度制約** (0° / 90° のみ、上下反転・横倒し禁止)
6. **嵌合沈み込み計算** ($Z_{upper} = Z_{lower} + H_{lower} - fitting\_depth$)
7. **空中配置禁止・底面支持率** ($\ge 85\%$)
8. **下段箱サイズ超過禁止**（直接支持する下段箱の幅・奥行きが、上段箱より両方とも1.0mmを超えて大きい段積みを禁止）
9. **3D幾何衝突・空間干渉の完全排除** (不正な食い込み 0 件)
10. **積み込み順序（Order）のトポロジカル整合性** ($order_{lower} < order_{upper}$)

---

## 4. 実行方法

```bash
python3 supervisor/validate.py
```
実行すると、ターミナルに各ケースの合否サマリーが表示され、[`supervisor/reports/validation_report.md`](file:///home/tmc1475337/Workspaces/palletizing_prototype/supervisor/reports/validation_report.md) に詳細レポートが出力されます。
