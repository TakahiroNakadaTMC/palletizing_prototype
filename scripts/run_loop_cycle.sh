#!/bin/bash
# run_loop_cycle.sh
# パレタイズアルゴリズム試作プロジェクト用ループ実行スクリプト
# テストケース生成 → アルゴリズム実行 → 制約検証 のパイプラインを一括実行

set -e  # エラーで即座に停止

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# ===== 色分け出力用 =====
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ===== ログ出力関数 =====
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓ SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗ ERROR]${NC} $1"
}

# ===== 前提条件チェック =====
check_prerequisites() {
    log_info "前提条件をチェック中..."
    
    # Python が利用可能か確認
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 が見つかりません。インストールしてください。"
        exit 1
    fi
    
    # 必須ファイルが存在するか確認
    local required_files=(
        "box_research/box_db.json"
        "algorithm_research/proposal.md"
        "constraints/constraints.md"
        "test_programmer/generate_testcases.py"
        "algorithm_programmer/palletizer.py"
        "tester/run_simulation.py"
        "supervisor/validate.py"
    )
    
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            log_warning "ファイルが見つかりません: $file"
            log_info "該当するエージェント（orchestrator）に作成を指示してください"
            return 1
        fi
    done
    
    log_success "前提条件チェック完了"
    return 0
}

# ===== フェーズ1: テストケース生成 =====
phase_generate_testcases() {
    log_info "フェーズ1: テストケース生成を開始..."
    
    if [ ! -f "test_programmer/generate_testcases.py" ]; then
        log_error "test_programmer/generate_testcases.py が見つかりません"
        return 1
    fi
    
    # テストケースを生成
    python3 test_programmer/generate_testcases.py
    
    if [ $? -eq 0 ]; then
        local test_count=$(find test_programmer/test_cases -name "*.json" 2>/dev/null | wc -l)
        log_success "テストケース生成完了 ($test_count ケース生成)"
        return 0
    else
        log_error "テストケース生成に失敗しました"
        return 1
    fi
}

# ===== フェーズ2: テスト実行 =====
phase_run_tests() {
    log_info "フェーズ2: テスト実行を開始..."
    
    if [ ! -f "tester/run_simulation.py" ]; then
        log_error "tester/run_simulation.py が見つかりません"
        return 1
    fi
    
    # テストケースが存在するか確認
    local test_count=$(find test_programmer/test_cases -name "*.json" 2>/dev/null | wc -l)
    if [ "$test_count" -eq 0 ]; then
        log_error "テストケースが見つかりません。フェーズ1を再実行してください。"
        return 1
    fi
    
    log_info "テストケース数: $test_count"
    
    # テストを実行
    python3 tester/run_simulation.py
    
    if [ $? -eq 0 ]; then
        local result_count=$(find tester/results -name "result_*.json" 2>/dev/null | wc -l)
        log_success "テスト実行完了 ($result_count 結果生成)"
        return 0
    else
        log_error "テスト実行に失敗しました"
        return 1
    fi
}

# ===== フェーズ3: 制約検証 =====
phase_validate_results() {
    log_info "フェーズ3: 制約検証を開始..."
    
    if [ ! -f "supervisor/validate.py" ]; then
        log_error "supervisor/validate.py が見つかりません"
        return 1
    fi
    
    # 結果ファイルが存在するか確認
    local result_count=$(find tester/results -name "result_*.json" 2>/dev/null | wc -l)
    if [ "$result_count" -eq 0 ]; then
        log_error "テスト結果ファイルが見つかりません。フェーズ2を再実行してください。"
        return 1
    fi
    
    log_info "検証対象ファイル数: $result_count"
    
    # 検証を実行
    python3 supervisor/validate.py
    
    if [ $? -eq 0 ]; then
        log_success "制約検証完了"
        
        # validation_summary.md が生成されたか確認
        if [ -f "supervisor/validation_summary.md" ]; then
            log_info "バリデーション結果: supervisor/validation_summary.md を参照してください"
        fi
        
        return 0
    else
        log_error "制約検証に失敗しました"
        return 1
    fi
}

# ===== フェーズ4: 可視化 =====
phase_visualize_results() {
    log_info "フェーズ4: 結果の可視化を開始..."
    
    if [ ! -f "visualizer/visualize.py" ]; then
        log_warning "visualizer/visualize.py が見つかりません。スキップします。"
        return 0
    fi
    
    # 可視化を実行
    python3 visualizer/visualize.py --all
    
    if [ $? -eq 0 ]; then
        log_success "結果の可視化完了"
        log_info "生成された HTML ファイル: visualizer/generated_viewers/ を参照してください"
        return 0
    else
        log_warning "結果の可視化に失敗しました（オプション処理のため継続）"
        return 0
    fi
}

# ===== メインフロー =====
main() {
    log_info "================================================"
    log_info "パレタイズアルゴリズム ループ実行スクリプト開始"
    log_info "================================================"
    log_info "プロジェクトルート: $PROJECT_ROOT"
    echo
    
    # 前提条件チェック
    if ! check_prerequisites; then
        log_error "前提条件を満たしていません"
        exit 1
    fi
    echo
    
    # 開始時刻を記録
    START_TIME=$(date +%s)
    
    # フェーズ1: テストケース生成
    if ! phase_generate_testcases; then
        log_error "テストケース生成フェーズで失敗しました"
        exit 1
    fi
    echo
    
    # フェーズ2: テスト実行
    if ! phase_run_tests; then
        log_error "テスト実行フェーズで失敗しました"
        exit 1
    fi
    echo
    
    # フェーズ3: 制約検証
    if ! phase_validate_results; then
        log_error "制約検証フェーズで失敗しました"
        exit 1
    fi
    echo
    
    # フェーズ4: 可視化
    phase_visualize_results
    echo
    
    # 完了時刻を計算
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    
    # ===== 最終レポート =====
    log_success "================================================"
    log_success "ループ実行スクリプト完了"
    log_success "================================================"
    log_info "実行時間: ${DURATION} 秒"
    log_info "次のステップ:"
    log_info "  1. supervisor/validation_summary.md で検証結果を確認"
    log_info "  2. 不合格（NG）項目がある場合は algorithm-programmer に改善を指示"
    log_info "  3. すべて合格（PASS）になるまでループを繰り返す"
    echo
}

# スクリプト実行
main "$@"
