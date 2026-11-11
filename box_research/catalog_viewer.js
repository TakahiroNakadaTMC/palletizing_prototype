'use strict';

(() => {
  const $ = id => document.getElementById(id);
  const clone = value => JSON.parse(JSON.stringify(value));
  const caseMode = location.pathname === '/catalog_cases.html';
  const state = { data: null, dirty: new Set(), tab: caseMode ? 'cases' : 'parts', busy: false, formDirty: false, editing: null };
  const titles = { parts: '品番・箱種DB', models: '箱モデルDB', lids: '蓋DB', pallets: 'パレットDB（参照）', cases: '品番方式のケース（切替準備用）' };
  const hints = {
    parts: '品番ごとに仕入先・箱名称・共通箱モデル・固定蓋を管理します。品番は文字列です。',
    models: '共通モデル名が表示名とIDを兼ねます。名前変更は「名前変更」から、関連品番・ケースを確認して行います。',
    lids: '蓋の仕様と嵌め方を管理します。使用中の蓋は削除できません。蓋IDの変更はこの段階では行いません。',
    pallets: '既存パレットDBの参照表示です。編集はDBサーバーの従来画面のパレットDBタブで行ってください。ケースで使用できるパレットは仕入先で絞ります。',
    cases: '仕入先→品番→数量の順で選びます。採用状態も準備用で、現在の実行対象は変わりません。第一候補の割当ては編集画面で確認できます。'
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
    $('add').disabled = state.busy || !state.data || state.tab === 'pallets';
    $('dirty').textContent = !state.data ? '未読込（再読み込みを押してください）'
      : state.dirty.size ? `未保存: ${[...state.dirty].map(key => titles[key]).join('、')}` : '保存済み';
    const id = $('field-id');
    if (id && state.editing?.id) id.disabled = true;
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
    state.data = data; state.dirty.clear();
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
  function caseLabel(caseData) {
    return caseData.box_list.map(row => {
      const part = state.data.parts[row.part_number];
      return `${row.part_number} / ${part.box_name} × ${row.count}`;
    }).join('、');
  }
  function columns(id, record) {
    switch (state.tab) {
      case 'parts': return [id, record.supplier_name, record.box_name, record.box_model_id, record.lid_id];
      case 'models': return [id, record.type, dimension(record), record.fitting_depth, record.rib_thickness, record.top_support_points, record.compatible_lids.join('、')];
      case 'lids': return [id, record.type, `${record.length} × ${record.width}`, record.thickness, record.fit_type, record.description || ''];
      case 'pallets': return [record.model, dimension(record), record.suppliers.join('、') || '全仕入先共通', id];
      default: return [id, record.description, record.supplier_name, caseLabel(record), `${record.pallet.max_x_span} × ${record.pallet.max_y_span} × ${record.pallet.max_height}`];
    }
  }
  const headers = {
    parts: ['品番', '仕入先', '箱名称', '共通箱モデル', '固定蓋'],
    models: ['共通モデル名', '規格', 'L × W × H (mm)', '嵌合深さ', 'リブ厚', '支持点数', '互換蓋'],
    lids: ['蓋ID', '規格', 'L × W (mm)', '高さ増加 (mm)', '嵌め方', '説明'],
    pallets: ['型番', 'L × W × H (mm)', '仕入先', '仕様ID'],
    cases: ['ケースID', '説明', '仕入先', '品番／箱名称・数量', '荷山最大L × W × H (mm)']
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
    for (const label of [...headers[state.tab], ...(caseMode ? ['採用（準備用）'] : []), ...(state.tab !== 'pallets' ? ['操作'] : [])]) head.append(node('th', label));
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
      if (state.tab !== 'pallets') {
        const td = node('td');
        const edit = node('button', '編集', { type: 'button' });
        edit.addEventListener('click', () => openEditor(id)); td.append(edit);
        if (state.tab === 'models') {
          const rename = node('button', '名前変更', { type: 'button' });
          rename.addEventListener('click', () => renameModel(id)); td.append(rename);
        }
        const remove = node('button', '削除', { type: 'button' });
        remove.addEventListener('click', () => removeRecord(id)); td.append(remove); tr.append(td);
      }
      $('table-body').append(tr);
    }
    $('counts').textContent = `${visible}件表示 / 全${Object.keys(records()).length}件`;
    controls();
  }
  function removeRecord(id) {
    const references = [];
    if (state.tab === 'parts') for (const [name, data] of Object.entries(state.data.cases.test_cases)) {
      if (data.box_list.some(row => row.part_number === id)) references.push(name);
    }
    if (state.tab === 'models' || state.tab === 'lids') {
      for (const part of Object.values(state.data.parts)) {
        if ((state.tab === 'models' ? part.box_model_id : part.lid_id) === id) references.push(part.id);
      }
      if (state.tab === 'lids') for (const model of Object.values(state.data.models)) {
        if (model.compatible_lids.includes(id)) references.push(model.id);
      }
      if (state.tab === 'models') references.push(...(state.data.model_references[id] || []).map(name => `旧箱名称: ${name}`));
    }
    if (references.length) { feedback(`使用中のため削除できません: ${references.join('、')}`, true); return; }
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
      await load(); feedback('モデル名と関連品番を保存しました。次回の品番方式の計算から反映されます。');
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
    const idInput = field('id', caseMode ? 'ケースID（英数字・下線・ハイフン）' : state.tab === 'models' ? '共通モデル名' : state.tab === 'parts' ? '品番（文字列）' : '蓋ID', 'text', id);
    idInput.required = true; idInput.disabled = Boolean(id);
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
    } else {
      setupCase(record);
    }
    $('case-lines').hidden = !caseMode;
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
  function setupCase(record) {
    field('description', '説明・検証目的', 'textarea', record.description).required = true;
    const suppliers = [...new Set(Object.values(state.data.parts).map(part => part.supplier_name))].sort();
    const supplier = field('supplier_name', '仕入先（先に選択）', 'select', record.supplier_name || suppliers[0], suppliers.map(name => [name, name]));
    field('pallet_id', 'パレット型番・本体 L × W × H (mm)', 'select', record.pallet_id, []);
    for (const [key, label, fallback] of [['max_x_span', '荷山最大L', 1360], ['max_y_span', '荷山最大W', 1100], ['max_height', '荷山最大H', 1200]]) {
      field(key, label + ' (mm)', 'number', record.pallet?.[key] ?? fallback);
    }
    state.editing.lines = clone(record.box_list || []);
    state.editing.supplier = supplier.value;
    supplier.addEventListener('change', () => {
      if (state.editing.lines.length && !confirm('仕入先を変更すると入力中の品番行をクリアします。変更しますか？')) {
        supplier.value = state.editing.supplier; return;
      }
      state.editing.supplier = supplier.value; state.editing.lines = [];
      updatePallets(); renderLines();
    });
    updatePallets(record.pallet_id); renderLines();
    const assignments = state.data.assignments.filter(row => row.case_file === `${state.editing.id}.json` && row.status === 'first_candidate');
    $('assignment-help').textContent = assignments.length ? '移行時の第一候補（変更可能）: ' + assignments.map(row => `箱行${row.row}: ${row.candidates.join('、')}`).join(' / ') : '';
  }
  function updatePallets(preferred) {
    const input = $('field-pallet_id'); input.replaceChildren();
    for (const pallet of availablePallets($('field-supplier_name').value)) {
      input.append(node('option', `${pallet.model} / ${dimension(pallet)}`, { value: pallet.id }));
    }
    if ([...input.options].some(option => option.value === preferred)) input.value = preferred;
  }
  function renderLines() {
    $('line-list').replaceChildren();
    state.editing.lines.forEach((row, index) => {
      const wrapper = node('div', null, { className: 'case-line' });
      const search = node('input', null, { type: 'search', placeholder: '品番・箱名称で候補を検索' });
      search.setAttribute('aria-label', `箱行${index + 1}の品番検索`);
      const select = node('select'); select.setAttribute('aria-label', `箱行${index + 1}の品番`);
      const info = node('p', null, { className: 'muted' });
      function populate() {
        select.replaceChildren(node('option', '品番を選択してください', { value: '' }));
        const query = search.value.toLowerCase();
        for (const part of Object.values(state.data.parts)) {
          if (part.supplier_name !== $('field-supplier_name').value) continue;
          if (part.id !== row.part_number && !`${part.id} ${part.box_name}`.toLowerCase().includes(query)) continue;
          select.append(node('option', `${part.id} / ${part.box_name}`, { value: part.id }));
        }
        select.value = row.part_number || '';
      }
      function describe() {
        const part = state.data.parts[row.part_number];
        info.textContent = part ? `箱名称: ${part.box_name} / 共通モデル: ${part.box_model_id} / 固定蓋: ${part.lid_id}` : '品番を選ぶと箱と蓋を自動表示します。';
      }
      search.addEventListener('input', populate);
      select.addEventListener('change', () => { row.part_number = select.value; describe(); state.formDirty = true; });
      const count = node('input', null, { type: 'number', min: '1', max: '500', step: '1', value: row.count, required: true });
      count.setAttribute('aria-label', `箱行${index + 1}の数量`);
      count.addEventListener('input', () => { row.count = Number(count.value); state.formDirty = true; });
      const remove = node('button', '行を削除', { type: 'button' });
      remove.addEventListener('click', () => { state.editing.lines.splice(index, 1); state.formDirty = true; renderLines(); });
      populate(); describe();
      wrapper.append(search, node('br'), select, node('label', ' 数量 '), count, remove, info);
      $('line-list').append(wrapper);
    });
  }
  function submitEditor(event) {
    event.preventDefault();
    try {
      const id = normalized($('field-id').value);
      if (!id) throw new Error('IDを入力してください');
      if (!state.editing.id && Object.hasOwn(records(), id)) throw new Error('同じIDが存在します。文字を統一した結果も確認してください。');
      const record = clone(state.editing.record);
      for (const input of $('fields').querySelectorAll('input[name], select[name], textarea[name]')) {
        if (input.name === 'compatible_lids') continue;
        if (input.type === 'number') {
          if (input.value.trim() === '' || !Number.isFinite(Number(input.value))) throw new Error('数値を入力してください');
          record[input.name] = Number(input.value);
        } else record[input.name] = ['description', 'name', 'color'].includes(input.name) ? input.value.trim() : normalized(input.value);
      }
      record.id = id;
      if (state.tab === 'models') {
        record.compatible_lids = [...$('fields').querySelectorAll('[name="compatible_lids"]:checked')].map(input => input.value);
        record.top_support_points = Number(record.top_support_points);
        record.module_ratio = record.module_ratio || null;
      }
      if (caseMode) {
        if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$/.test(id)) throw new Error('ケースIDの形式が不正です');
        if (!state.editing.lines.length || state.editing.lines.some(row => !row.part_number || !Number.isInteger(row.count) || row.count < 1 || row.count > 500)) throw new Error('品番と1〜500の整数の数量を入力してください');
        record.name = id; delete record.id;
        record.box_list = clone(state.editing.lines);
        record.pallet = {};
        for (const key of ['max_x_span', 'max_y_span', 'max_height']) { record.pallet[key] = record[key]; delete record[key]; }
        if (Object.values(record.pallet).some(value => value <= 0) || record.pallet.max_x_span < record.pallet.max_y_span) throw new Error('荷山上限は正数、最大Lは最大W以上にしてください');
        if (!record.pallet_id) throw new Error('パレットを選択してください');
        if (!state.editing.id) state.data.cases.approval_state[id] = false;
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
  $('add-line').addEventListener('click', () => { state.editing.lines.push({ part_number: '', count: 1 }); state.formDirty = true; renderLines(); });
  $('add').addEventListener('click', () => openEditor());
  $('search').addEventListener('input', render);
  document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => { state.tab = button.dataset.tab; $('search').value = ''; render(); }));
  $('reload').addEventListener('click', () => {
    if (state.dirty.size && !confirm('未保存の編集を破棄して再読み込みしますか？')) return;
    busy(async () => { await load(); feedback('保存済みデータを読み込みました。'); });
  });
  $('save').addEventListener('click', () => busy(async () => {
    const payload = { revision: state.data.revision };
    for (const key of state.dirty) payload[key] = state.data[key];
    await api('/save', payload);
    await load(); feedback('品番方式のデータを保存しました。次回の品番方式の計算から反映されます。旧方式のデータは変更していません。');
  }));
  for (const [id, approved] of [['approve-all', true], ['approve-none', false]]) $(id).addEventListener('click', () => {
    if (!confirm(`全ケースを${approved ? '採用' : '不採用'}予定にしますか？ 検索対象以外も含みます。`)) return;
    for (const key of Object.keys(state.data.cases.approval_state)) state.data.cases.approval_state[key] = approved;
    mark('cases'); render();
  });
  window.addEventListener('beforeunload', event => {
    if (state.dirty.size || state.formDirty || state.busy) { event.preventDefault(); event.returnValue = ''; }
  });
  busy(async () => { await load(); feedback('品番方式のデータを読み込みました。計算はCLIから明示的に実行してください。'); });
})();
