(function () {
  const state = {
    loaded: false,
    loadError: '',
    saving: false,
    activeTab: 'boxes',
    draft: { boxes: {}, lids: {} },
    persisted: { boxes: {}, lids: {} },
    approval: {},
    lidReferences: {},
    lidReferencesLoaded: false,
    boxReferences: {},
    boxReferencesLoaded: false,
    boxSearch: '',
    boxFilter: 'all',
    lidSearch: '',
    editingBoxId: null,
    editingLidId: null,
    formDirty: { box: false, lid: false },
    boxLidSyncTouched: false,
  };

  const el = {
    globalDirty: byId('global-dirty'),
    errorBanner: byId('error-banner'),
    errorText: byId('error-text'),
    retryLoad: byId('btn-retry-load'),
    saveFeedback: byId('save-feedback'),
    tabBoxes: byId('tab-boxes'),
    tabLids: byId('tab-lids'),
    panelBoxes: byId('panel-boxes'),
    panelLids: byId('panel-lids'),
    boxStatus: byId('box-status'),
    lidStatus: byId('lid-status'),
    boxSearch: byId('box-search'),
    boxesBody: byId('boxes-body'),
    lidsBody: byId('lids-body'),
    boxNoResults: byId('box-no-results'),
    selectAll: byId('btn-select-all'),
    deselectAll: byId('btn-deselect-all'),
    selectTpOnly: byId('btn-select-tp-only'),
    copyJson: byId('btn-copy-json'),
    downloadJson: byId('btn-download-json'),
    reloadAll: byId('btn-reload-all'),
    boxAdd: byId('btn-box-add'),
    boxSave: byId('btn-box-save'),
    lidAdd: byId('btn-lid-add'),
    lidSave: byId('btn-lid-save'),
    statTotal: byId('stat-total'),
    statApproved: byId('stat-approved'),
    statApprovedSub: byId('stat-approved-total-sub'),
    statApprovedTp: byId('stat-approved-tp'),
    statApprovedNonTp: byId('stat-approved-nontp'),
    statLidCount: byId('stat-lid-count'),
    statOuterFit: byId('stat-outer-fit'),
    statInnerFit: byId('stat-inner-fit'),
    boxDialog: byId('box-dialog'),
    boxDialogContainer: byId('box-dialog-container'),
    boxForm: byId('box-form'),
    boxFormTitle: byId('box-form-title'),
    boxModalSubtitle: byId('box-modal-subtitle'),
    boxModalIconBg: byId('box-modal-icon-bg'),
    boxSubmitLabel: byId('box-submit-label'),
    boxCancel: byId('box-cancel'),
    boxClose: byId('btn-close-box-modal'),
    boxId: byId('box-id'),
    boxName: byId('box-name'),
    boxType: byId('box-type'),
    boxModule: byId('box-module'),
    boxFitting: byId('box-fitting'),
    boxLength: byId('box-length'),
    boxWidth: byId('box-width'),
    boxHeight: byId('box-height'),
    boxRib: byId('box-rib'),
    boxDescription: byId('box-description'),
    boxCompatibleLids: byId('box-compatible-lids'),
    lidDialog: byId('lid-dialog'),
    lidDialogContainer: byId('lid-dialog-container'),
    lidForm: byId('lid-form'),
    lidFormTitle: byId('lid-form-title'),
    lidModalSubtitle: byId('lid-modal-subtitle'),
    lidSubmitLabel: byId('lid-submit-label'),
    lidCancel: byId('lid-cancel'),
    lidClose: byId('btn-close-lid-modal'),
    lidId: byId('lid-id'),
    lidName: byId('lid-name'),
    lidType: byId('lid-type'),
    lidColor: byId('lid-color'),
    lidFitType: byId('lid-fit-type'),
    lidLength: byId('lid-length'),
    lidWidth: byId('lid-width'),
    lidThickness: byId('lid-thickness'),
    lidDescription: byId('lid-description'),
    toast: byId('toast'),
    toastMsg: byId('toast-msg'),
  };

  function byId(id) {
    return document.getElementById(id);
  }

  function qsa(selector, root) {
    const target = root || document;
    if (!target || typeof target.querySelectorAll !== 'function') return [];
    return target.querySelectorAll(selector);
  }

  function clone(obj) {
    return JSON.parse(JSON.stringify(obj));
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function asNumber(value, fallback) {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  }

  function normalizeDimensionOrder(db) {
    Object.values(db).forEach(item => {
      const width = Number(item.width);
      const length = Number(item.length);
      if (Number.isFinite(width) && Number.isFinite(length) && width > length) {
        item.width = length;
        item.length = width;
      }
    });
    return db;
  }

  function refreshIcons() {
    if (typeof lucide !== 'undefined' && lucide && typeof lucide.createIcons === 'function') {
      lucide.createIcons();
    }
  }

  function showToast(message) {
    if (!el.toast || !el.toastMsg) return;
    el.toastMsg.textContent = message;
    el.toast.classList.remove('opacity-0', 'translate-y-4');
    el.toast.classList.add('opacity-100', 'translate-y-0');
    setTimeout(() => {
      el.toast.classList.remove('opacity-100', 'translate-y-0');
      el.toast.classList.add('opacity-0', 'translate-y-4');
    }, 2600);
  }

  function setFeedback(kind, message) {
    el.saveFeedback.classList.remove('hidden', 'info', 'success', 'warning');
    el.saveFeedback.classList.add(kind || 'info');
    el.saveFeedback.textContent = message;
  }

  function clearFeedback() {
    el.saveFeedback.classList.add('hidden');
    el.saveFeedback.classList.remove('info', 'success', 'warning');
    el.saveFeedback.textContent = '';
  }

  function computeDirty() {
    const approvedDraftBoxes = getApprovedBoxes();
    return {
      boxesDirty: JSON.stringify(approvedDraftBoxes) !== JSON.stringify(state.persisted.boxes),
      lidsDirty: JSON.stringify(state.draft.lids) !== JSON.stringify(state.persisted.lids),
    };
  }

  function hasUnsavedChanges() {
    const dirty = computeDirty();
    return dirty.boxesDirty || dirty.lidsDirty || state.formDirty.box || state.formDirty.lid;
  }

  function updateDirtyIndicator() {
    el.globalDirty.classList.remove('bg-slate-100', 'text-slate-700', 'bg-emerald-100', 'text-emerald-700', 'bg-amber-100', 'text-amber-800', 'bg-rose-100', 'text-rose-700');
    if (!state.loaded) {
      el.globalDirty.classList.add('bg-rose-100', 'text-rose-700');
      el.globalDirty.textContent = '状態: 読み込み失敗';
      return;
    }
    const dirty = computeDirty();
    if (!dirty.boxesDirty && !dirty.lidsDirty && !state.formDirty.box && !state.formDirty.lid) {
      el.globalDirty.classList.add('bg-emerald-100', 'text-emerald-700');
      el.globalDirty.textContent = '状態: 保存済み';
      return;
    }
    const parts = [];
    if (dirty.boxesDirty) parts.push('箱ドラフト未保存');
    if (dirty.lidsDirty) parts.push('蓋ドラフト未保存');
    if (state.formDirty.box || state.formDirty.lid) parts.push('編集中フォーム未反映');
    el.globalDirty.classList.add('bg-amber-100', 'text-amber-800');
    el.globalDirty.textContent = `状態: ${parts.join(' / ')}`;
  }

  function setEditable(enabled) {
    const controls = [
      el.tabBoxes, el.tabLids, el.boxSearch, el.lidSearch,
      el.selectAll, el.deselectAll, el.selectTpOnly, el.copyJson, el.downloadJson, el.reloadAll,
      el.boxAdd, el.boxSave, el.lidAdd, el.lidSave,
      ...qsa('.filter-tab'),
    ];
    controls.forEach(control => {
      if (control) control.disabled = !enabled;
    });
    qsa('button,input,select', el.boxesBody).forEach(n => { n.disabled = !enabled; });
    qsa('button,input,select', el.lidsBody).forEach(n => { n.disabled = !enabled; });
  }

  function setSaving(flag) {
    state.saving = flag;
    setEditable(state.loaded && !flag);
    if (flag) {
      el.boxStatus.textContent = '保存中... 完了まで編集をロックしています。';
      el.lidStatus.textContent = '保存中... 完了まで編集をロックしています。';
    }
  }

  function validateLoadedShape(boxes, lids, refs, boxRefs) {
    if (!boxes || typeof boxes !== 'object' || Array.isArray(boxes)) throw new Error('箱DB形式不正');
    if (!lids || typeof lids !== 'object' || Array.isArray(lids)) throw new Error('蓋DB形式不正');
    if (!refs || typeof refs !== 'object' || Array.isArray(refs)) throw new Error('蓋参照形式不正');
    if (!boxRefs || typeof boxRefs !== 'object' || Array.isArray(boxRefs)
        || Object.values(boxRefs).some(names => !Array.isArray(names) || names.some(name => typeof name !== 'string'))) {
      throw new Error('箱参照形式不正');
    }
  }

  function showError(message) {
    state.loaded = false;
    state.boxReferencesLoaded = false;
    state.loadError = message;
    el.errorText.textContent = message;
    el.errorBanner.classList.remove('hidden');
    el.boxStatus.textContent = '読み込み失敗のため編集できません。再試行してください。';
    el.lidStatus.textContent = '読み込み失敗のため編集できません。再試行してください。';
    setEditable(false);
    updateDirtyIndicator();
  }

  function hideError() {
    el.errorBanner.classList.add('hidden');
  }

  async function loadAll() {
    hideError();
    setEditable(false);
    state.loaded = false;
    el.boxStatus.textContent = '箱・蓋・参照情報を読み込み中...';
    el.lidStatus.textContent = '箱・蓋・参照情報を読み込み中...';
    try {
      const [boxesRes, lidsRes, refsRes, boxRefsRes] = await Promise.all([
        fetch('/api/boxes', { cache: 'no-store' }),
        fetch('/api/lids', { cache: 'no-store' }),
        fetch('/api/lid_references', { cache: 'no-store' }),
        fetch('/api/box_references', { cache: 'no-store' }),
      ]);
      if (!boxesRes.ok) throw new Error(`箱DB取得に失敗 (HTTP ${boxesRes.status})`);
      if (!lidsRes.ok) throw new Error(`蓋DB取得に失敗 (HTTP ${lidsRes.status})`);
      if (!refsRes.ok) throw new Error(`蓋参照取得に失敗 (HTTP ${refsRes.status})`);
      if (!boxRefsRes.ok) throw new Error(`箱参照取得に失敗 (HTTP ${boxRefsRes.status})`);

      const boxes = normalizeDimensionOrder(await boxesRes.json());
      const lids = normalizeDimensionOrder(await lidsRes.json());
      const refs = await refsRes.json();
      const boxRefs = await boxRefsRes.json();
      validateLoadedShape(boxes, lids, refs, boxRefs);

      state.persisted.boxes = clone(boxes);
      state.persisted.lids = clone(lids);
      state.draft.boxes = clone(boxes);
      state.draft.lids = clone(lids);
      state.approval = {};
      Object.keys(state.draft.boxes).forEach(id => { state.approval[id] = true; });
      state.lidReferences = refs;
      state.lidReferencesLoaded = true;
      state.boxReferences = boxRefs;
      state.boxReferencesLoaded = true;
      state.formDirty.box = false;
      state.formDirty.lid = false;
      state.boxLidSyncTouched = false;
      state.loaded = true;
      state.loadError = '';
      setEditable(true);
      renderAll();
      clearFeedback();
    } catch (error) {
      showError(error.message || '読み込みに失敗しました');
    }
  }

  function updateStats() {
    const allIds = Object.keys(state.draft.boxes);
    const total = allIds.length;
    let approved = 0;
    let approvedTp = 0;
    let approvedNonTp = 0;
    allIds.forEach(id => {
      if (state.approval[id] !== false) {
        approved += 1;
        if (state.draft.boxes[id].type === 'TP') approvedTp += 1;
        else approvedNonTp += 1;
      }
    });
    el.statTotal.textContent = String(total);
    el.statApproved.textContent = String(approved);
    el.statApprovedSub.textContent = `/ ${total} 箱`;
    el.statApprovedTp.textContent = String(approvedTp);
    el.statApprovedNonTp.textContent = String(approvedNonTp);

    const lids = Object.values(state.draft.lids);
    el.statLidCount.textContent = String(lids.length);
    el.statOuterFit.textContent = String(lids.filter(l => l.fit_type === '外嵌め').length);
    el.statInnerFit.textContent = String(lids.filter(l => l.fit_type === '内嵌め').length);
  }

  function refreshStatusLines() {
    const approvedCount = Object.values(state.approval).filter(Boolean).length;
    el.boxStatus.textContent = `編集・採用状態は画面内のみで保持します。「box_db.json に保存」で採用中の箱をマスタに反映してください。承認済み: ${approvedCount}件`;
    el.lidStatus.textContent = `編集状態は画面内のみで保持します。「lid_db.json に保存」でマスタに反映してください。登録数: ${Object.keys(state.draft.lids).length}件`;
  }

  function renderAll() {
    renderBoxes();
    renderLids();
    updateStats();
    refreshStatusLines();
    updateDirtyIndicator();
    refreshIcons();
  }

  function renderBoxes() {
    const tbody = el.boxesBody;
    tbody.innerHTML = '';
    const q = state.boxSearch.trim().toLowerCase();
    const rows = Object.values(state.draft.boxes).filter(box => {
      const approved = state.approval[box.id] !== false;
      if (state.boxFilter === 'TP' && box.type !== 'TP') return false;
      if (state.boxFilter === 'NON_TP' && box.type !== 'NON_TP') return false;
      if (state.boxFilter === 'approved' && !approved) return false;
      if (state.boxFilter === 'rejected' && approved) return false;
      if (!q) return true;
      const target = `${box.id} ${box.name || ''} ${box.description || ''} ${box.module_ratio || ''}`.toLowerCase();
      return target.includes(q);
    });

    rows.forEach(box => {
      const isApproved = state.approval[box.id] !== false;
      const tr = document.createElement('tr');
      tr.className = `hover:bg-slate-50 transition border-b border-slate-100 ${isApproved ? '' : 'bg-slate-50/60 opacity-60'}`;
      const typeBadge = box.type === 'TP' ? 'badge-tp' : 'badge-nontp';
      tr.innerHTML = `
        <td class="py-3 px-4 text-center">
          <input type="checkbox" data-approve-id="${escapeHtml(box.id)}" class="box-checkbox w-4 h-4 text-indigo-600 rounded border-slate-300 focus:ring-indigo-500 cursor-pointer" ${isApproved ? 'checked' : ''}>
        </td>
        <td class="py-3 px-4">
          <button type="button" data-toggle-status data-id="${escapeHtml(box.id)}" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold cursor-pointer transition ${isApproved ? 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200' : 'bg-rose-100 text-rose-800 hover:bg-rose-200'}">
            <i data-lucide="${isApproved ? 'check' : 'x'}" class="w-3 h-3"></i>
            <span>${isApproved ? '採用' : '不採用'}</span>
          </button>
        </td>
        <td class="py-3 px-4 font-mono font-bold text-slate-900">${escapeHtml(box.id)}</td>
        <td class="py-3 px-4 font-medium text-slate-800">${escapeHtml(box.name || '')}</td>
        <td class="py-3 px-3"><span class="inline-block px-2 py-0.5 rounded text-[11px] font-bold ${typeBadge}">${box.type === 'TP' ? 'TP規格' : '非TP'}</span></td>
        <td class="py-3 px-3 text-right font-mono font-semibold">${escapeHtml(String(box.length ?? ''))}</td>
        <td class="py-3 px-3 text-right font-mono font-semibold">${escapeHtml(String(box.width ?? ''))}</td>
        <td class="py-3 px-3 text-right font-mono font-semibold">${escapeHtml(String(box.height ?? ''))}</td>
        <td class="py-3 px-3 text-right font-mono text-indigo-600 font-bold">${escapeHtml(String(box.fitting_depth ?? ''))}</td>
        <td class="py-3 px-3 text-right font-mono text-slate-600 font-bold">${escapeHtml(String(box.rib_thickness ?? ''))}</td>
        <td class="py-3 px-3 text-center font-mono text-slate-600">${box.module_ratio ? `<span class="bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">${escapeHtml(box.module_ratio)}</span>` : '<span class="text-slate-300">-</span>'}</td>
        <td class="py-3 px-4 text-slate-500 max-w-xs truncate" title="${escapeHtml(box.description || '')}">${escapeHtml(box.description || '-')}</td>
        <td class="py-3 px-3 text-center">
          <div class="inline-flex items-center gap-1">
            <button type="button" data-box-edit="${escapeHtml(box.id)}" class="p-1 text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 rounded transition" title="この箱の寸法・仕様を変更" aria-label="この箱の寸法・仕様を変更">
              <i data-lucide="edit-3" class="w-3.5 h-3.5"></i>
            </button>
            <button type="button" data-box-delete="${escapeHtml(box.id)}" class="p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded transition" title="この箱を削除" aria-label="この箱を削除">
              <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
            </button>
          </div>
        </td>`;
      tbody.appendChild(tr);
    });

    el.boxNoResults.classList.toggle('hidden', rows.length > 0);

    tbody.querySelectorAll('[data-approve-id]').forEach(node => {
      node.addEventListener('change', () => {
        if (!guardEditable()) return;
        setBoxApproval(node.getAttribute('data-approve-id'), !!node.checked);
        renderAll();
      });
    });
    tbody.querySelectorAll('[data-toggle-status]').forEach(node => {
      node.addEventListener('click', () => {
        if (!guardEditable()) return;
        const id = node.getAttribute('data-id');
        setBoxApproval(id, !(state.approval[id] !== false));
        renderAll();
      });
    });
    tbody.querySelectorAll('[data-box-edit]').forEach(node => {
      node.addEventListener('click', () => {
        if (!guardEditable()) return;
        openBoxDialog(node.getAttribute('data-box-edit'));
      });
    });
    tbody.querySelectorAll('[data-box-delete]').forEach(node => {
      node.addEventListener('click', () => {
        if (!guardEditable()) return;
        deleteBox(node.getAttribute('data-box-delete'));
      });
    });
  }

  function renderLids() {
    const tbody = el.lidsBody;
    tbody.innerHTML = '';
    const q = (state.lidSearch || '').trim().toLowerCase();
    const rows = Object.values(state.draft.lids).filter(lid => {
      if (!q) return true;
      return `${lid.id} ${lid.name || ''} ${lid.description || ''}`.toLowerCase().includes(q);
    });
    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="10" class="px-4 py-8 text-center text-slate-500">登録された蓋がありません</td></tr>';
      return;
    }

    rows.forEach(lid => {
      const typeDisplay = {
        TP: { label: 'TP規格', className: 'badge-tp' },
        NONE: { label: '無蓋', className: 'bg-slate-100 text-slate-700 border border-slate-200' },
        OTHER: { label: 'その他', className: 'badge-nontp' },
      }[lid.type] || { label: lid.type || '未設定', className: 'bg-slate-100 text-slate-600 border border-slate-200' };
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-slate-50 transition';
      tr.innerHTML = `
        <td class="py-3 px-4 font-mono font-bold text-slate-900">${escapeHtml(lid.id)}</td>
        <td class="py-3 px-4 font-medium text-slate-800">${escapeHtml(lid.name || '')}</td>
        <td class="py-3 px-3"><span class="inline-block px-2 py-0.5 rounded text-[11px] font-bold ${typeDisplay.className}">${typeDisplay.label}</span></td>
        <td class="py-3 px-3 text-slate-600 whitespace-nowrap">${escapeHtml(lid.color || '未設定')}</td>
        <td class="py-3 px-3 text-right font-mono font-semibold">${escapeHtml(String(lid.length ?? ''))}</td>
        <td class="py-3 px-3 text-right font-mono font-semibold">${escapeHtml(String(lid.width ?? ''))}</td>
        <td class="py-3 px-3 text-right font-mono text-slate-600">${escapeHtml(String(lid.thickness ?? ''))}</td>
        <td class="py-3 px-3">
          <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${lid.fit_type === '外嵌め' ? 'bg-blue-100 text-blue-700' : lid.fit_type === '内嵌め' ? 'bg-purple-100 text-purple-700' : 'bg-slate-100 text-slate-700'}">${escapeHtml(lid.fit_type || '未設定')}</span>
        </td>
        <td class="py-3 px-4 text-slate-500 max-w-xs truncate" title="${escapeHtml(lid.description || '')}">${escapeHtml(lid.description || '—')}</td>
        <td class="py-3 px-3 text-center">
          <div class="inline-flex items-center gap-1">
            <button type="button" data-lid-edit="${escapeHtml(lid.id)}" class="p-1 text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 rounded transition" title="この蓋の寸法・仕様を変更" aria-label="この蓋の寸法・仕様を変更">
              <i data-lucide="edit-3" class="w-3.5 h-3.5"></i>
            </button>
            <button type="button" data-lid-delete="${escapeHtml(lid.id)}" class="p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded transition" title="この蓋を削除" aria-label="この蓋を削除">
              <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
            </button>
          </div>
        </td>`;
      tbody.appendChild(tr);
    });

    qsa('[data-lid-edit]', tbody).forEach(node => {
      node.addEventListener('click', () => {
        if (!guardEditable()) return;
        openLidDialog(node.getAttribute('data-lid-edit'));
      });
    });
    qsa('[data-lid-delete]', tbody).forEach(node => {
      node.addEventListener('click', () => {
        if (!guardEditable()) return;
        deleteLid(node.getAttribute('data-lid-delete'));
      });
    });
  }

  function openOverlay(dialog, container) {
    dialog.classList.remove('hidden');
    setTimeout(() => {
      dialog.classList.remove('opacity-0');
      container.classList.remove('scale-95');
      container.classList.add('scale-100');
    }, 10);
  }

  function closeOverlay(dialog, container) {
    dialog.classList.add('opacity-0');
    container.classList.remove('scale-100');
    container.classList.add('scale-95');
    dialog.classList.add('hidden');
  }

  function renderCompatibleLids(selectedLids) {
    el.boxCompatibleLids.innerHTML = '';
    const noLidAvailable = Object.values(state.draft.lids).some(l => l.type === 'NONE');
    const note = document.createElement('p');
    note.className = 'text-xs text-slate-600 sm:col-span-2';
    note.textContent = noLidAvailable
      ? '無蓋はすべての箱で選択できます（互換蓋への登録は不要です）。'
      : '蓋DBに「無蓋」の定義がありません。';
    el.boxCompatibleLids.appendChild(note);

    const lids = Object.values(state.draft.lids).filter(l => l.type !== 'NONE');
    if (lids.length === 0) {
      const p = document.createElement('p');
      p.className = 'text-xs text-slate-500 italic sm:col-span-2';
      p.textContent = '選択可能な蓋がありません';
      el.boxCompatibleLids.appendChild(p);
      return;
    }
    lids.forEach(lid => {
      const label = document.createElement('label');
      label.className = 'flex items-center gap-2 p-2 border border-slate-200 rounded-lg hover:bg-slate-50 cursor-pointer transition';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.className = 'w-4 h-4 text-indigo-600 rounded border-slate-300 focus:ring-indigo-500';
      input.value = lid.id;
      input.checked = selectedLids.includes(lid.id);
      input.addEventListener('change', () => {
        state.formDirty.box = true;
        updateDirtyIndicator();
      });
      const details = document.createElement('div');
      details.className = 'flex-1 min-w-0';
      const name = document.createElement('div');
      name.className = 'text-xs font-bold text-slate-900';
      name.textContent = lid.name || lid.id;
      const fitType = document.createElement('span');
      fitType.className = 'ml-1 font-medium text-slate-600';
      fitType.textContent = `（${lid.fit_type || '嵌め方未設定'}）`;
      name.appendChild(fitType);

      const dimensions = document.createElement('div');
      dimensions.className = 'text-[11px] text-slate-500';
      dimensions.textContent = `${lid.id} • ${lid.length ?? '?'}×${lid.width ?? '?'} mm`;
      details.append(name, dimensions);

      label.append(input, details);
      el.boxCompatibleLids.appendChild(label);
    });
  }

  function openBoxDialog(boxId) {
    state.editingBoxId = boxId || null;
    state.formDirty.box = false;
    if (boxId && state.draft.boxes[boxId]) {
      const box = state.draft.boxes[boxId];
      el.boxFormTitle.textContent = `箱仕様の編集 (${box.id})`;
      el.boxModalSubtitle.textContent = '寸法、勘合深さ、上縁幅等のパラメータを変更します';
      el.boxSubmitLabel.textContent = '変更を反映';
      el.boxModalIconBg.className = 'p-2 bg-indigo-100 text-indigo-700 rounded-lg';
      el.boxId.value = box.id || '';
      el.boxId.disabled = true;
      el.boxName.value = box.name || '';
      el.boxType.value = box.type || 'TP';
      el.boxModule.value = box.module_ratio || '';
      el.boxFitting.value = box.fitting_depth ?? '';
      el.boxLength.value = box.length ?? '';
      el.boxWidth.value = box.width ?? '';
      el.boxHeight.value = box.height ?? '';
      el.boxRib.value = box.rib_thickness ?? '';
      el.boxDescription.value = box.description || '';
      renderCompatibleLids(box.compatible_lids || []);
    } else {
      el.boxFormTitle.textContent = '新しい箱の仕様を登録';
      el.boxModalSubtitle.textContent = 'パレタイズ対象として箱データベースに追加します';
      el.boxSubmitLabel.textContent = '登録して採用';
      el.boxModalIconBg.className = 'p-2 bg-emerald-100 text-emerald-700 rounded-lg';
      el.boxForm.reset();
      el.boxId.disabled = false;
      el.boxType.value = 'TP';
      el.boxFitting.value = '10.0';
      el.boxRib.value = '22.0';
      renderCompatibleLids([]);
    }
    openOverlay(el.boxDialog, el.boxDialogContainer);
    refreshIcons();
  }

  function closeBoxDialog() {
    state.formDirty.box = false;
    state.editingBoxId = null;
    closeOverlay(el.boxDialog, el.boxDialogContainer);
    updateDirtyIndicator();
  }

  function submitBoxForm(event) {
    event.preventDefault();
    if (!guardEditable()) return;
    const id = el.boxId.value.trim();
    const name = el.boxName.value.trim();
    if (!id || !name) return alert('箱IDと箱名称は必須です');
    const length = asNumber(el.boxLength.value, NaN);
    const width = asNumber(el.boxWidth.value, NaN);
    const height = asNumber(el.boxHeight.value, NaN);
    const fittingDepth = asNumber(el.boxFitting.value, NaN);
    if ([length, width, height, fittingDepth].some(v => !Number.isFinite(v))) return alert('必須数値を入力してください');
    if (length < width) return alert('長さ L は幅 W 以上にしてください');
    if (!state.editingBoxId && state.draft.boxes[id]) return alert(`箱ID "${id}" は既に存在します`);

    const existing = state.editingBoxId ? clone(state.draft.boxes[state.editingBoxId]) : {};
    const next = Object.assign(existing, {
      id,
      name,
      type: el.boxType.value,
      module_ratio: el.boxType.value === 'TP' ? (el.boxModule.value.trim() || null) : null,
      fitting_depth: fittingDepth,
      length,
      width,
      height,
      rib_thickness: asNumber(el.boxRib.value, existing.rib_thickness ?? 0),
      description: el.boxDescription.value.trim(),
      compatible_lids: Array.from(qsa('input[type="checkbox"]:checked', el.boxCompatibleLids)).map(n => n.value),
    });

    if (state.editingBoxId && state.editingBoxId !== id) {
      if (!guardBoxRemoval([state.editingBoxId], 'ID変更')) return;
      if (state.draft.boxes[id]) return alert(`箱ID "${id}" は既に存在します`);
      delete state.draft.boxes[state.editingBoxId];
      delete state.approval[state.editingBoxId];
    }
    state.draft.boxes[id] = next;
    if (!Object.prototype.hasOwnProperty.call(state.approval, id)) state.approval[id] = true;
    state.formDirty.box = false;
    closeOverlay(el.boxDialog, el.boxDialogContainer);
    renderAll();
    showToast(`箱 "${id}" を${state.editingBoxId ? '更新' : '登録'}しました`);
  }

  function openLidDialog(lidId) {
    state.editingLidId = lidId || null;
    state.formDirty.lid = false;
    if (lidId && state.draft.lids[lidId]) {
      const lid = state.draft.lids[lidId];
      el.lidFormTitle.textContent = `蓋仕様の編集 (${lid.id})`;
      el.lidModalSubtitle.textContent = '寸法、嵌め方等のパラメータを変更します';
      el.lidSubmitLabel.textContent = '更新して保存';
      el.lidId.value = lid.id || '';
      el.lidName.value = lid.name || '';
      el.lidType.value = lid.type || 'TP';
      el.lidLength.value = lid.length ?? '';
      el.lidWidth.value = lid.width ?? '';
      el.lidThickness.value = lid.thickness ?? '';
      el.lidFitType.value = lid.fit_type || '外嵌め';
      el.lidColor.value = lid.color || '';
      el.lidDescription.value = lid.description || '';
    } else {
      el.lidFormTitle.textContent = '新しい蓋を登録';
      el.lidModalSubtitle.textContent = '新しい蓋仕様をデータベースに追加します';
      el.lidSubmitLabel.textContent = '登録する';
      el.lidForm.reset();
      el.lidType.value = 'TP';
      el.lidFitType.value = '外嵌め';
      el.lidThickness.value = '15';
    }
    openOverlay(el.lidDialog, el.lidDialogContainer);
    refreshIcons();
  }

  function closeLidDialog() {
    state.formDirty.lid = false;
    state.editingLidId = null;
    closeOverlay(el.lidDialog, el.lidDialogContainer);
    updateDirtyIndicator();
  }

  function countNoneTypeLidsWithMutation(oldId, next) {
    const tmp = clone(state.draft.lids);
    if (oldId && oldId !== next.id) delete tmp[oldId];
    tmp[next.id] = next;
    return Object.values(tmp).filter(lid => lid.type === 'NONE').length;
  }

  function submitLidForm(event) {
    event.preventDefault();
    if (!guardEditable()) return;
    const id = el.lidId.value.trim();
    const name = el.lidName.value.trim();
    if (!id || !name) return alert('蓋IDと蓋名称は必須です');
    const length = asNumber(el.lidLength.value, NaN);
    const width = asNumber(el.lidWidth.value, NaN);
    const thickness = asNumber(el.lidThickness.value, NaN);
    if ([length, width, thickness].some(v => !Number.isFinite(v))) return alert('必須数値を入力してください');
    if (length < width) return alert('長さ L は幅 W 以上にしてください');
    if (!state.editingLidId && state.draft.lids[id]) return alert(`蓋ID "${id}" は既に存在します`);

    const oldId = state.editingLidId;
    if (oldId && id !== oldId) {
      if (!state.lidReferencesLoaded) return alert('蓋参照を読み込めないためID変更をブロックしました');
      const refs = state.lidReferences[oldId] || [];
      if (refs.length > 0) return alert(`蓋 "${oldId}" はテストケース参照があるためID変更できません`);
    }

    const prev = oldId ? state.draft.lids[oldId] : null;
    const existing = prev ? clone(prev) : {};
    const next = Object.assign(existing, {
      id,
      name,
      type: el.lidType.value,
      length,
      width,
      thickness,
      fit_type: el.lidFitType.value,
      color: el.lidColor.value.trim(),
      description: el.lidDescription.value.trim(),
    });
    if (countNoneTypeLidsWithMutation(oldId, next) < 1) return alert('type=NONE の蓋を最低1件残してください');

    if (oldId && id !== oldId) {
      delete state.draft.lids[oldId];
      Object.values(state.draft.boxes).forEach(box => {
        if (!Array.isArray(box.compatible_lids)) return;
        box.compatible_lids = Array.from(new Set(box.compatible_lids.map(lidId => lidId === oldId ? id : lidId)));
      });
      state.boxLidSyncTouched = true;
    }
    state.draft.lids[id] = next;
    state.formDirty.lid = false;
    closeOverlay(el.lidDialog, el.lidDialogContainer);
    renderAll();
    showToast(`蓋 "${id}" を${oldId ? '更新' : '登録'}しました`);
  }

  function deleteLid(lidId) {
    if (!state.lidReferencesLoaded) return alert('蓋参照を取得できないため削除をブロックしました');
    const refs = state.lidReferences[lidId] || [];
    if (refs.length > 0) return alert(`蓋 "${lidId}" はテストケース参照があるため削除できません`);
    const lid = state.draft.lids[lidId];
    if (!lid) return;
    const noneCount = Object.values(state.draft.lids).filter(item => item.type === 'NONE').length;
    if (lid.type === 'NONE' && noneCount <= 1) return alert('最後の NONE 蓋は削除できません');
    if (!confirm(`蓋 "${lidId}" を削除します。互換蓋参照も更新します。よろしいですか？`)) return;
    delete state.draft.lids[lidId];
    Object.values(state.draft.boxes).forEach(box => {
      if (Array.isArray(box.compatible_lids) && box.compatible_lids.includes(lidId)) {
        box.compatible_lids = box.compatible_lids.filter(id => id !== lidId);
        state.boxLidSyncTouched = true;
      }
    });
    renderAll();
  }

  function getApprovedBoxes() {
    const approved = {};
    Object.entries(state.draft.boxes).forEach(([id, box]) => {
      if (state.approval[id] !== false) approved[id] = box;
    });
    return approved;
  }

  function guardBoxRemoval(ids, action) {
    if (!state.boxReferencesLoaded) {
      alert(`箱参照を取得できないため${action}できません。再読み込みしてください。`);
      return false;
    }
    const used = ids.filter(id => (state.boxReferences[id] || []).length > 0);
    if (used.length === 0) return true;
    const details = used.map(id => `箱 "${id}": ${state.boxReferences[id].join(', ')}`);
    alert(`テストケースで使用中のため${action}できません。\n${details.join('\n')}`);
    return false;
  }

  function deleteBox(id) {
    if (!guardEditable() || !guardBoxRemoval([id], '削除')) return;
    if (!confirm(`型番 "${id}" をデータベースから削除しますか？`)) return;
    delete state.draft.boxes[id];
    delete state.approval[id];
    renderAll();
  }

  function setBoxApproval(id, approved) {
    if (!approved && !guardBoxRemoval([id], '採用解除')) return;
    state.approval[id] = approved;
  }

  function getApprovedJSON(pretty) {
    return JSON.stringify(getApprovedBoxes(), null, pretty ? 2 : 0);
  }

  function lidDependencyForBoxSave(approvedBoxes) {
    const persistedLidIds = new Set(Object.keys(state.persisted.lids));
    const missingInPersisted = new Set();
    Object.values(approvedBoxes).forEach(box => {
      (box.compatible_lids || []).forEach(lidId => {
        if (!persistedLidIds.has(lidId)) missingInPersisted.add(lidId);
      });
    });
    const dirty = computeDirty();
    return { needJointSave: missingInPersisted.size > 0, missingIds: Array.from(missingInPersisted), lidsDirty: dirty.lidsDirty };
  }

  function needsJointSaveFromLidSave() {
    const dirty = computeDirty();
    if (!dirty.lidsDirty) return false;
    if (state.boxLidSyncTouched) return true;
    const approved = getApprovedBoxes();
    const persistedApproved = {};
    Object.entries(state.persisted.boxes).forEach(([id, box]) => {
      if (state.approval[id] !== false) persistedApproved[id] = box;
    });
    return JSON.stringify(approved) !== JSON.stringify(persistedApproved);
  }

  async function saveDatasets(payload) {
    if (payload.boxes) {
      const removed = Object.keys(state.persisted.boxes).filter(id => !Object.prototype.hasOwnProperty.call(payload.boxes, id));
      if (!guardBoxRemoval(removed, '保存対象から除外')) return;
    }
    setSaving(true);
    try {
      const response = await fetch('/api/databases/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        let msg = `HTTP ${response.status}`;
        try {
          const err = await response.json();
          if (err && err.message) msg = err.message;
        } catch (_ignored) {}
        throw new Error(msg);
      }
      const result = await response.json();
      if (!result || result.status !== 'ok') throw new Error((result && result.message) || '保存に失敗しました');
      if (payload.boxes) state.persisted.boxes = clone(payload.boxes);
      if (payload.lids) state.persisted.lids = clone(payload.lids);
      if (payload.boxes && !payload.lids) {
        Object.keys(state.approval).forEach(id => {
          if (!Object.prototype.hasOwnProperty.call(payload.boxes, id)) state.approval[id] = false;
        });
      }
      if (payload.lids) state.boxLidSyncTouched = false;
      renderAll();
      setFeedback('success', '保存が完了しました。');
      showToast('保存が完了しました');
    } catch (error) {
      const detail = `保存に失敗しました: ${error.message}`;
      setFeedback('warning', detail);
      el.boxStatus.textContent = detail;
      el.lidStatus.textContent = detail;
      alert(detail);
    } finally {
      setSaving(false);
      renderAll();
    }
  }

  async function saveBoxes() {
    if (!guardEditable()) return;
    const approvedBoxes = getApprovedBoxes();
    const dep = lidDependencyForBoxSave(approvedBoxes);
    if (dep.needJointSave || (dep.lidsDirty && state.boxLidSyncTouched)) {
      const msg = [
        '箱保存には未保存の蓋変更を同時保存する必要があります。',
        dep.needJointSave
          ? `理由: 承認済み箱が参照する蓋ID [${dep.missingIds.join(', ')}] は、現行保存済み lid_db に存在しません。`
          : '理由: 蓋の削除/改名に伴う互換蓋同期が未保存です。',
        '',
        `同時保存対象:`,
        `- 箱DB: 現在の承認済み ${Object.keys(approvedBoxes).length} 件（不採用は除外）`,
        `- 蓋DB: 現在のドラフト ${Object.keys(state.draft.lids).length} 件`,
        '',
        '未保存の箱編集・不採用設定もこの保存に含まれます。続行しますか？',
      ].join('\n');
      if (!confirm(msg)) return;
      return saveDatasets({ boxes: approvedBoxes, lids: state.draft.lids });
    }
    return saveDatasets({ boxes: approvedBoxes });
  }

  async function saveLids() {
    if (!guardEditable()) return;
    if (Object.values(state.draft.lids).filter(lid => lid.type === 'NONE').length < 1) return alert('type=NONE の蓋が1件以上必要です');
    if (needsJointSaveFromLidSave()) {
      const approvedBoxes = getApprovedBoxes();
      const msg = [
        '蓋保存に伴い箱DBの整合更新も必要なため、箱DBも同時保存します。',
        '',
        `同時保存対象:`,
        `- 蓋DB: 現在のドラフト ${Object.keys(state.draft.lids).length} 件`,
        `- 箱DB: 承認済み ${Object.keys(approvedBoxes).length} 件（不採用は除外）`,
        '',
        '他の未保存箱編集・不採用設定も含めて保存します。続行しますか？',
      ].join('\n');
      if (!confirm(msg)) return;
      return saveDatasets({ boxes: approvedBoxes, lids: state.draft.lids });
    }
    return saveDatasets({ lids: state.draft.lids });
  }

  function switchTab(tabName) {
    state.activeTab = tabName;
    const isBoxes = tabName === 'boxes';
    el.panelBoxes.classList.toggle('hidden', !isBoxes);
    el.panelLids.classList.toggle('hidden', isBoxes);
    el.tabBoxes.className = isBoxes ? 'px-3 py-1.5 rounded-md bg-indigo-600 text-white' : 'px-3 py-1.5 rounded-md bg-slate-100 text-slate-700 hover:bg-slate-200';
    el.tabLids.className = isBoxes ? 'px-3 py-1.5 rounded-md bg-slate-100 text-slate-700 hover:bg-slate-200' : 'px-3 py-1.5 rounded-md bg-indigo-600 text-white';
    el.tabBoxes.setAttribute('aria-selected', isBoxes ? 'true' : 'false');
    el.tabLids.setAttribute('aria-selected', isBoxes ? 'false' : 'true');
    if (typeof location !== 'undefined' && typeof history !== 'undefined') {
      if (location.hash !== `#${tabName}`) history.replaceState(null, '', `#${tabName}`);
    }
  }

  function applyHashTab() {
    const hash = (typeof location !== 'undefined' ? (location.hash || '') : '').replace('#', '');
    switchTab(hash === 'lids' ? 'lids' : 'boxes');
  }

  function guardEditable() {
    if (!state.loaded) {
      alert('初期読み込み失敗中は編集できません。再試行してください。');
      return false;
    }
    if (state.saving) {
      alert('保存中は編集できません。完了までお待ちください。');
      return false;
    }
    return true;
  }

  function bindEvents() {
    el.retryLoad.addEventListener('click', loadAll);
    el.tabBoxes.addEventListener('click', () => switchTab('boxes'));
    el.tabLids.addEventListener('click', () => switchTab('lids'));
    el.boxSearch.addEventListener('input', () => {
      state.boxSearch = el.boxSearch.value;
      renderBoxes();
      refreshIcons();
    });
    if (el.lidSearch) {
      el.lidSearch.addEventListener('input', () => {
        state.lidSearch = el.lidSearch.value;
        renderLids();
        refreshIcons();
      });
    }
    qsa('.filter-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        if (!guardEditable()) return;
        state.boxFilter = btn.getAttribute('data-filter');
        qsa('.filter-tab').forEach(tab => {
          tab.classList.remove('bg-white', 'text-slate-900', 'shadow-sm');
          tab.classList.add('text-slate-600');
        });
        btn.classList.add('bg-white', 'text-slate-900', 'shadow-sm');
        btn.classList.remove('text-slate-600');
        renderBoxes();
        refreshIcons();
      });
    });
    el.selectAll.addEventListener('click', () => {
      if (!guardEditable()) return;
      Object.keys(state.draft.boxes).forEach(id => { state.approval[id] = true; });
      renderAll();
    });
    el.deselectAll.addEventListener('click', () => {
      if (!guardEditable()) return;
      if (!guardBoxRemoval(Object.keys(state.draft.boxes), '採用解除')) return;
      Object.keys(state.draft.boxes).forEach(id => { state.approval[id] = false; });
      renderAll();
    });
    el.selectTpOnly.addEventListener('click', () => {
      if (!guardEditable()) return;
      const excluded = Object.keys(state.draft.boxes).filter(id => state.draft.boxes[id].type !== 'TP');
      if (!guardBoxRemoval(excluded, '採用解除')) return;
      Object.entries(state.draft.boxes).forEach(([id, box]) => { state.approval[id] = box.type === 'TP'; });
      renderAll();
    });
    el.copyJson.addEventListener('click', async () => {
      if (!guardEditable()) return;
      try {
        if (!navigator || !navigator.clipboard || !navigator.clipboard.writeText) throw new Error('clipboard API が利用できません');
        await navigator.clipboard.writeText(getApprovedJSON(true));
        showToast('承認済みJSONをクリップボードにコピーしました');
      } catch (error) {
        alert(`JSONコピーに失敗しました: ${error.message}`);
      }
    });
    el.downloadJson.addEventListener('click', () => {
      if (!guardEditable()) return;
      const blob = new Blob([getApprovedJSON(true)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'box_db.json';
      if (document.body && document.body.appendChild) {
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } else {
        a.click();
      }
      URL.revokeObjectURL(url);
      showToast('承認済み box_db.json をダウンロードしました');
    });
    el.reloadAll.addEventListener('click', async () => {
      if (!guardEditable()) return;
      if (hasUnsavedChanges()) {
        const ok = confirm('箱・蓋の未保存の追加/編集/採用状態/フォーム入力をすべて破棄して再読み込みします。よろしいですか？');
        if (!ok) return;
      }
      closeBoxDialog();
      closeLidDialog();
      await loadAll();
      setFeedback('info', '箱DB・蓋DBをサーバーの最新状態に再読み込みしました。');
    });
    el.boxAdd.addEventListener('click', () => openBoxDialog());
    el.lidAdd.addEventListener('click', () => openLidDialog());
    el.boxSave.addEventListener('click', saveBoxes);
    el.lidSave.addEventListener('click', saveLids);
    el.boxClose.addEventListener('click', closeBoxDialog);
    el.boxCancel.addEventListener('click', closeBoxDialog);
    el.lidClose.addEventListener('click', closeLidDialog);
    el.lidCancel.addEventListener('click', closeLidDialog);
    el.boxDialog.addEventListener('click', (event) => {
      if (event.target === el.boxDialog) closeBoxDialog();
    });
    el.lidDialog.addEventListener('click', (event) => {
      if (event.target === el.lidDialog) closeLidDialog();
    });
    el.boxForm.addEventListener('submit', submitBoxForm);
    el.lidForm.addEventListener('submit', submitLidForm);
    [el.boxId, el.boxName, el.boxType, el.boxModule, el.boxFitting, el.boxLength, el.boxWidth, el.boxHeight, el.boxRib, el.boxDescription].forEach(input => {
      input.addEventListener('input', () => {
        state.formDirty.box = true;
        updateDirtyIndicator();
      });
    });
    [el.lidId, el.lidName, el.lidType, el.lidColor, el.lidFitType, el.lidLength, el.lidWidth, el.lidThickness, el.lidDescription].forEach(input => {
      input.addEventListener('input', () => {
        state.formDirty.lid = true;
        updateDirtyIndicator();
      });
    });
    if (typeof window !== 'undefined') {
      window.addEventListener('hashchange', applyHashTab);
      window.addEventListener('beforeunload', event => {
        if (!hasUnsavedChanges()) return;
        event.preventDefault();
        event.returnValue = '未保存の変更があります。';
      });
    }
  }

  bindEvents();
  applyHashTab();
  loadAll();
  refreshIcons();

  window.__dbViewer = {
    state,
    loadAll,
    switchTab,
    saveBoxes,
    saveLids,
    computeDirty,
    getApprovedBoxes,
    lidDependencyForBoxSave,
    submitBoxForm,
    submitLidForm,
    deleteLid,
    deleteBox,
    setBoxApproval,
    openBoxDialog,
    closeBoxDialog,
    openLidDialog,
    closeLidDialog,
  };
})();
