# 3D/2D 可視化ツール (visualizer/)

**文書番号:** VZ-DOC-2026-001  
**作成日:** 2026-08-19  
**担当エージェント:** `visualizer`  
**対象読者:** `orchestrator`, `tester`, `supervisor`, `algorithm-programmer`  

---

## 1. 概要

本ディレクトリは、パレタイズアルゴリズムが出力した荷姿結果データ（配置座標、回転、積み順、支持関係）を Web ブラウザ上で直感的に確認・検証できる **Three.js ベースの3Dインタラクティブ可視化ツール** を提供します。

---

## 2. ツール構成

```text
visualizer/
├── visualize.py          # スタンドアロン3D HTML生成スクリプト
├── index.html            # 統合3Dビューワ Webフロントエンド
├── serve_3d_viewer.py    # 統合3Dビューワ用ローカルHTTPサーバー
└── README.md             # 本ドキュメント
```

---

## 3. 主な機能と特徴

1. **リアルタイム 3D レンダリング**:
   - パレット（$1200 \times 1000 \times 144\text{ mm}$）およびガイドライン枠（最大積載高 $1200\text{ mm}$、長辺許容幅 $1360\text{ mm}$ 点線）の描画。
   - 箱型番ごとの自動カラーパレット色分け、エッジワイヤーフレーム強調。
   - 積み順番号と型番の 3D スプライトラベル表示。

2. **積み順 Step-by-Step コントロール**:
   - **タイムラインスライダー**: 1箱目から全箱配置までを自由にスライド確認。
   - **自動再生 / 一時停止**: 積み上げ工程をアニメーション再生（再生速度: 0.5x, 1x, 3x）。

3. **視点操作 & プリセットカメラ**:
   - マウスドラッグによる 360 度自由回転、パン、ズーム（OrbitControls）。
   - ワンクリック視点切替（俯瞰 ISO、上面 Top、正面 Front、側面 Side）。

4. **箱詳細インスペクタ**:
   - 3D 空間上の任意の箱をクリックすると、型番、配置座標 $(X, Y, Z)$、外寸、回転角、勘合深さ、および **下段支持箱の Order 番号（`supported_by`）** を即座に表示。

---

## 4. 起動・利用方法

### (1) 統合ビューワサーバーの起動（推奨）

```bash
python3 visualizer/serve_3d_viewer.py
```
ブラウザで `http://localhost:8082` を開くと、`tester/results/` にある全テスト結果をプルダウンで切り替えて 3D 荷姿を確認できます。

### (2) スタンドアロン HTML の個別生成

```bash
python3 visualizer/visualize.py tester/results/result_mixed_tp_same_height.json -o visualizer/viewer.html
```
生成された `visualizer/viewer.html` をブラウザで直接開いて確認できます。
