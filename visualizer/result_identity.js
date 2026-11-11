'use strict';

const ResultIdentity = {
  key(box) { return box.part_number || box.box_id; },
  label(box) {
    return box.part_number ? `${box.part_number} / ${box.box_name}` : box.box_id;
  },
  escape(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[char]);
  },
  validate(data) {
    if (data.input_mode !== 'part_number' && data.schema_version !== 2) return;
    if (data.schema_version !== 2 || data.input_mode !== 'part_number' ||
        !Array.isArray(data.boxes) || !Array.isArray(data.part_counts) ||
        !Array.isArray(data.unplaced_boxes)) throw new Error('品番結果の形式が不正です');
    const parts = new Map();
    for (const row of data.part_counts) {
      if (!row.part_number || parts.has(row.part_number) ||
          ['part_number', 'supplier_name', 'box_name', 'box_model_id', 'lid_id'].some(k => typeof row[k] !== 'string') ||
          ['input_count', 'placed_count', 'unplaced_count'].some(k => !Number.isInteger(row[k]) || row[k] < 0) ||
          row.input_count !== row.placed_count + row.unplaced_count) throw new Error('品番別数量が不正です');
      parts.set(row.part_number, {row, placed: 0, unplaced: 0});
    }
    for (const [rows, countKey, totalKey] of [
      [data.boxes, null, 'placed'], [data.unplaced_boxes, 'count', 'unplaced']
    ]) {
      for (const box of rows) {
        const part = parts.get(box.part_number);
        if (!part || ['supplier_name', 'box_name', 'box_model_id', 'lid_id'].some(k => box[k] !== part.row[k]) ||
            box.box_id !== box.box_name) throw new Error('配置・未配置箱の品番情報が一致しません');
        const count = countKey ? box[countKey] : 1;
        if (!Number.isInteger(count) || count < 1) throw new Error('品番数量が不正です');
        part[totalKey] += count;
      }
    }
    let input = 0, placed = 0, unplaced = 0;
    for (const part of parts.values()) {
      if (part.placed !== part.row.placed_count || part.unplaced !== part.row.unplaced_count)
        throw new Error('品番集計と箱一覧の数量が一致しません');
      input += part.row.input_count; placed += part.placed; unplaced += part.unplaced;
    }
    if (input !== data.input_boxes_count || placed !== data.placed_boxes_count ||
        unplaced !== data.unplaced_boxes_count) throw new Error('品番数量と全体数量が一致しません');
  },
  renderSummary(data) {
    this.validate(data);
    const target = document.getElementById('part-summary');
    target.replaceChildren();
    const notice = document.createElement('p');
    notice.textContent = data.input_mode === 'part_number'
      ? '品番方式・計算時点の記録です。合否バッジは計算判定です。独立検証レポートも確認してください。'
      : '旧方式の結果（品番情報なし）';
    target.appendChild(notice);
    if (data.input_mode !== 'part_number') return;
    for (const row of data.part_counts) {
      const entry = document.createElement('p');
      entry.textContent = `${this.label(row)} / 仕入先: ${row.supplier_name} / 共通モデル: ${row.box_model_id} / 蓋: ${row.lid_id} / 投入${row.input_count}・配置${row.placed_count}・未配置${row.unplaced_count}`;
      target.appendChild(entry);
    }
  },
  inspect(content, box) {
    if (!box.part_number) return;
    const detail = document.createElement('p');
    detail.id = 'part-inspector';
    detail.textContent = `品番: ${box.part_number} / 仕入先: ${box.supplier_name} / 箱名称: ${box.box_name} / 共通モデル: ${box.box_model_id} / 固定蓋: ${box.lid_id}`;
    content.prepend(detail);
  }
};
