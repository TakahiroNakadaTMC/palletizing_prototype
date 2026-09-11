# テストケース仕様書 (test_programmer/)

**文書番号:** TP-DOC-2026-001  
**作成日:** 2026-08-19  
**担当エージェント:** `test-programmer`  
**対象読者:** `tester`, `algorithm-programmer`, `supervisor`, `orchestrator`  

---

## 1. 概要

本ディレクトリは、パレタイズアルゴリズムの評価・シミュレーションに使用するテストデータ生成スクリプトおよびテストケースJSON群を管理します。

[`box_research/box_db.json`](file:///home/tmc1475337/Workspaces/palletizing_prototype/box_research/box_db.json) で承認された13種類のTP規格箱（基準335系、1.5倍340系、2倍360系、大型460系、ハーフ131系、および浅型/標準/深型の各高さ体系）をもとに、単載・同高混載・異高モジュール混載・境界値テストを網羅した **計13件のテストケース** を作成しました。

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
