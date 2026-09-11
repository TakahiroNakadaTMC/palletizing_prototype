# サブエージェント設定定義一覧 (.agent/)

本ディレクトリは、パレタイズアルゴリズム試作プロジェクトにおける各サブエージェントの設定ファイル（役割、入出力ファイル、担当ディレクトリ、システムプロンプト）を管理します。

次回以降の実行時やサブエージェント起動時に、これらの設定ファイルを参照・ロードすることで、一貫した動作と品質を担保します。

---

## エージェント一覧

| エージェント名 | 設定ファイル | 担当ディレクトリ | 主な役割 |
| :--- | :--- | :--- | :--- |
| **`orchestrator`** | [`orchestrator.yaml`](file:///home/tmc1475337/Workspaces/palletizing_prototype/.agent/orchestrator.yaml) | `.` (ルート) | 全体進行管理・フェーズ計画・エージェント統括 |
| **`box-research`** | [`box-research.yaml`](file:///home/tmc1475337/Workspaces/palletizing_prototype/.agent/box-research.yaml) | `box_research/` | TP規格箱・通い箱の仕様調査、`box_db.json` の作成 |
| **`algorithm-research`** | [`algorithm-research.yaml`](file:///home/tmc1475337/Workspaces/palletizing_prototype/.agent/algorithm-research.yaml) | `algorithm_research/` | 嵌合・段積み考慮パレタイズ手法の調査・方式提案 |
| **`test-programmer`** | [`test-programmer.yaml`](file:///home/tmc1475337/Workspaces/palletizing_prototype/.agent/test-programmer.yaml) | `test_programmer/` | テストデータ生成スクリプト・テストケースJSON群の作成 |
| **`algorithm-programmer`** | [`algorithm-programmer.yaml`](file:///home/tmc1475337/Workspaces/palletizing_prototype/.agent/algorithm-programmer.yaml) | `algorithm_programmer/` | パレタイズ計算エンジンの実装・修正 |
| **`visualizer`** | [`visualizer.yaml`](file:///home/tmc1475337/Workspaces/palletizing_prototype/.agent/visualizer.yaml) | `visualizer/` | 3D荷姿・積み込みアニメーション可視化ツールの開発 |
| **`tester`** | [`tester.yaml`](file:///home/tmc1475337/Workspaces/palletizing_prototype/.agent/tester.yaml) | `tester/` | テストケース実行・シミュレーション結果収集・ベンチマーク |
| **`supervisor`** | [`supervisor.yaml`](file:///home/tmc1475337/Workspaces/palletizing_prototype/.agent/supervisor.yaml) | `supervisor/` | `constraints/constraints.md` に基づく自動制約検証・改善指示 |
