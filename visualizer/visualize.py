#!/usr/bin/env python3
"""
荷姿可視化ジェネレータ (visualize.py)
パレタイズ結果JSONを読み込み、WebGL不要・完全動作保証の
Canvas 2D/3Dハイブリッド可視化スタンドアロンHTMLファイルを生成します。
"""

import os
import sys
import json
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

def generate_html(result_data: dict, output_html_path: str):
    result_json_str = json.dumps(result_data, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>パレタイズ荷姿ビューワ - {result_data.get('test_name', 'Palletize Viewer')}</title>
  <!-- Tailwind CSS CDN -->
  <script src="https://cdn.tailwindcss.com"></script>
  <!-- Lucide Icons -->
  <script src="https://unpkg.com/lucide@latest"></script>
  <style>
    body {{ margin: 0; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background-color: #0f172a; }}
    #viewport-container {{ width: 100vw; height: 100vh; position: absolute; top: 0; left: 0; z-index: 0; }}
    canvas {{ display: block; width: 100%; height: 100%; }}
    .custom-scrollbar::-webkit-scrollbar {{ width: 6px; }}
    .custom-scrollbar::-webkit-scrollbar-track {{ background: rgba(30, 41, 59, 0.5); }}
    .custom-scrollbar::-webkit-scrollbar-thumb {{ background: #475569; border-radius: 3px; }}
  </style>
</head>
<body class="bg-slate-900 text-slate-100 select-none overflow-hidden">

  <!-- Viewport Container -->
  <div id="viewport-container">
    <canvas id="main-canvas"></canvas>
  </div>

  <!-- Top Navigation / Info Bar -->
  <header class="absolute top-4 left-4 right-4 z-20 flex flex-col md:flex-row items-start md:items-center justify-between gap-3 pointer-events-none">
    <div class="bg-slate-900/90 backdrop-blur-md border border-slate-700/80 px-4 py-3 rounded-2xl shadow-2xl pointer-events-auto flex items-center gap-3">
      <div class="p-2 bg-indigo-600 text-white rounded-xl shadow">
        <i data-lucide="layers" class="w-5 h-5"></i>
      </div>
      <div>
        <div class="flex items-center gap-2">
          <h1 class="text-sm font-bold text-white">{result_data.get('test_name', 'Palletize Result')}</h1>
          <span id="badge-valid" class="text-[10px] px-2 py-0.5 rounded-full font-black uppercase tracking-wider"></span>
        </div>
        <p class="text-[11px] text-slate-400 mt-0.5">荷姿シミュレーション ＆ 積み順（Step-by-Step）可視化</p>
      </div>
    </div>

    <!-- Summary Metrics Badges -->
    <div class="bg-slate-900/90 backdrop-blur-md border border-slate-700/80 px-4 py-2.5 rounded-2xl shadow-2xl pointer-events-auto flex items-center gap-4 text-xs">
      <div>
        <span class="text-[10px] text-slate-400 block font-medium">配置箱数</span>
        <span class="font-bold font-mono text-white text-sm" id="metric-boxes">0 箱</span>
      </div>
      <div class="w-px h-6 bg-slate-700"></div>
      <div>
        <span class="text-[10px] text-slate-400 block font-medium">段数</span>
        <span class="font-bold font-mono text-white text-sm" id="metric-layers">0 段</span>
      </div>
      <div class="w-px h-6 bg-slate-700"></div>
      <div>
        <span class="text-[10px] text-slate-400 block font-medium">荷姿寸法 (X×Y×Z)</span>
        <span class="font-bold font-mono text-indigo-300 text-xs" id="metric-dims">0 × 0 × 0 mm</span>
      </div>
      <div class="w-px h-6 bg-slate-700"></div>
      <div>
        <span class="text-[10px] text-slate-400 block font-medium">体積充填率</span>
        <span class="font-bold font-mono text-emerald-400 text-sm" id="metric-vol">0 %</span>
      </div>
    </div>
  </header>

  <!-- Left Camera & View Mode Controls -->
  <aside class="absolute left-4 top-28 z-20 flex flex-col gap-2 pointer-events-auto">
    <div class="bg-slate-900/90 backdrop-blur-md border border-slate-700/80 p-1.5 rounded-xl shadow-2xl flex flex-col gap-1 text-xs">
      <div class="text-[10px] font-bold text-slate-400 px-2 py-1 uppercase tracking-wider">視点切替</div>
      <button class="view-btn px-2.5 py-1.5 rounded-lg transition flex items-center gap-1.5 bg-indigo-600 text-white font-bold cursor-pointer" data-view="iso" title="等角俯瞰">
        <i data-lucide="compass" class="w-3.5 h-3.5"></i> 俯瞰 (ISO 3D)
      </button>
      <button class="view-btn px-2.5 py-1.5 text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg transition flex items-center gap-1.5 cursor-pointer" data-view="top" title="上面図（平面配置）">
        <i data-lucide="arrow-down" class="w-3.5 h-3.5 text-blue-400"></i> 上面 (Top 2D)
      </button>
      <button class="view-btn px-2.5 py-1.5 text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg transition flex items-center gap-1.5 cursor-pointer" data-view="front" title="正面図（長辺立面）">
        <i data-lucide="eye" class="w-3.5 h-3.5 text-emerald-400"></i> 正面 (Front 2D)
      </button>
      <button class="view-btn px-2.5 py-1.5 text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg transition flex items-center gap-1.5 cursor-pointer" data-view="side" title="側面図（短辺立面）">
        <i data-lucide="move-right" class="w-3.5 h-3.5 text-amber-400"></i> 側面 (Side 2D)
      </button>
    </div>

    <!-- Wireframe & Guides Toggle -->
    <div class="bg-slate-900/90 backdrop-blur-md border border-slate-700/80 p-2 rounded-xl shadow-2xl flex flex-col gap-1 text-[11px]">
      <label class="flex items-center gap-2 cursor-pointer text-slate-300 hover:text-white">
        <input type="checkbox" id="toggle-guides" checked class="rounded border-slate-700 bg-slate-800 text-indigo-600 focus:ring-0 cursor-pointer">
        <span>制約ガイド枠</span>
      </label>
      <label class="flex items-center gap-2 cursor-pointer text-slate-300 hover:text-white">
        <input type="checkbox" id="toggle-labels" checked class="rounded border-slate-700 bg-slate-800 text-indigo-600 focus:ring-0 cursor-pointer">
        <span>積み順・型番</span>
      </label>
    </div>

    <!-- Zoom & Reset -->
    <div class="bg-slate-900/90 backdrop-blur-md border border-slate-700/80 p-1.5 rounded-xl shadow-2xl flex items-center justify-around text-xs">
      <button id="btn-zoom-in" class="p-1.5 text-slate-300 hover:text-white hover:bg-slate-800 rounded transition cursor-pointer" title="拡大">
        <i data-lucide="zoom-in" class="w-4 h-4"></i>
      </button>
      <button id="btn-zoom-out" class="p-1.5 text-slate-300 hover:text-white hover:bg-slate-800 rounded transition cursor-pointer" title="縮小">
        <i data-lucide="zoom-out" class="w-4 h-4"></i>
      </button>
      <button id="btn-view-reset" class="p-1.5 text-slate-300 hover:text-white hover:bg-slate-800 rounded transition cursor-pointer" title="視点リセット">
        <i data-lucide="maximize" class="w-4 h-4"></i>
      </button>
    </div>
  </aside>

  <!-- Right Detail Inspector Panel -->
  <aside id="inspector-panel" class="absolute right-4 top-24 bottom-28 w-72 bg-slate-900/90 backdrop-blur-md border border-slate-700/80 rounded-2xl shadow-2xl p-4 z-20 pointer-events-auto flex flex-col gap-3 hidden md:flex">
    <div class="flex items-center justify-between border-b border-slate-800 pb-2">
      <h2 class="text-xs font-bold text-slate-300 flex items-center gap-1.5">
        <i data-lucide="info" class="w-3.5 h-3.5 text-indigo-400"></i> 箱詳細インスペクタ
      </h2>
      <span class="text-[10px] text-slate-500">箱をクリック</span>
    </div>
    
    <div id="inspector-content" class="flex-1 overflow-y-auto space-y-3 text-xs text-slate-400 custom-scrollbar">
      <p class="text-center py-10 text-slate-500">荷姿の箱をクリックすると、詳細パラメータが表示されます。</p>
    </div>

    <!-- Color Legend -->
    <div class="border-t border-slate-800 pt-2">
      <p class="text-[10px] font-bold text-slate-400 mb-1.5 uppercase tracking-wider">箱種別カラー凡例</p>
      <div id="legend-list" class="space-y-1 max-h-28 overflow-y-auto pr-1 text-[11px] custom-scrollbar"></div>
    </div>
  </aside>

  <!-- Bottom Timeline & Step Player Controls -->
  <footer class="absolute bottom-4 left-4 right-4 z-20 pointer-events-none flex justify-center">
    <div class="bg-slate-900/90 backdrop-blur-md border border-slate-700/80 px-6 py-3.5 rounded-2xl shadow-2xl pointer-events-auto w-full max-w-3xl flex flex-col gap-2.5">
      <div class="flex items-center justify-between gap-4">
        
        <div class="flex items-center gap-2">
          <button id="btn-play-prev" class="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition cursor-pointer" title="1ステップ前へ">
            <i data-lucide="skip-back" class="w-4 h-4"></i>
          </button>
          <button id="btn-play-toggle" class="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition font-bold text-xs flex items-center gap-1.5 shadow cursor-pointer" title="再生/一時停止">
            <i data-lucide="play" class="w-4 h-4" id="play-icon"></i>
            <span id="play-label">再生</span>
          </button>
          <button id="btn-play-next" class="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition cursor-pointer" title="1ステップ次へ">
            <i data-lucide="skip-forward" class="w-4 h-4"></i>
          </button>
          <button id="btn-play-reset" class="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white rounded-lg transition cursor-pointer" title="最初に戻す">
            <i data-lucide="rotate-ccw" class="w-4 h-4"></i>
          </button>
        </div>

        <div class="text-xs font-mono">
          <span class="text-slate-400 font-sans">積み込み手順: </span>
          <span id="step-current" class="text-indigo-400 font-bold text-sm">0</span>
          <span class="text-slate-500"> / </span>
          <span id="step-total" class="text-slate-300">0</span>
        </div>

        <div class="flex items-center gap-1 text-[11px] bg-slate-800/80 p-1 rounded-lg">
          <button class="speed-btn px-2 py-0.5 rounded text-slate-400 hover:text-white cursor-pointer" data-speed="1000">0.5x</button>
          <button class="speed-btn px-2 py-0.5 rounded bg-slate-700 text-white font-bold cursor-pointer" data-speed="400">1x</button>
          <button class="speed-btn px-2 py-0.5 rounded text-slate-400 hover:text-white cursor-pointer" data-speed="150">3x</button>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <input type="range" id="step-slider" min="0" max="0" value="0" class="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-indigo-500">
      </div>
    </div>
  </footer>

  <!-- Embedded Data -->
  <script>
    const PALLETIZE_DATA = {result_json_str};
  </script>

  <!-- Universal 2D/3D Canvas Renderer Script -->
  <script>
    const COLOR_PALETTE = [
      {{ fill: '#4f46e5', top: '#6366f1', side: '#3730a3', stroke: '#818cf8' }},
      {{ fill: '#059669', top: '#10b981', side: '#065f46', stroke: '#34d399' }},
      {{ fill: '#d97706', top: '#f59e0b', side: '#92400e', stroke: '#fbbf24' }},
      {{ fill: '#dc2626', top: '#ef4444', side: '#991b1b', stroke: '#f87171' }},
      {{ fill: '#0284c7', top: '#0ea5e9', side: '#075985', stroke: '#38bdf8' }},
      {{ fill: '#7c3aed', top: '#8b5cf6', side: '#5b21b6', stroke: '#a78bfa' }},
      {{ fill: '#db2777', top: '#ec4899', side: '#9d174d', stroke: '#f472b6' }},
      {{ fill: '#0d9488', top: '#14b8a6', side: '#115e59', stroke: '#2dd4bf' }},
      {{ fill: '#ca8a04', top: '#eab308', side: '#854d0e', stroke: '#fde047' }},
      {{ fill: '#2563eb', top: '#3b82f6', side: '#1e40af', stroke: '#60a5fa' }}
    ];

    let canvas, ctx;
    let currentData = PALLETIZE_DATA;
    let boxColorMap = {{}};
    let viewMode = 'iso';
    let currentStep = 0;
    let isPlaying = false;
    let playInterval = null;
    let playSpeed = 400;

    let zoom = 0.55;
    let panX = 0, panY = 0;
    let angleX = 35 * Math.PI / 180;
    let angleZ = 45 * Math.PI / 180;
    let isDragging = false;
    let lastMouseX = 0, lastMouseY = 0;
    let selectedBoxOrder = null;

    let showGuides = true;
    let showLabels = true;

    function initRenderer() {{
      canvas = document.getElementById('main-canvas');
      ctx = canvas.getContext('2d');

      resizeCanvas();
      window.addEventListener('resize', resizeCanvas);

      setupInteractions();
      setupUIEvents();
      processData(PALLETIZE_DATA);

      requestAnimationFrame(renderLoop);
    }}

    function resizeCanvas() {{
      canvas.width = window.innerWidth * window.devicePixelRatio;
      canvas.height = window.innerHeight * window.devicePixelRatio;
      canvas.style.width = window.innerWidth + 'px';
      canvas.style.height = window.innerHeight + 'px';
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    }}

    function processData(data) {{
      boxColorMap = {{}};
      const boxes = data.boxes || [];
      const uniqueIds = Array.from(new Set(boxes.map(b => b.box_id)));
      uniqueIds.forEach((id, idx) => {{
        boxColorMap[id] = COLOR_PALETTE[idx % COLOR_PALETTE.length];
      }});

      updateUIMetrics(data);

      currentStep = boxes.length;
      document.getElementById('step-total').textContent = boxes.length;
      document.getElementById('step-slider').max = boxes.length;
      document.getElementById('step-slider').value = currentStep;
      document.getElementById('step-current').textContent = currentStep;

      const legendList = document.getElementById('legend-list');
      legendList.innerHTML = '';
      Object.keys(boxColorMap).forEach(id => {{
        const c = boxColorMap[id];
        const item = document.createElement('div');
        item.className = 'flex items-center gap-2 text-slate-300';
        item.innerHTML = `
          <span class="w-3 h-3 rounded-md shadow inline-block" style="background-color: ${{c.fill}}; border: 1px solid ${{c.stroke}}"></span>
          <span class="font-mono font-medium">${{id}}</span>
        `;
        legendList.appendChild(item);
      }});

      selectedBoxOrder = null;
      resetViewTransform();
      lucide.createIcons();
    }}

    function updateUIMetrics(data) {{
      const summary = data.summary || {{}};
      const bbox = summary.bounding_box || {{}};
      const totalBoxes = data.boxes ? data.boxes.length : 0;

      const validBadge = document.getElementById('badge-valid');
      if (summary.is_valid) {{
        validBadge.textContent = "PASS 制約合格";
        validBadge.className = "text-[10px] px-2.5 py-0.5 rounded-full font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30";
      }} else {{
        validBadge.textContent = "FAIL 制約違反あり";
        validBadge.className = "text-[10px] px-2.5 py-0.5 rounded-full font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30";
      }}

      document.getElementById('metric-boxes').textContent = `${{totalBoxes}} 箱`;
      document.getElementById('metric-layers').textContent = `${{summary.total_layers || 0}} 段`;
      document.getElementById('metric-dims').textContent = `${{bbox.x_span || 0}} × ${{bbox.y_span || 0}} × ${{bbox.max_z || 0}} mm`;
      document.getElementById('metric-vol').textContent = `${{summary.volume_efficiency_percent || 0}} %`;
    }}

    function resetViewTransform() {{
      const w = window.innerWidth;
      const h = window.innerHeight;
      panX = w / 2;
      panY = h / 2 + 80;
      if (viewMode === 'iso') {{
        zoom = Math.min(w, h) / 2400;
        panY = h / 2 + 100;
      }} else if (viewMode === 'top') {{
        zoom = Math.min(w, h) / 1800;
        panY = h / 2;
      }} else {{
        zoom = Math.min(w, h) / 1800;
        panY = h / 2 + 100;
      }}
    }}

    function project3D(x, y, z) {{
      const pW = currentData?.pallet?.width || 1200;
      const pL = currentData?.pallet?.length || 1000;
      const cx = x - pW / 2;
      const cy = y - pL / 2;
      const cz = z;

      if (viewMode === 'iso') {{
        const rotX = cx * Math.cos(angleZ) - cy * Math.sin(angleZ);
        const rotY = cx * Math.sin(angleZ) + cy * Math.cos(angleZ);
        const screenX = rotX * zoom + panX;
        const screenY = (rotY * Math.sin(angleX) - cz * Math.cos(angleX)) * zoom + panY;
        const depth = rotY * Math.cos(angleX) + cz * Math.sin(angleX);
        return {{ x: screenX, y: screenY, depth: depth }};
      }} else if (viewMode === 'top') {{
        return {{ x: cx * zoom + panX, y: cy * zoom + panY, depth: cz }};
      }} else if (viewMode === 'front') {{
        return {{ x: cx * zoom + panX, y: -cz * zoom + panY, depth: cy }};
      }} else if (viewMode === 'side') {{
        return {{ x: cy * zoom + panX, y: -cz * zoom + panY, depth: cx }};
      }}
      return {{ x: 0, y: 0, depth: 0 }};
    }}

    function renderLoop() {{
      const w = window.innerWidth;
      const h = window.innerHeight;

      ctx.clearRect(0, 0, w, h);

      const bgGrad = ctx.createRadialGradient(w/2, h/2, 100, w/2, h/2, w);
      bgGrad.addColorStop(0, '#1e293b');
      bgGrad.addColorStop(1, '#0f172a');
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, w, h);

      if (currentData) {{
        drawGridAndPallet();
        if (showGuides) drawGuides();
        drawBoxes();
      }}

      requestAnimationFrame(renderLoop);
    }}

    function drawGridAndPallet() {{
      const pW = currentData.pallet?.width || 1200;
      const pL = currentData.pallet?.length || 1000;
      const pH = 144;

      ctx.strokeStyle = 'rgba(51, 65, 85, 0.4)';
      ctx.lineWidth = 1;
      const gridSpan = 2000;
      for (let g = -gridSpan; g <= gridSpan + pW; g += 400) {{
        const p1 = project3D(g, -gridSpan, -pH);
        const p2 = project3D(g, gridSpan + pL, -pH);
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();

        const p3 = project3D(-gridSpan, g, -pH);
        const p4 = project3D(gridSpan + pW, g, -pH);
        ctx.beginPath();
        ctx.moveTo(p3.x, p3.y);
        ctx.lineTo(p4.x, p4.y);
        ctx.stroke();
      }}

      drawSolidBox(0, 0, -pH, pW, pL, pH, {{
        fill: '#1e293b', top: '#334155', side: '#0f172a', stroke: '#475569'
      }}, false);
    }}

    function drawGuides() {{
      const pW = currentData.pallet?.width || 1200;
      const pL = currentData.pallet?.length || 1000;
      const maxH = currentData.pallet?.max_height || 1200;
      const maxSpanX = currentData.pallet?.max_x_span || 1360;
      const maxSpanY = currentData.pallet?.max_y_span || 1100;
      const ovhX = (maxSpanX - pW) / 2;
      const ovhY = (maxSpanY - pL) / 2;

      ctx.save();
      ctx.setLineDash([8, 6]);

      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 1.5;
      const hPts = [
        project3D(0, 0, maxH), project3D(pW, 0, maxH),
        project3D(pW, pL, maxH), project3D(0, pL, maxH)
      ];
      ctx.beginPath();
      ctx.moveTo(hPts[0].x, hPts[0].y);
      for (let i = 1; i < hPts.length; i++) ctx.lineTo(hPts[i].x, hPts[i].y);
      ctx.closePath();
      ctx.stroke();

      ctx.strokeStyle = '#f59e0b';
      ctx.lineWidth = 1.5;
      const ovhPts = [
        project3D(-ovhX, -ovhY, 0), project3D(pW + ovhX, -ovhY, 0),
        project3D(pW + ovhX, pL + ovhY, 0), project3D(-ovhX, pL + ovhY, 0)
      ];
      ctx.beginPath();
      ctx.moveTo(ovhPts[0].x, ovhPts[0].y);
      for (let i = 1; i < ovhPts.length; i++) ctx.lineTo(ovhPts[i].x, ovhPts[i].y);
      ctx.closePath();
      ctx.stroke();

      ctx.restore();
    }}

    function drawBoxes() {{
      const boxes = currentData.boxes || [];
      const visibleBoxes = boxes.slice(0, currentStep);

      const renderList = visibleBoxes.map(b => {{
        const cx = b.position.x + b.dimensions.width / 2;
        const cy = b.position.y + b.dimensions.length / 2;
        const cz = b.position.z + b.dimensions.height / 2;
        const pt = project3D(cx, cy, cz);
        return {{ box: b, depth: pt.depth, screenPt: pt }};
      }});

      renderList.sort((a, b) => a.depth - b.depth);

      renderList.forEach(item => {{
        const b = item.box;
        const colors = boxColorMap[b.box_id] || COLOR_PALETTE[0];
        const isSelected = (b.order === selectedBoxOrder);

        const customColors = isSelected ? {{
          fill: '#0284c7', top: '#38bdf8', side: '#0369a1', stroke: '#ffffff'
        }} : colors;

        drawSolidBox(
          b.position.x, b.position.y, b.position.z,
          b.dimensions.width, b.dimensions.length, b.dimensions.height,
          customColors,
          showLabels,
          `${{b.order}}: ${{b.box_id}}`
        );
      }});
    }}

    function drawSolidBox(x, y, z, w, l, h, colors, drawLabel = false, labelText = "") {{
      const p000 = project3D(x, y, z);
      const p100 = project3D(x + w, y, z);
      const p110 = project3D(x + w, y + l, z);
      const p010 = project3D(x, y + l, z);

      const p001 = project3D(x, y, z + h);
      const p101 = project3D(x + w, y, z + h);
      const p111 = project3D(x + w, y + l, z + h);
      const p011 = project3D(x, y + l, z + h);

      if (viewMode === 'iso') {{
        drawPolygon([p001, p101, p111, p011], colors.top, colors.stroke);
        drawPolygon([p000, p100, p101, p001], colors.fill, colors.stroke);
        drawPolygon([p100, p110, p111, p101], colors.side, colors.stroke);

        if (drawLabel && labelText) {{
          const lX = (p001.x + p101.x + p111.x + p011.x) / 4;
          const lY = (p001.y + p101.y + p111.y + p011.y) / 4;
          drawBadge(lX, lY, labelText);
        }}
      }} else if (viewMode === 'top') {{
        drawPolygon([p000, p100, p110, p010], colors.top, colors.stroke);
        if (drawLabel && labelText) {{
          drawBadge((p000.x + p110.x) / 2, (p000.y + p110.y) / 2, labelText);
        }}
      }} else if (viewMode === 'front') {{
        drawPolygon([p000, p100, p101, p001], colors.fill, colors.stroke);
        if (drawLabel && labelText) {{
          drawBadge((p000.x + p101.x) / 2, (p000.y + p101.y) / 2, labelText);
        }}
      }} else if (viewMode === 'side') {{
        drawPolygon([p000, p010, p011, p001], colors.side, colors.stroke);
        if (drawLabel && labelText) {{
          drawBadge((p000.x + p011.x) / 2, (p000.y + p011.y) / 2, labelText);
        }}
      }}
    }}

    function drawPolygon(points, fillColor, strokeColor) {{
      ctx.beginPath();
      ctx.moveTo(points[0].x, points[0].y);
      for (let i = 1; i < points.length; i++) ctx.lineTo(points[i].x, points[i].y);
      ctx.closePath();
      ctx.fillStyle = fillColor;
      ctx.fill();
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 1.2;
      ctx.stroke();
    }}

    function drawBadge(x, y, text) {{
      ctx.save();
      ctx.font = 'bold 10px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      const paddingX = 6, paddingY = 3;
      const metrics = ctx.measureText(text);
      const bw = metrics.width + paddingX * 2;
      const bh = 16;

      ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
      ctx.beginPath();
      ctx.roundRect(x - bw/2, y - bh/2, bw, bh, 4);
      ctx.fill();
      ctx.strokeStyle = '#818cf8';
      ctx.lineWidth = 1;
      ctx.stroke();

      ctx.fillStyle = '#ffffff';
      ctx.fillText(text, x, y);
      ctx.restore();
    }}

    function setupInteractions() {{
      window.addEventListener('mousedown', (e) => {{
        if (e.clientY < 80 || e.clientY > window.innerHeight - 100 || e.clientX < 140 || e.clientX > window.innerWidth - 300) return;
        isDragging = true;
        lastMouseX = e.clientX;
        lastMouseY = e.clientY;
      }});

      window.addEventListener('mousemove', (e) => {{
        if (!isDragging) return;
        const dx = e.clientX - lastMouseX;
        const dy = e.clientY - lastMouseY;

        if (e.buttons === 1) {{
          if (viewMode === 'iso') {{
            angleZ += dx * 0.006;
            angleX = Math.max(0.1, Math.min(Math.PI / 2 - 0.05, angleX - dy * 0.006));
          }} else {{
            panX += dx;
            panY += dy;
          }}
        }} else if (e.buttons === 2 || e.buttons === 4) {{
          panX += dx;
          panY += dy;
        }}

        lastMouseX = e.clientX;
        lastMouseY = e.clientY;
      }});

      window.addEventListener('mouseup', () => {{ isDragging = false; }});
      window.addEventListener('contextmenu', (e) => e.preventDefault());

      window.addEventListener('wheel', (e) => {{
        e.preventDefault();
        const factor = e.deltaY < 0 ? 1.1 : 0.9;
        zoom = Math.max(0.1, Math.min(3.0, zoom * factor));
      }}, {{ passive: false }});

      window.addEventListener('click', (e) => {{
        if (e.clientY < 80 || e.clientY > window.innerHeight - 100 || e.clientX < 140 || e.clientX > window.innerWidth - 300) return;
        handleBoxClick(e.clientX, e.clientY);
      }});
    }}

    function handleBoxClick(mouseX, mouseY) {{
      if (!currentData || !currentData.boxes) return;
      const visibleBoxes = currentData.boxes.slice(0, currentStep);

      for (let i = visibleBoxes.length - 1; i >= 0; i--) {{
        const b = visibleBoxes[i];
        const p1 = project3D(b.position.x, b.position.y, b.position.z);
        const p2 = project3D(b.position.x + b.dimensions.width, b.position.y + b.dimensions.length, b.position.z + b.dimensions.height);

        const minX = Math.min(p1.x, p2.x) - 20;
        const maxX = Math.max(p1.x, p2.x) + 20;
        const minY = Math.min(p1.y, p2.y) - 20;
        const maxY = Math.max(p1.y, p2.y) + 20;

        if (mouseX >= minX && mouseX <= maxX && mouseY >= minY && mouseY <= maxY) {{
          selectedBoxOrder = b.order;
          inspectBox(b);
          return;
        }}
      }}
    }}

    function inspectBox(b) {{
      const content = document.getElementById('inspector-content');
      content.innerHTML = `
        <div class="bg-slate-800/80 p-3 rounded-xl border border-slate-700 space-y-2">
          <div class="flex items-center justify-between">
            <span class="font-mono font-bold text-white text-sm">${{b.box_id}}</span>
            <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">Order #${{b.order}}</span>
          </div>
          <div class="grid grid-cols-2 gap-2 text-[11px] pt-1">
            <div><span class="text-slate-500">配置座標:</span><br><span class="font-mono text-slate-200">(${{b.position.x}}, ${{b.position.y}}, ${{b.position.z}})</span></div>
            <div><span class="text-slate-500">外寸寸法:</span><br><span class="font-mono text-slate-200">${{b.dimensions.width}}×${{b.dimensions.length}}×${{b.dimensions.height}}</span></div>
            <div><span class="text-slate-500">回転角:</span><br><span class="font-mono text-slate-200">${{b.rotation}}°</span></div>
            <div><span class="text-slate-500">勘合深さ:</span><br><span class="font-mono text-indigo-400 font-bold">${{b.fitting_depth}} mm</span></div>
          </div>
          ${{b.supported_by && b.supported_by.length > 0 ? `
            <div class="pt-2 border-t border-slate-700 text-[11px]">
              <span class="text-slate-500">下段支持箱 (Order):</span>
              <span class="font-mono text-emerald-400 font-bold ml-1">${{b.supported_by.join(', ')}}</span>
            </div>
          ` : '<div class="pt-1 text-[11px] text-slate-500">パレット直置き</div>'}}
        </div>
      `;
    }}

    function setupUIEvents() {{
      document.querySelectorAll('.view-btn').forEach(btn => {{
        btn.addEventListener('click', () => {{
          document.querySelectorAll('.view-btn').forEach(b => {{
            b.classList.remove('bg-indigo-600', 'text-white', 'font-bold');
            b.classList.add('text-slate-300');
          }});
          btn.classList.add('bg-indigo-600', 'text-white', 'font-bold');
          btn.classList.remove('text-slate-300');

          viewMode = btn.getAttribute('data-view');
          resetViewTransform();
        }});
      }});

      document.getElementById('btn-zoom-in').addEventListener('click', () => {{ zoom *= 1.2; }});
      document.getElementById('btn-zoom-out').addEventListener('click', () => {{ zoom *= 0.8; }});
      document.getElementById('btn-view-reset').addEventListener('click', resetViewTransform);

      document.getElementById('toggle-guides').addEventListener('change', (e) => {{ showGuides = e.target.checked; }});
      document.getElementById('toggle-labels').addEventListener('change', (e) => {{ showLabels = e.target.checked; }});

      document.getElementById('step-slider').addEventListener('input', (e) => {{
        if (isPlaying) togglePlay();
        setStep(parseInt(e.target.value));
      }});

      document.getElementById('btn-play-toggle').addEventListener('click', togglePlay);
      document.getElementById('btn-play-prev').addEventListener('click', () => {{
        if (isPlaying) togglePlay();
        setStep(currentStep - 1);
      }});
      document.getElementById('btn-play-next').addEventListener('click', () => {{
        if (isPlaying) togglePlay();
        setStep(currentStep + 1);
      }});
      document.getElementById('btn-play-reset').addEventListener('click', () => {{
        if (isPlaying) togglePlay();
        setStep(0);
      }});

      document.querySelectorAll('.speed-btn').forEach(btn => {{
        btn.addEventListener('click', () => {{
          document.querySelectorAll('.speed-btn').forEach(b => {{
            b.classList.remove('bg-slate-700', 'text-white', 'font-bold');
            b.classList.add('text-slate-400');
          }});
          btn.classList.add('bg-slate-700', 'text-white', 'font-bold');
          btn.classList.remove('text-slate-400');
          playSpeed = parseInt(btn.getAttribute('data-speed'));
          if (isPlaying) {{
            clearInterval(playInterval);
            playInterval = setInterval(() => {{
              const maxBoxes = currentData?.boxes?.length || 0;
              if (currentStep < maxBoxes) setStep(currentStep + 1);
              else togglePlay();
            }}, playSpeed);
          }}
        }});
      }});
    }}

    function setStep(step) {{
      const maxBoxes = currentData?.boxes?.length || 0;
      currentStep = Math.max(0, Math.min(step, maxBoxes));
      document.getElementById('step-current').textContent = currentStep;
      document.getElementById('step-slider').value = currentStep;
    }}

    function togglePlay() {{
      isPlaying = !isPlaying;
      const playIcon = document.getElementById('play-icon');
      const playLabel = document.getElementById('play-label');
      const maxBoxes = currentData?.boxes?.length || 0;

      if (isPlaying) {{
        playLabel.textContent = "停止";
        playIcon.setAttribute('data-lucide', 'pause');
        lucide.createIcons();

        if (currentStep >= maxBoxes) setStep(0);

        playInterval = setInterval(() => {{
          if (currentStep < maxBoxes) {{
            setStep(currentStep + 1);
          }} else {{
            togglePlay();
          }}
        }}, playSpeed);
      }} else {{
        playLabel.textContent = "再生";
        playIcon.setAttribute('data-lucide', 'play');
        lucide.createIcons();
        if (playInterval) clearInterval(playInterval);
      }}
    }}

    window.addEventListener('DOMContentLoaded', initRenderer);
  </script>
</body>
</html>
"""
    os.makedirs(os.path.dirname(os.path.abspath(output_html_path)), exist_ok=True)
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✨ 荷姿可視化HTMLを生成しました: {output_html_path}")

def main():
    parser = argparse.ArgumentParser(description="荷姿可視化ジェネレータ")
    parser.add_argument("result_json", help="パレタイズ結果JSONファイルのパス")
    parser.add_argument("--output", "-o", default=None, help="出力HTMLファイルパス")
    args = parser.parse_args()

    with open(args.result_json, "r", encoding="utf-8") as f:
        result_data = json.load(f)

    if args.output:
        out_path = args.output
    else:
        out_path = os.path.join(PROJECT_ROOT, "visualizer", "viewer.html")

    generate_html(result_data, out_path)

if __name__ == "__main__":
    main()
