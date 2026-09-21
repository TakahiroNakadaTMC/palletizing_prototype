#!/usr/bin/env python3
"""
独立制約バリデータ (validate.py)
constraints/constraints.md の全制約項目に基づき、
tester/results/ 配下の全パレタイズ結果データを独立・厳格に検証します。
"""

import os
import sys
import glob
import json
from typing import List, Dict, Tuple, Any

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
BOX_DB_PATH = os.path.join(PROJECT_ROOT, "box_research", "box_db.json")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "tester", "results")
REPORT_PATH = os.path.join(BASE_DIR, "reports", "validation_report.md")

# 荷姿制約パラメータ (constraints/constraints.md より)
MAX_HEIGHT = 1200.0        # mm (最大積載高)
MAX_X_SPAN = 1360.0        # mm (長辺荷姿許容上限: <1360mm)
MIN_Y_SPAN = 800.0         # mm (短辺荷姿最小幅: >=800mm)
MAX_Y_SPAN = 1100.0        # mm (短辺荷姿許容上限: <1100mm)
MIN_SUPPORT_RATIO = 0.85   # 底面支持面積比率の下限 (85%)
EPS = 1e-3                 # 浮動小数点誤差マージン

def load_box_db() -> Dict[str, Any]:
    with open(BOX_DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def intersects_2d_rect(x1, y1, w1, l1, x2, y2, w2, l2, eps=EPS):
    return not (x1 + w1 <= x2 + eps or x2 + w2 <= x1 + eps or
                y1 + l1 <= y2 + eps or y2 + l2 <= y1 + eps)

def get_intersection_area(x1, y1, w1, l1, x2, y2, w2, l2):
    ix_min = max(x1, x2)
    ix_max = min(x1 + w1, x2 + w2)
    iy_min = max(y1, y2)
    iy_max = min(y1 + l1, y2 + l2)
    if ix_max > ix_min and iy_max > iy_min:
        return (ix_max - ix_min) * (iy_max - iy_min)
    return 0.0

class PalletizeValidator:
    def __init__(self, box_db: Dict[str, Any]):
        self.box_db = box_db

    def validate_case(self, result_path: str) -> Dict[str, Any]:
        with open(result_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        test_name = data.get("test_name", os.path.basename(result_path))
        boxes = data.get("boxes", [])
        total_boxes = len(boxes)

        violations = []
        warnings = []

        if total_boxes == 0:
            return {
                "test_name": test_name,
                "is_pass": False,
                "total_boxes": 0,
                "violations": ["配置箱数が0です"],
                "warnings": [],
                "details": {}
            }

        # -------------------------------------------------------------
        # 1. 荷姿寸法・境界制約の検証
        # -------------------------------------------------------------
        min_x = min(b["position"]["x"] for b in boxes)
        max_x = max(b["position"]["x"] + b["dimensions"]["width"] for b in boxes)
        x_span = max_x - min_x

        min_y = min(b["position"]["y"] for b in boxes)
        max_y = max(b["position"]["y"] + b["dimensions"]["length"] for b in boxes)
        y_span = max_y - min_y

        max_z = max(b["position"]["z"] + b["dimensions"]["height"] for b in boxes)

        # (1) 最大積載高
        if max_z > MAX_HEIGHT + EPS:
            violations.append(f"最大積載高超過: {max_z:.1f}mm > {MAX_HEIGHT}mm (超過: {max_z - MAX_HEIGHT:.1f}mm)")

        # (2) 長辺荷姿幅 (< 1360mm)
        if x_span >= MAX_X_SPAN:
            violations.append(f"長辺荷姿幅超過: {x_span:.1f}mm >= {MAX_X_SPAN}mm")

        # (3) 短辺荷姿幅 (800mm <= Y < 1100mm)
        if y_span < MIN_Y_SPAN - EPS:
            violations.append(f"短辺荷姿幅不足: {y_span:.1f}mm < {MIN_Y_SPAN}mm (安定性不足)")
        if y_span >= MAX_Y_SPAN:
            violations.append(f"短辺荷姿幅超過: {y_span:.1f}mm >= {MAX_Y_SPAN}mm (短辺オーバーハング許容枠超過)")

        # -------------------------------------------------------------
        # 2. 各箱の幾何・回転・天地固定・嵌合寸法の検証
        # -------------------------------------------------------------
        for b in boxes:
            bid = b["box_id"]
            order = b["order"]
            pos = b["position"]
            dims = b["dimensions"]
            rot = b["rotation"]
            fitting = b["fitting_depth"]

            if bid not in self.box_db:
                violations.append(f"Order #{order}: 未知の箱型番 '{bid}' が使用されています")
                continue

            master = self.box_db[bid]

            # 天地固定（高さチェック）
            if abs(dims["height"] - master["height"]) > EPS:
                violations.append(f"Order #{order} ({bid}): 天地固定違反（外寸高さ {master['height']}mm に対して {dims['height']}mm）")

            # 回転角チェック
            if rot not in [0, 90]:
                violations.append(f"Order #{order} ({bid}): 不正な回転角 {rot}° (0°または90°のみ許可)")

            # 水平寸法チェック
            if rot == 0:
                if abs(dims["width"] - master["width"]) > EPS or abs(dims["length"] - master["length"]) > EPS:
                    violations.append(f"Order #{order} ({bid}): 0度回転時の寸法不一致")
            elif rot == 90:
                if abs(dims["width"] - master["length"]) > EPS or abs(dims["length"] - master["width"]) > EPS:
                    violations.append(f"Order #{order} ({bid}): 90度回転時の寸法不一致")

        # -------------------------------------------------------------
        # 3. 3D干渉（衝突）＆ 嵌合深さ沈み込みの検証
        # -------------------------------------------------------------
        for i in range(total_boxes):
            b1 = boxes[i]
            for j in range(i + 1, total_boxes):
                b2 = boxes[j]

                # 2D平面での重なりチェック
                if intersects_2d_rect(b1["position"]["x"], b1["position"]["y"], b1["dimensions"]["width"], b1["dimensions"]["length"],
                                      b2["position"]["x"], b2["position"]["y"], b2["dimensions"]["width"], b2["dimensions"]["length"]):
                    
                    b1_z = b1["position"]["z"]
                    b1_top = b1_z + b1["dimensions"]["height"]
                    b2_z = b2["position"]["z"]
                    b2_top = b2_z + b2["dimensions"]["height"]

                    # b2がb1の上に載る場合: b2_z >= b1_top - b2.fitting_depth
                    if b2_z >= b1_top - b2["fitting_depth"] - EPS:
                        continue
                    # b1がb2の上に載る場合: b1_z >= b2_top - b1.fitting_depth
                    if b1_z >= b2_top - b1["fitting_depth"] - EPS:
                        continue

                    # Z区間が重なる場合は不正な食い込み衝突
                    if not (b1_top <= b2_z + EPS or b2_top <= b1_z + EPS):
                        violations.append(f"3D幾何衝突: Order #{b1['order']} ({b1['box_id']}) と Order #{b2['order']} ({b2['box_id']}) が空間干渉しています")

        # -------------------------------------------------------------
        # 4. 空中浮き防止 ＆ 底面支持面積比率の検証
        # -------------------------------------------------------------
        for b in boxes:
            order = b["order"]
            z = b["position"]["z"]
            x = b["position"]["x"]
            y = b["position"]["y"]
            w = b["dimensions"]["width"]
            l = b["dimensions"]["length"]
            fitting = b["fitting_depth"]

            if z <= EPS:
                continue  # パレット直置きはOK

            # 直下にある下段箱を探索
            supporting_boxes = []
            for other in boxes:
                if other["order"] == order:
                    continue
                other_top = other["position"]["z"] + other["dimensions"]["height"]
                # 上面Zが (z + fitting) と一致しているか
                if abs(other_top - (z + fitting)) <= 1.0:
                    if intersects_2d_rect(x, y, w, l, other["position"]["x"], other["position"]["y"], other["dimensions"]["width"], other["dimensions"]["length"]):
                        supporting_boxes.append(other)

            if not supporting_boxes:
                violations.append(f"Order #{order} ({b['box_id']}): 空中浮遊エラー（下段に支持する箱が存在しません）")
                continue

            # 支持面積比率の算出
            total_support_area = 0.0
            for sb in supporting_boxes:
                area = get_intersection_area(x, y, w, l, sb["position"]["x"], sb["position"]["y"], sb["dimensions"]["width"], sb["dimensions"]["length"])
                total_support_area += area

            box_bottom_area = w * l
            support_ratio = total_support_area / box_bottom_area
            if support_ratio < MIN_SUPPORT_RATIO - EPS:
                violations.append(f"Order #{order} ({b['box_id']}): 支持面積不足 ({support_ratio*100:.1f}% < {MIN_SUPPORT_RATIO*100:.0f}%)")

        # -------------------------------------------------------------
        # 5. 積み込み順序（Order）のトポロジカル依存性検証
        # -------------------------------------------------------------
        for b in boxes:
            order = b["order"]
            z = b["position"]["z"]
            fitting = b["fitting_depth"]

            if z <= EPS:
                continue

            for other in boxes:
                if other["order"] == order:
                    continue
                other_top = other["position"]["z"] + other["dimensions"]["height"]
                if abs(other_top - (z + fitting)) <= 1.0:
                    if intersects_2d_rect(b["position"]["x"], b["position"]["y"], b["dimensions"]["width"], b["dimensions"]["length"],
                                          other["position"]["x"], other["position"]["y"], other["dimensions"]["width"], other["dimensions"]["length"]):
                        if other["order"] >= order:
                            violations.append(f"積み順トポロジカル違反: 上段 Order #{order} ({b['box_id']}) が下段 Order #{other['order']} ({other['box_id']}) より先に配置されています")

        # -------------------------------------------------------------
        # 6. 最高層四隅高さ一致（Top 4-Corner Leveling）の検証
        # -------------------------------------------------------------
        margin = 35.0  # mm
        c1_boxes = [b for b in boxes if b["position"]["x"] <= min_x + margin and b["position"]["y"] <= min_y + margin]
        c2_boxes = [b for b in boxes if b["position"]["x"] + b["dimensions"]["width"] >= max_x - margin and b["position"]["y"] <= min_y + margin]
        c3_boxes = [b for b in boxes if b["position"]["x"] <= min_x + margin and b["position"]["y"] + b["dimensions"]["length"] >= max_y - margin]
        c4_boxes = [b for b in boxes if b["position"]["x"] + b["dimensions"]["width"] >= max_x - margin and b["position"]["y"] + b["dimensions"]["length"] >= max_y - margin]

        if not (c1_boxes and c2_boxes and c3_boxes and c4_boxes):
            violations.append("最高層四隅エラー: 荷姿の四隅（4コーナー）の一部に箱が配置されていません")
        else:
            top_c1 = max(b["position"]["z"] + b["dimensions"]["height"] for b in c1_boxes)
            top_c2 = max(b["position"]["z"] + b["dimensions"]["height"] for b in c2_boxes)
            top_c3 = max(b["position"]["z"] + b["dimensions"]["height"] for b in c3_boxes)
            top_c4 = max(b["position"]["z"] + b["dimensions"]["height"] for b in c4_boxes)

            if not (abs(top_c1 - max_z) <= 1.0 and abs(top_c2 - max_z) <= 1.0 and
                    abs(top_c3 - max_z) <= 1.0 and abs(top_c4 - max_z) <= 1.0):
                violations.append(
                    f"最高層四隅高さ不一致: 左手前={top_c1:.1f}mm, 右手前={top_c2:.1f}mm, 左奥={top_c3:.1f}mm, 右奥={top_c4:.1f}mm (最高到達高={max_z:.1f}mm)"
                )

        is_pass = (len(violations) == 0)

        pallet_vol = 1200.0 * 1000.0 * 1200.0
        box_vol = sum(b["dimensions"]["width"] * b["dimensions"]["length"] * b["dimensions"]["height"] for b in boxes)
        vol_eff = (box_vol / pallet_vol) * 100.0

        return {
            "test_name": test_name,
            "is_pass": is_pass,
            "total_boxes": total_boxes,
            "x_span": x_span,
            "y_span": y_span,
            "max_z": max_z,
            "vol_eff": vol_eff,
            "violations": violations,
            "warnings": warnings
        }

def run_supervisor_validation():
    box_db = load_box_db()
    validator = PalletizeValidator(box_db)

    result_files = sorted(glob.glob(os.path.join(RESULTS_DIR, "*.json")))
    if not result_files:
        print("❌ テスト結果ファイルが見つかりません。先に tester/run_tests.py を実行してください。")
        return

    print("="*80)
    print("🛡️ 【supervisor】荷姿制約 独立バリデーション実行開始")
    print("="*80)

    reports = []
    pass_count = 0
    fail_count = 0

    for rpath in result_files:
        res = validator.validate_case(rpath)
        reports.append(res)
        status = "✅ PASS" if res["is_pass"] else "❌ FAIL"
        if res["is_pass"]:
            pass_count += 1
        else:
            fail_count += 1

        print(f"{status} [{res['test_name']:<28}] 箱数:{res['total_boxes']:>3}箱 | 荷姿:{res['x_span']:>4.0f}x{res['y_span']:>4.0f}x{res['max_z']:>4.0f}mm | 充填率:{res['vol_eff']:>5.1f}%")
        if not res["is_pass"]:
            for v in res["violations"]:
                print(f"    - 🚨 違反: {v}")

    print("="*80)
    print(f"📊 検証結果: 全 {len(reports)} ケース中  合格: {pass_count} 件 / 不合格: {fail_count} 件 (合格率: {pass_count/len(reports)*100:.1f}%)")
    print("="*80)

    # Markdown レポートの出力
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("# 荷姿制約 総合検証レポート (validation_report.md)\n\n")
        f.write(f"**作成日:** 2026-08-19  \n")
        f.write(f"**検証エージェント:** `supervisor`  \n")
        f.write(f"**検証対象:** `tester/results/*.json` (全 {len(reports)} 件)  \n")
        f.write(f"**総合判定:** {'✅ **全ケース合格 (100% PASS)**' if fail_count == 0 else '❌ **制約違反あり (要修正)**'}  \n\n")
        f.write("---\n\n")
        f.write("## 1. 検証結果サマリー\n\n")
        f.write("| テストケース名 | 判定 | 配置箱数 | 荷姿寸法 (X × Y × Z mm) | 体積充填率 | 備考・検証詳細 |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: | :--- |\n")
        for r in reports:
            status = "✅ PASS" if r["is_pass"] else "❌ FAIL"
            dims = f"{r['x_span']:.0f} × {r['y_span']:.0f} × {r['max_z']:.0f}"
            notes = "制約項目全クリア" if r["is_pass"] else "<br>".join(r["violations"])
            f.write(f"| **`{r['test_name']}`** | {status} | {r['total_boxes']} 箱 | {dims} | {r['vol_eff']:.1f}% | {notes} |\n")
        f.write("\n---\n\n")
        f.write("## 2. 制約別チェック項目と検証基準\n\n")
        f.write(r"1. **最大積載高さ制約** ($\le 1200\text{ mm}$): 全箱の頂点Z座標がパレット上面から1200mm以下であること。" + "\n")
        f.write(r"2. **長辺荷姿スパン制約** ($< 1360\text{ mm}$): X方向の全幅が1360mm未満であること。" + "\n")
        f.write(r"3. **短辺荷姿スパン制約** ($800\text{ mm} \le Y < 1100\text{ mm}$): Y方向の全幅が800mm以上かつオーバーハング許容枠1100mm未満であること。" + "\n")
        f.write(r"4. **天地固定・回転制約**: 全箱の外寸高さがカタログ仕様と一致し、回転角が0度または90度のみであること。" + "\n")
        f.write(r"5. **嵌合沈み込み計算**: 段積み時の上段箱の底面Z座標が `下段上面Z - fitting_depth` と正確に一致していること。" + "\n")
        f.write(r"6. **空中配置禁止・底面支持率** ($\ge 85\%$): 底面積の85%以上が下段箱またはパレットによって支持されていること。" + "\n")
        f.write(r"7. **3D幾何衝突の完全排除**: 箱同士の不正な空間食い込み（嵌合深さを超える干渉）が0件であること。" + "\n")
        f.write(r"8. **積み込み順序（Order）の物理的整合性**: 支持関係にある箱について、下段箱が上段箱より必ず先に積載されていること ($order_{lower} < order_{upper}$)。" + "\n")
        f.write(r"9. **最高層四隅高さ一致制約 (Top 4-Corner Leveling)**: 荷姿の四隅（4コーナー）に位置する箱の上面高さが荷山の最高到達点 $Z_{max}$ と同一（フラット）であること。" + "\n")

    print(f"📄 総合検証レポートを出力しました: {REPORT_PATH}")

if __name__ == "__main__":
    run_supervisor_validation()
