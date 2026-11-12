'use strict';

(() => {
  const $ = id => document.getElementById(id);
  const clone = value => JSON.parse(JSON.stringify(value));
  const caseMode = location.pathname === '/catalog_cases.html';
  const state = { data: null, dirty: new Set(), skidRenames: {}, originalSkids: new Set(), tab: caseMode ? 'cases' : 'parts', busy: false, formDirty: false, editing: null };
  const titles = { parts: '品番・箱種DB', models: '箱モデルDB', lids: '蓋DB', pallets: 'パレットDB', skids: 'スキッドDB', suppliers: '仕入先対応表', cases: '品番方式のケース' };
  const hints = {
    parts: '品番ごとに仕入先・箱名称・共通箱モデル・固定蓋を管理します。品番は文字列です。',
    models: '共通モデル名が表示名とIDを兼ねます。名前変更は「名前変更」から、関連品番・ケースを確認して行います。',
    lids: '蓋の仕様と嵌め方を管理します。使用中の蓋は削除できません。蓋IDの変更はこの段階では行いません。',
    pallets: 'パレット型番・本体寸法・利用可能な仕入先を管理します。使用中のパレットは削除できません。標準パレットは固定です。',
    skids: 'スキッド・仕入先・使用可能なパレット・荷山上限・候補品番を管理します。変更は影響確認後に保存されます。',
    suppliers: '4桁の仕入先と仕入先名の対応を管理します。番号の変更は削除して新規登録してください。名前の修正は影響を確認して保存します。',
    cases: '仕入先→スキッド→候補品番の順で選びます。採用状態はテスト実行対象を示します。'
  };
  function node(tag, text, props = {}) {
    const element = document.createElement(tag);
    if (text !== null && text !== undefined) element.textContent = text;
    Object.assign(element, props);
    return element;
  }
  function feedback(message, error = false) {
    $('feedback').textContent = message;
    $('feedback').className = error ? 'error' : 'success';
  }
  function controls() {
    document.querySelectorAll('button, input, select, textarea').forEach(element => {
      element.disabled = state.busy || !state.data;
    });
    $('reload').disabled = state.busy;
    $('save').disabled = state.busy || !state.data || !state.dirty.size;
    $('add').disabled = state.busy || !state.data;
    $('dirty').textContent = !state.data ? '未読込（再読み込みを押してください）'
      : state.dirty.size ? `未保存: ${[...state.dirty].map(key => titles[key]).join('、')}` : '保存済み';
    const id = $('field-id');
    if (id && state.editing?.id && state.tab !== 'skids') id.disabled = true;
  }
  function mark(key) { state.dirty.add(key); controls(); }
  async function api(path, payload) {
    const response = await fetch('/api/catalog' + path, {
      cache: 'no-store', ...(payload === undefined ? {} : {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
      })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || `通信エラー ${response.status}`);
    return result;
  }
  async function busy(action) {
    state.busy = true; controls();
    try { await action(); }
    catch (error) { feedback(error.message, true); }
    finally { state.busy = false; controls(); }
  }
  async function load() {
    const data = await api('');
    state.data = data; state.dirty.clear(); state.skidRenames = {};
    state.originalSkids = new Set(Object.keys(data.skids));
    render();
  }
  function normalized(value) {
    if (/\p{C}/u.test(value)) throw new Error('制御文字・不可視文字を入力できません');
    return value.replace(/[\uFF66-\uFF9F]+/g, text => text.normalize('NFKC'))
      .replace(/[Ａ-Ｚａ-ｚ０-９]/g, text => String.fromCharCode(text.charCodeAt(0) - 0xFEE0))
      .replace(/＃/g, '#').replace(/－/g, '-').replace(/　/g, ' ').normalize('NFC').replace(/^ +| +$/g, '');
  }
  const records = () => state.tab === 'cases' ? state.data.cases.test_cases : state.data[state.tab];
  const dimension = record => `${record.length} × ${record.width} × ${record.height ?? record.thickness}`;
  const skidLimits = skid => skid?.pallet
    ? `${skid.pallet.max_x_span ?? '未設定'} × ${skid.pallet.max_y_span ?? '未設定'} × ${skid.pallet.max_height ?? '未設定'}`
    : '未設定';
  const skidComplete = skid => Boolean(skid?.pallet_id && skid.pallet
    && ['max_x_span', 'max_y_span', 'max_height'].every(key => Number.isFinite(skid.pallet[key]) && skid.pallet[key] > 0)
    && skid.part_numbers?.length);
  const skidPallet = skid => skid?.pallet_id ? state.data.pallets[skid.pallet_id] : null;
  function caseLabel(caseData) {
    return caseData.box_list.map(row => {
      const part = state.data.parts[row.part_number];
      return `${row.part_number} / ${part?.box_name ?? '品番なし'} × ${row.count}`;
    }).join('、');
  }
  function columns(id, record) {
    switch (state.tab) {
      case 'parts': return [id, record.supplier_name, record.box_name, record.box_model_id, record.lid_id];
      case 'models': return [id, record.type, dimension(record), record.fitting_depth, record.rib_thickness, record.top_support_points, record.compatible_lids.join('、')];
      case 'lids': return [id, record.type, `${record.length} × ${record.width}`, record.thickness, record.fit_type, record.description || ''];
      case 'pallets': return [id, record.model, dimension(record), record.suppliers.join('、') || '全仕入先共通'];
      case 'skids': return [id, record.supplier_name, skidPallet(record)?.model || record.pallet_id || '未設定', skidLimits(record), (record.part_numbers || []).join('、'), record.updated_at || '未保存', `${(record.history || []).length}件`];
      case 'suppliers': return [id, record.supplier_name];
      default: {
        const skid = state.data.skids[record.skid_id];
        const status = skid ? `${skidLimits(skid)} / スキッド更新: ${skid.updated_at || '未保存'}${skidComplete(skid) ? '' : ' / 計算ブロック（未設定）'}` : 'スキッド情報なし / 計算ブロック';
        return [id, record.description, record.supplier_name, record.skid_id || '未設定', caseLabel(record), status];
      }
    }
  }
  const headers = {
    parts: ['品番', '仕入先', '箱名称', '共通箱モデル', '固定蓋'],
    models: ['共通モデル名', '規格', 'L × W × H (mm)', '嵌合深さ', 'リブ厚', '支持点数', '互換蓋'],
    lids: ['蓋ID', '規格', 'L × W (mm)', '高さ増加 (mm)', '嵌め方', '説明'],
    pallets: ['パレット型番', 'モデル', '本体 L × W × H (mm)', '利用可能な仕入先'],
    skids: ['スキッドID', '仕入先名', 'パレット', '荷山最大L × W × H (mm)', '候補品番', '更新日時', '履歴'],
    suppliers: ['仕入先', '仕入先名'],
    cases: ['ケースID', '説明', '仕入先', 'スキッド', '品番／箱名称・数量', '荷山上限・更新通知']
  };
  function render() {
    $('db-tabs').hidden = caseMode;
    $('section-title').textContent = titles[state.tab];
    $('help').textContent = hints[state.tab];
    $('approve-all').hidden = $('approve-none').hidden = !caseMode;
    document.querySelectorAll('[data-tab]').forEach(button => button.setAttribute('aria-selected', String(button.dataset.tab === state.tab)));
    $('records').setAttribute('aria-label', titles[state.tab]);
    $('table-head').replaceChildren();
    const head = node('tr');
    for (const label of [...headers[state.tab], ...(caseMode ? ['採用'] : []), '操作']) head.append(node('th', label));
    $('table-head').append(head);
    $('table-body').replaceChildren();
    const query = $('search').value.toLowerCase();
    let visible = 0;
    for (const [id, record] of Object.entries(records())) {
      const values = columns(id, record);
      if (!values.join(' ').toLowerCase().includes(query)) continue;
      visible++;
      const tr = node('tr');
      tr.dataset.recordId = id;
      for (const value of values) tr.append(node('td', String(value)));
      if (caseMode) {
        const td = node('td');
        const approved = node('input', null, { type: 'checkbox', checked: state.data.cases.approval_state[id] });
        approved.setAttribute('aria-label', `${id}の採用`);
        approved.addEventListener('change', () => { state.data.cases.approval_state[id] = approved.checked; mark('cases'); });
        td.append(approved); tr.append(td);
      }
      const td = node('td');
      if (state.tab !== 'pallets' || !record.standard) {
        const edit = node('button', '編集', { type: 'button' });
        edit.addEventListener('click', () => openEditor(id)); td.append(edit);
        if (state.tab === 'models') {
          const rename = node('button', '名前変更', { type: 'button' });
          rename.addEventListener('click', () => renameModel(id)); td.append(rename);
        }
        const remove = node('button', '削除', { type: 'button' });
        remove.addEventListener('click', () => removeRecord(id)); td.append(remove);
      } else {
        td.append(node('span', '固定'));
      }
      tr.append(td);
      $('table-body').append(tr);
    }
    $('counts').textContent = `${visible}件表示 / 全${Object.keys(records()).length}件`;
    controls();
  }
  function removeRecord(id) {
    const references = [];
    if (state.tab === 'skids' && Object.values(state.skidRenames).includes(id)) {
      feedback('IDを変更したスキッドは先に変更を保存してから削除してください。', true); return;
    }
    if (state.tab === 'parts') for (const [name, data] of Object.entries(state.data.cases.test_cases)) {
      if (data.box_list.some(row => row.part_number === id)) references.push(name);
    }
    if (state.tab === 'parts') for (const [skidId, skid] of Object.entries(state.data.skids)) {
      if ((skid.part_numbers || []).includes(id)) references.push(`スキッド:${skidId}`);
    }
    if (state.tab === 'skids') for (const [name, data] of Object.entries(state.data.cases.test_cases)) {
      if (data.skid_id === id) references.push(name);
    }
    if (state.tab === 'pallets') for (const skid of Object.values(state.data.skids)) {
      if (skid.pallet_id === id) references.push(`スキッド:${skid.id}`);
    }
    if (state.tab === 'models' || state.tab === 'lids') {
      for (const part of Object.values(state.data.parts)) {
        if ((state.tab === 'models' ? part.box_model_id : part.lid_id) === id) references.push(part.id);
      }
      if (state.tab === 'lids') for (const model of Object.values(state.data.models)) {
        if (model.compatible_lids.includes(id)) references.push(model.id);
      }
    }
    if (references.length) {
      const owner = state.tab === 'skids' ? '使用中のスキッドは削除できません' : '使用中のため削除できません';
      feedback(`${owner}: ${references.join('、')}`, true); return;
    }
    if (!confirm(`${id} を削除予定にしますか？ 保存するまではファイルは変わりません。`)) return;
    delete records()[id];
    if (caseMode) delete state.data.cases.approval_state[id];
    mark(state.tab); render();
  }
  async function renameModel(id) {
    if (state.dirty.size) { feedback('名前変更の前に、未保存の編集を保存するか再読み込みしてください。', true); return; }
    const name = prompt('新しい共通モデル名を入力してください。関連品番もまとめて変更します。', id);
    if (name === null) return;
    await busy(async () => {
      const plan = await api('/rename-preview', { old_name: id, new_name: name });
      if (plan.revision !== state.data.revision) throw new Error('別の画面で更新されています。再読み込みして再確認してください。');
      const message = `${plan.old_name} → ${plan.new_name}\n関連品番: ${plan.affected_parts.join('、') || 'なし'}\n互換・使用蓋: ${plan.affected_lids.join('、') || 'なし'}\n関連ケース: ${plan.affected_cases.join('、') || 'なし'}\n\n対応付けもまとめて保存します。変更しますか？`;
      if (!confirm(message)) return;
      await api('/rename', { ...plan, confirmation: plan.confirmation });
      await load(); feedback('モデル名と関連品番を保存しました。');
    });
  }
  function field(key, label, type, value, options = []) {
    const wrapper = node('label', label);
    const input = node(type === 'select' ? 'select' : type === 'textarea' ? 'textarea' : 'input');
    input.id = `field-${key}`; input.name = key;
    if (type !== 'select' && type !== 'textarea') input.type = type;
    if (type === 'select') for (const [id, text] of options) input.append(node('option', text, { value: id }));
    input.value = value ?? '';
    if (type === 'number') { input.step = 'any'; input.min = '0'; input.required = true; }
    wrapper.append(input); $('fields').append(wrapper);
    return input;
  }
  function selectOptions(collection) {
    return Object.keys(collection).map(id => [id, id]);
  }
  function openEditor(id = null) {
    state.editing = { id, record: id ? clone(records()[id]) : {} };
    const record = state.editing.record;
    $('fields').replaceChildren(); $('form-error').textContent = '';
    $('editor-title').textContent = `${titles[state.tab]} ${id ? '編集' : '追加'}`;
    const idInput = field('id', caseMode ? 'ケースID（英数字・下線・ハイフン）' : state.tab === 'models' ? '共通モデル名' : state.tab === 'parts' ? '品番（文字列）' : state.tab === 'pallets' ? 'パレット型番' : state.tab === 'skids' ? 'スキッドID（自動生成）' : state.tab === 'suppliers' ? '仕入先' : '蓋ID', 'text', id);
    idInput.required = state.tab !== 'skids'; idInput.readOnly = state.tab === 'skids';
    idInput.disabled = state.tab !== 'skids' && (Boolean(id) || Boolean(record.standard));
    if (state.tab === 'parts') {
      field('supplier_name', '仕入先名', 'text', record.supplier_name).required = true;
      field('box_name', '箱名称（現場での呼び名）', 'text', record.box_name).required = true;
      field('box_model_id', '共通箱モデル', 'select', record.box_model_id, selectOptions(state.data.models))
        .addEventListener('change', updatePartLids);
      field('lid_id', '固定蓋', 'select', record.lid_id, []);
      if (!id) $('field-box_model_id').selectedIndex = 0;
      updatePartLids(record.lid_id);
    } else if (state.tab === 'models') {
      field('type', '規格', 'select', record.type || 'TP', [['TP', 'TP'], ['NON_TP', '非TP']]);
      for (const [key, label] of [['length', '長さ L'], ['width', '幅 W'], ['height', '高さ H'], ['fitting_depth', '嵌合深さ'], ['rib_thickness', 'リブ厚']]) {
        field(key, label + ' (mm)', 'number', record[key]);
      }
      field('top_support_points', '上載せパレット支持点数', 'select', record.top_support_points || 4, [['4', '4点'], ['5', '5点']]);
      field('module_ratio', 'モジュール比（未設定なら空白）', 'text', record.module_ratio);
      const compatible = node('fieldset'); compatible.append(node('legend', '互換蓋（装着できる蓋）'));
      const list = node('div', null, { className: 'check-list' });
      for (const lid of Object.values(state.data.lids).filter(lid => lid.type !== 'NONE')) {
        const label = node('label'); label.append(node('input', null, {
          type: 'checkbox', name: 'compatible_lids', value: lid.id, checked: (record.compatible_lids || []).includes(lid.id)
        }), document.createTextNode(lid.id)); list.append(label);
      }
      compatible.append(list); $('fields').append(compatible);
      field('description', '説明', 'textarea', record.description);
    } else if (state.tab === 'lids') {
      field('type', '規格', 'select', record.type || 'TP', [['TP', 'TP'], ['OTHER', '非TP'], ['NONE', '無蓋']]);
      for (const [key, label] of [['length', '長さ L'], ['width', '幅 W'], ['thickness', '装着時の高さ増加']]) field(key, label + ' (mm)', 'number', record[key]);
      field('fit_type', '嵌め方', 'select', record.fit_type || '内嵌め', ['内嵌め', '外嵌め', 'なし'].map(text => [text, text]));
      field('name', '名称・用途', 'text', record.name);
      field('color', '色', 'text', record.color);
      field('description', '説明', 'textarea', record.description);
    } else if (state.tab === 'pallets') {
      field('model', 'モデル名', 'text', record.model).required = true;
      for (const [key, label] of [['length', '長さ L'], ['width', '幅 W'], ['height', '高さ H']]) {
        field(key, label + ' (mm)', 'number', record[key]);
      }
      field('suppliers', '利用可能な仕入先（1行に1件）', 'textarea', (record.suppliers || []).join('\n')).required = true;
    } else if (state.tab === 'skids') {
      setupSkid(record);
    } else if (state.tab === 'suppliers') {
      field('supplier_name', '仕入先名', 'text', record.supplier_name).required = true;
    } else {
      setupCase(record);
    }
    $('case-lines').hidden = !caseMode;
    $('skid-history').hidden = state.tab !== 'skids';
    state.formDirty = false;
    $('editor').showModal(); controls(); idInput.focus();
  }
  function updatePartLids(preferred) {
    const model = state.data.models[$('field-box_model_id').value];
    const input = $('field-lid_id');
    const previous = typeof preferred === 'string' ? preferred : input.value;
    input.replaceChildren();
    for (const lid of Object.values(state.data.lids)) {
      if (lid.type === 'NONE' || model?.compatible_lids.includes(lid.id)) input.append(node('option', lid.id, { value: lid.id }));
    }
    if ([...input.options].some(option => option.value === previous)) input.value = previous;
  }
  function availablePallets(supplier) {
    return Object.values(state.data.pallets).filter(pallet => pallet.standard || pallet.suppliers.includes(supplier));
  }
  function suppliers() {
    return [...new Set(Object.values(state.data.parts).map(part => part.supplier_name))].sort();
  }
  function setupSkid(record) {
    const id = record.id || '';
    const components = [
      ['supplier_number', '仕入先', id.slice(0, 4)],
      ['work_area', '工区', id.slice(4, 5)],
      ['shipping_area', '出荷場（任意）', id.length === 9 ? id.slice(5, 8) : ''],
      ['course', 'コース', id.length === 9 ? id.slice(8, 9) : id.slice(5, 6)]
    ];
    for (const [key, label, value] of components) field(key, label, 'text', value);
    field('supplier_name', '仕入先名', 'text', record.supplier_name).readOnly = true;
    field('pallet_id', 'パレット（任意）', 'select', record.pallet_id, []);
    for (const [key, label] of [['max_x_span', '荷山最大L'], ['max_y_span', '荷山最大W'], ['max_height', '荷山最大H']]) {
      const input = field(key, `${label} (mm)（未設定可）`, 'number', record.pallet?.[key]);
      input.required = false; input.min = '0';
    }
    const candidates = node('fieldset'); candidates.append(node('legend', '候補品番（仕入先内）'));
    candidates.append(node('div', null, { id: 'skid-parts', className: 'check-list' }));
    $('fields').append(candidates);
    const updateId = () => {
      const oldSupplier = $('field-supplier_name').value;
      try {
        const values = components.map(([key]) => normalized($(`field-${key}`).value).toUpperCase());
        $('field-id').value = values.join('');
        $('field-supplier_name').value = state.data.suppliers[values[0]]?.supplier_name || '';
      } catch (_) {
        $('field-id').value = '';
        $('field-supplier_name').value = '';
      }
      if (oldSupplier !== $('field-supplier_name').value) {
        updatePallets('');
        renderSkidParts([]);
      }
    };
    for (const [key] of components) $(`field-${key}`).addEventListener('input', updateId);
    updateId();
    updatePallets(record.pallet_id);
    renderSkidParts(record.part_numbers || []);
    $('skid-updated-at').textContent = `更新日時: ${record.updated_at || '新規（保存時にサーバーが設定）'}`;
    const history = $('skid-history-list'); history.replaceChildren();
    for (const entry of record.history || []) {
      const item = node('li');
      const before = entry.before ? JSON.stringify(entry.before) : '新規';
      const affected = (entry.affected_cases || []).join('、') || 'なし';
      const rename = entry.previous_id && entry.skid_id ? ` / ${entry.previous_id} → ${entry.skid_id}` : '';
      item.textContent = `${entry.updated_at || ''}${rename} / ${before} → ${JSON.stringify(entry.after)} / 影響ケース: ${affected}`;
      history.append(item);
    }
  }
  function renderSkidParts(selected) {
    const list = $('skid-parts'); if (!list) return;
    list.replaceChildren();
    const supplier = $('field-supplier_name').value;
    const selectedParts = new Set(selected);
    for (const part of Object.values(state.data.parts).filter(item => item.supplier_name === supplier)) {
      const label = node('label');
      label.append(node('input', null, { type: 'checkbox', name: 'part_numbers', value: part.id, checked: selectedParts.has(part.id) }),
        document.createTextNode(`${part.id} / ${part.box_name}`));
      list.append(label);
    }
  }
  function setupCase(record) {
    field('description', '説明・検証目的', 'textarea', record.description).required = true;
    const supplierList = suppliers();
    const supplier = field('supplier_name', '仕入先（先に選択）', 'select', record.supplier_name || supplierList[0], supplierList.map(name => [name, name]));
    field('skid_id', 'スキッド', 'select', record.skid_id, []);
    state.editing.lines = clone(record.box_list || []);
    state.editing.supplier = supplier.value;
    state.editing.skid = record.skid_id || '';
    supplier.addEventListener('change', () => {
      if (state.editing.lines.some(row => row.count > 0) && !confirm('仕入先を変更すると入力中の数量をすべてクリアします。変更しますか？')) {
        supplier.value = state.editing.supplier; return;
      }
      state.editing.supplier = supplier.value; state.editing.skid = ''; state.editing.lines = [];
      updateSkidOptions(); refreshCaseLines();
    });
    $('field-skid_id').addEventListener('change', () => {
      const next = $('field-skid_id').value;
      if (state.editing.lines.some(row => row.count > 0) && next !== state.editing.skid
          && !confirm('スキッドを変更すると入力中の数量をすべてクリアします。変更しますか？')) {
        $('field-skid_id').value = state.editing.skid; return;
      }
      state.editing.skid = next; state.editing.lines = [];
      refreshCaseLines();
    });
    updateSkidOptions(record.skid_id);
    refreshCaseLines();
  }
  function updatePallets(preferred) {
    const input = $('field-pallet_id'); input.replaceChildren(node('option', '未設定', { value: '' }));
    for (const pallet of availablePallets($('field-supplier_name').value)) {
      input.append(node('option', `${pallet.model} / ${dimension(pallet)}`, { value: pallet.id }));
    }
    if ([...input.options].some(option => option.value === preferred)) input.value = preferred;
  }
  function updateSkidOptions(preferred) {
    const input = $('field-skid_id'); input.replaceChildren(node('option', 'スキッドを選択してください', { value: '' }));
    for (const [id, skid] of Object.entries(state.data.skids)) {
      if (skid.supplier_name === $('field-supplier_name').value) input.append(node('option', id, { value: id }));
    }
    if ([...input.options].some(option => option.value === preferred)) input.value = preferred;
  }
  function selectedSkid() {
    return state.data.skids[$('field-skid_id').value];
  }
  function refreshCaseLines() {
    const skid = selectedSkid();
    const pallet = skidPallet(skid);
    const complete = skidComplete(skid);
    $('case-skid-info').textContent = skid
      ? `パレット: ${pallet ? `${pallet.id} / ${pallet.model} (${dimension(pallet)} mm)` : '未設定'} / 荷山上限 L × W × H: ${skidLimits(skid)} mm / スキッド更新: ${skid.updated_at || '未保存'}`
      : 'スキッドを選択してください。パレット情報と荷山上限はスキッドDBから表示します。';
    $('case-skid-blocked').hidden = complete || !skid;
    $('case-skid-blocked').textContent = skid && !complete ? 'このスキッドは未設定項目があるため新規ケースを作成できず、計算もブロックされます。既存ケースの数量編集は可能です。' : '';
    const validParts = new Set((skid?.part_numbers || []).filter(partId => state.data.parts[partId]?.supplier_name === $('field-supplier_name').value));
    const ordered = [];
    for (const row of state.editing.lines) if (validParts.has(row.part_number) && !ordered.includes(row.part_number)) ordered.push(row.part_number);
    for (const partId of skid?.part_numbers || []) {
      if (validParts.has(partId) && !ordered.includes(partId)) ordered.push(partId);
    }
    const old = new Map(state.editing.lines.map(row => [row.part_number, row.count]));
    state.editing.lines = ordered.map(part_number => ({ part_number, count: old.get(part_number) || 0 }));
    renderLines();
  }
  function renderLines() {
    $('line-list').replaceChildren();
    state.editing.lines.forEach((row, index) => {
      const wrapper = node('div', null, { className: 'case-line' });
      const part = state.data.parts[row.part_number];
      const title = node('strong', `${row.part_number} / ${part?.box_name ?? '品番が見つかりません'}`);
      const info = node('p', null, { className: 'muted' });
      info.textContent = part ? `共通モデル: ${part.box_model_id} / 固定蓋: ${part.lid_id}` : '';
      const count = node('input', null, { type: 'number', min: '0', max: '500', step: '1', value: row.count || '', required: false });
      count.setAttribute('aria-label', `${row.part_number}の数量`);
      count.addEventListener('input', () => {
        row.count = count.value.trim() ? Number(count.value) : 0;
        state.formDirty = true; updateLineSummary();
      });
      wrapper.append(title, node('label', ' 数量（空欄・0は除外） '), count, info);
      $('line-list').append(wrapper);
    });
    updateLineSummary();
  }
  function updateLineSummary() {
    const included = state.editing.lines.filter(row => Number.isInteger(row.count) && row.count > 0);
    const total = included.reduce((sum, row) => sum + row.count, 0);
    $('line-summary').textContent = `選択品番数: ${included.length} / 箱数合計: ${total}`;
  }
  function submitEditor(event) {
    event.preventDefault();
    try {
      let id = normalized($('field-id').value);
      if (state.tab === 'skids') {
        const parts = ['supplier_number', 'work_area', 'shipping_area', 'course'].map(key => normalized($(`field-${key}`).value).toUpperCase());
        if (!/^[0-9]{4}$/.test(parts[0]) || !/^[A-Z0-9]$/.test(parts[1])
            || !/^(?:[A-Z0-9]{3})?$/.test(parts[2]) || !/^[A-Z]$/.test(parts[3])) {
          throw new Error('仕入先は半角数字4桁、工区は英数字1桁、出荷場は空欄または英数字3桁、コースは英字1桁で入力してください。');
        }
        if (!state.data.suppliers[parts[0]]) throw new Error('未登録の仕入先です。先に仕入先対応表へ登録してください。');
        id = parts.join('');
      }
      if (!id) throw new Error('IDを入力してください');
      if (id !== state.editing.id && (Object.hasOwn(records(), id)
          || (state.tab === 'skids' && state.originalSkids.has(id)
            && !Object.entries(state.skidRenames).some(([old, current]) => old === id && current === state.editing.id)))) {
        throw new Error('同じIDが存在します。文字を統一した結果も確認してください。');
      }
      const record = clone(state.editing.record);
      for (const input of $('fields').querySelectorAll('input[name], select[name], textarea[name]')) {
        if (['compatible_lids', 'part_numbers', 'supplier_number', 'work_area', 'shipping_area', 'course'].includes(input.name)) continue;
        if (input.type === 'number') {
          if (input.value.trim() === '' && state.tab === 'skids') { record[input.name] = null; continue; }
          if (input.value.trim() === '' || !Number.isFinite(Number(input.value))) throw new Error('数値を入力してください');
          record[input.name] = Number(input.value);
        } else if (input.name === 'suppliers' && state.tab === 'pallets') {
          record.suppliers = input.value.split(/\r?\n/).map(value => normalized(value)).filter(Boolean);
        } else record[input.name] = ['description', 'name', 'color'].includes(input.name) ? input.value.trim() : normalized(input.value);
      }
      record.id = id;
      if (state.tab === 'suppliers' && !/^[0-9]{4}$/.test(id)) throw new Error('仕入先は半角数字4桁で入力してください。');
      if (state.tab === 'models') {
        record.compatible_lids = [...$('fields').querySelectorAll('[name="compatible_lids"]:checked')].map(input => input.value);
        record.top_support_points = Number(record.top_support_points);
        record.module_ratio = record.module_ratio || null;
      }
      if (state.tab === 'pallets') {
        if (!record.suppliers.length) throw new Error('利用可能な仕入先を1件以上入力してください');
        if (record.length < record.width) throw new Error('パレットの長さLは幅W以上にしてください');
      }
      if (state.tab === 'skids') {
        record.supplier_name = state.data.suppliers[id.slice(0, 4)].supplier_name;
        if (record.pallet_id && !availablePallets(record.supplier_name).some(pallet => pallet.id === record.pallet_id)) {
          throw new Error('仕入先に適合するパレットを選択してください');
        }
        record.pallet_id = record.pallet_id || null;
        for (const key of ['max_x_span', 'max_y_span', 'max_height']) {
          if (record[key] !== null && (!Number.isFinite(record[key]) || record[key] <= 0)) throw new Error('荷山上限は空欄または正数にしてください');
        }
        record.pallet = {
          max_x_span: record.max_x_span, max_y_span: record.max_y_span, max_height: record.max_height
        };
        for (const key of ['max_x_span', 'max_y_span', 'max_height']) delete record[key];
        const selectedParts = [...$('fields').querySelectorAll('[name="part_numbers"]:checked')]
          .map(input => input.value).filter(partId => state.data.parts[partId]?.supplier_name === record.supplier_name);
        record.part_numbers = (record.part_numbers || []).filter(partId => selectedParts.includes(partId));
        record.part_numbers.push(...selectedParts.filter(partId => !record.part_numbers.includes(partId)));
        record.id = id;
        if (!state.editing.id) { record.updated_at = ''; record.history = []; }
      }
      if (caseMode) {
        if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$/.test(id)) throw new Error('ケースIDの形式が不正です');
        const skidId = $('field-skid_id').value;
        const skid = state.data.skids[skidId];
        if (!skid) throw new Error('スキッドを選択してください');
        if (!state.editing.id && !skidComplete(skid)) throw new Error('未設定項目のあるスキッドでは新規ケースを作成できません');
        if (state.editing.lines.some(row => row.count !== 0 && (!Number.isInteger(row.count) || row.count < 1 || row.count > 500))) {
          throw new Error('数量は空欄・0、または1〜500の整数にしてください');
        }
        const boxList = state.editing.lines.filter(row => row.count > 0)
          .map(row => ({ part_number: row.part_number, count: row.count }));
        if (!boxList.length) throw new Error('少なくとも1品番に1〜500の整数数量を入力してください');
        if (boxList.some(row => !(skid.part_numbers || []).includes(row.part_number)
            || state.data.parts[row.part_number]?.supplier_name !== $('field-supplier_name').value)) {
          throw new Error('投入品番は選択したスキッドの候補品番から選んでください');
        }
        if (state.editing.id && state.editing.record.skid_id !== skidId && !skidComplete(skid)) {
          throw new Error('未設定項目のあるスキッドへ既存ケースを変更できません');
        }
        Object.assign(record, {
          name: id, description: $('field-description').value.trim(),
          supplier_name: $('field-supplier_name').value, skid_id: skidId, box_list: boxList
        });
        delete record.id; delete record.pallet_id; delete record.pallet;
        if (!state.editing.id) state.data.cases.approval_state[id] = false;
      }
      if (state.tab === 'skids' && state.editing.id && state.editing.id !== id) {
        const previous = state.editing.id;
        const original = Object.keys(state.skidRenames).find(key => state.skidRenames[key] === previous)
          || (state.originalSkids.has(previous) ? previous : null);
        if (original) {
          if (original === id) delete state.skidRenames[original];
          else state.skidRenames[original] = id;
        }
        delete records()[previous];
        for (const item of Object.values(state.data.cases.test_cases)) {
          if (item.skid_id === previous) item.skid_id = id;
        }
      }
      records()[id] = record; mark(state.tab);
      state.formDirty = false; $('editor').close(); render();
      feedback('入力を確定しました。「まとめて保存」でファイルへ保存してください。');
    } catch (error) { $('form-error').textContent = error.message; }
  }
  $('edit-form').addEventListener('submit', submitEditor);
  $('edit-form').addEventListener('input', () => { state.formDirty = true; });
  $('edit-form').addEventListener('change', () => { state.formDirty = true; });
  function cancelEdit(event) {
    if (state.formDirty && !confirm('入力中の内容を破棄しますか？')) { event?.preventDefault(); return; }
    state.formDirty = false; $('editor').close();
  }
  $('cancel-edit').addEventListener('click', cancelEdit);
  $('editor').addEventListener('cancel', cancelEdit);
  $('add').addEventListener('click', () => openEditor());
  $('search').addEventListener('input', render);
  document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => { state.tab = button.dataset.tab; $('search').value = ''; render(); }));
  $('reload').addEventListener('click', () => {
    if (state.dirty.size && !confirm('未保存の編集を破棄して再読み込みしますか？')) return;
    busy(async () => { await load(); feedback('保存済みデータを読み込みました。'); });
  });
  function skidSnapshotText(snapshot) {
    if (!snapshot) return '（なし）';
    const limits = snapshot.pallet
      ? `${snapshot.pallet.max_x_span ?? '未設定'} × ${snapshot.pallet.max_y_span ?? '未設定'} × ${snapshot.pallet.max_height ?? '未設定'}`
      : '未設定';
    return `仕入先=${snapshot.supplier_name || '未設定'} / パレット=${snapshot.pallet_id || '未設定'} / 上限=${limits} / 品番=${(snapshot.part_numbers || []).join('、') || 'なし'}`;
  }
  $('save').addEventListener('click', () => busy(async () => {
    const payload = { revision: state.data.revision };
    for (const key of state.dirty) payload[key] = state.data[key];
    if (Object.keys(state.skidRenames).length) payload.skid_renames = { ...state.skidRenames };
    if (state.dirty.has('skids') || state.dirty.has('suppliers') || payload.skid_renames) {
      const plan = await api('/skid-preview', payload);
      if (plan.revision !== undefined && plan.revision !== state.data.revision) {
        throw new Error('別の画面で更新されています。再読み込みして再確認してください。');
      }
      const changes = (plan.changes || []).map(change =>
        `${change.old_skid_id ? `${change.old_skid_id} → ` : ''}${change.skid_id}: ${skidSnapshotText(change.before)} → ${skidSnapshotText(change.after)}\n影響ケース: ${(change.affected_cases || []).join('、') || 'なし'}`);
      for (const change of plan.supplier_changes || []) {
        const list = (items) => (items || []).join('、') || 'なし';
        changes.push(`仕入先名: ${change.before ?? '（なし）'} → ${change.after ?? '（なし）'}\n仕入先: ${list(change.affected_suppliers)}\n品番: ${list(change.affected_parts)}\nスキッド: ${list(change.affected_skids)}\nケース: ${list(change.affected_cases)}\nパレット: ${list(change.affected_pallets)}`);
      }
      const message = `変更の影響を確認してください。\n\n${changes.join('\n\n') || '変更対象なし'}\n\nこの内容で保存しますか？`;
      if (!confirm(message)) return;
      payload.confirmation = plan.confirmation;
    }
    await api('/save', payload);
    await load(); feedback('変更を保存しました。');
  }));
  for (const [id, approved] of [['approve-all', true], ['approve-none', false]]) $(id).addEventListener('click', () => {
    if (!confirm(`全ケースを${approved ? '採用' : '不採用'}にしますか？ 検索対象以外も含みます。`)) return;
    for (const key of Object.keys(state.data.cases.approval_state)) state.data.cases.approval_state[key] = approved;
    mark('cases'); render();
  });
  window.addEventListener('beforeunload', event => {
    if (state.dirty.size || state.formDirty || state.busy) { event.preventDefault(); event.returnValue = ''; }
  });
  busy(async () => { await load(); feedback('品番カタログとケースを読み込みました。'); });
})();
