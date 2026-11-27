'use strict';

const ResultIdentity = {
  supportedCoordinateReferences: new Set([
    'combined_footprint_min_xy_top_z',
  ]),
  key(box) { return box.part_number || box.box_id; },
  label(box) {
    return box.part_number ? `${box.part_number} / ${box.box_name}` : box.box_id;
  },
  boxLabel(box) {
    return box.part_number ? `${box.box_model_id} / ${box.lid_id}` : box.box_id;
  },
  escape(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[char]);
  },
  validate(data) {
    if (data?.schema_version !== 2) throw new Error('schema_version=2 の品番結果のみ表示できます');
    if (data?.input_mode !== 'part_number') throw new Error("input_mode='part_number' の結果のみ表示できます");
    if (!this.supportedCoordinateReferences.has(data?.coordinate_reference)) {
      throw new Error(`coordinate_reference が未対応です: ${data?.coordinate_reference ?? '(未設定)'}`);
    }
    if (!Array.isArray(data.boxes) || !Array.isArray(data.part_counts) || !Array.isArray(data.unplaced_boxes)) {
      throw new Error('品番結果の形式が不正です');
    }
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
    notice.className = 'mb-1 text-slate-400';
    notice.textContent = '品番方式・計算時点の記録です。合否バッジは計算判定です。独立検証レポートも確認してください。';
    target.appendChild(notice);

    const table = document.createElement('table');
    table.className = 'min-w-[600px] w-full border-collapse text-left';
    const head = document.createElement('thead');
    const headerRow = document.createElement('tr');
    for (const label of ['品番', '共通モデル', '蓋', '投入数', '配置数', '未配置数']) {
      const cell = document.createElement('th');
      cell.className = 'border-b border-slate-700 px-2 py-1 font-semibold text-slate-400';
      cell.scope = 'col';
      cell.textContent = label;
      headerRow.appendChild(cell);
    }
    head.appendChild(headerRow);
    table.appendChild(head);

    const body = document.createElement('tbody');
    for (const row of data.part_counts) {
      const line = document.createElement('tr');
      const values = [row.part_number, row.box_model_id, row.lid_id,
        row.input_count, row.placed_count, row.unplaced_count];
      values.forEach((value, index) => {
        const cell = document.createElement('td');
        cell.className = `border-b border-slate-800 px-2 py-1 ${index >= 3 ? 'text-right font-mono' : ''}`;
        cell.textContent = String(value);
        line.appendChild(cell);
      });
      body.appendChild(line);
    }
    table.appendChild(body);
    target.appendChild(table);
  },
  inspect(content, box) {
    if (!box.part_number) return;
    const detail = document.createElement('p');
    detail.id = 'part-inspector';
    detail.textContent = `仕入先: ${box.supplier_name} / 共通モデル: ${box.box_model_id}`;
    content.prepend(detail);
  }
};
