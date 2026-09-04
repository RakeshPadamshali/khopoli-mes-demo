/* Injects the standalone header + sidebar into a Khopoli content page.
   Each page sets window.KHP_PAGE / KHP_TITLE / KHP_ICON before loading this. Hidden when embedded in index.html. */
(function () {
  var NAV = [
    ['Planning', [['home', 'Plant Dashboard', 'fa-gauge-high'], ['orders', 'Sales Orders & TDC', 'fa-file-invoice'], ['planning', 'Routes & Schedules', 'fa-route'], ['allocation', 'Material Allocator', 'fa-boxes-packing']]],
    ['Execution', [['execution', 'Shop-floor Execution', 'fa-industry'], ['packing', 'Slitting · Packing · Dispatch', 'fa-truck-ramp-box']]],
    ['Quality & Trace', [['quality', 'Quality & Defects', 'fa-microscope'], ['genealogy', 'Genealogy · Digital Thread', 'fa-diagram-project']]],
    ['Integration', [['integration', 'Integration Monitor', 'fa-tower-broadcast']]],
    ['Support', [['support', 'AI Support Data (S7)', 'fa-robot']]]
  ];
  var DECOR = [['Lines & Equipment', 'fa-gears'], ['Specs & TDC', 'fa-book'], ['Users & Roles', 'fa-user-shield']];
  var cur = window.KHP_PAGE || '';
  var layout = document.querySelector('.bm-layout');
  if (!layout) return;
  var h = document.createElement('header'); h.className = 'bm-header';
  h.innerHTML =
    '<div class="logo"><i class="fa-solid fa-layer-group"></i> JSW Steel Coated Products <span class="sub">Khopoli NextGen MES</span></div>' +
    '<div class="module-name"><i class="fa-solid ' + (window.KHP_ICON || 'fa-diagram-project') + '" style="margin-right:4px;color:var(--accent);"></i>' + (window.KHP_TITLE || 'One MES — Coated Products template') + '</div>' +
    '<div class="spacer"></div>' +
    '<div class="plant-switch"><button class="active"><i class="fa-solid fa-location-dot" style="margin-right:4px"></i>Khopoli</button><button>Vasind</button><button>Tarapur</button><button>Kalmeshwar</button></div>' +
    '<div class="right"><span class="asof"><i class="fa-regular fa-clock"></i> as of Tue 15 Sep 2026 10:30 · Shift A</span><button class="btn-reset" id="khp-reset" title="Reset the live-demo actions on every page"><i class="fa-solid fa-rotate-left"></i> Reset demo</button><div class="avatar">RP</div></div>';
  document.body.insertBefore(h, layout);
  var side = document.createElement('aside'); side.className = 'bm-sidebar';
  var html = '';
  NAV.forEach(function (sec) {
    html += '<div class="nav-label">' + sec[0] + '</div>';
    sec[1].forEach(function (it) { html += '<a href="' + it[0] + '.html" class="' + (it[0] === cur ? 'active' : '') + '"><i class="fa-solid ' + it[2] + '"></i>' + it[1] + '</a>'; });
  });
  html += '<div class="nav-label">Masters</div>';
  DECOR.forEach(function (d) { html += '<a class="decor"><i class="fa-solid ' + d[1] + '"></i>' + d[0] + '</a>'; });
  side.innerHTML = html;
  layout.insertBefore(side, layout.firstChild);
  var rb = document.getElementById('khp-reset');
  if (rb) rb.addEventListener('click', function () { if (window.KHPState) { KHPState.reset(); location.reload(); } });
})();
