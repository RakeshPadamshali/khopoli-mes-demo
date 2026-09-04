/* When a Khopoli page loads inside index.html (an iframe tab), render content-only (hide its own header + sidebar)
   and route in-content links to the host's tabs. Standalone: leave the page untouched. */
(function () {
  if (window.self === window.top) return;
  document.documentElement.className += ' embedded';
  var s = document.createElement('style');
  s.textContent = '.embedded .bm-header,.embedded .bm-sidebar{display:none!important}' +
                  '.embedded .bm-layout{height:100vh!important}' +
                  '.embedded .bm-content{padding-top:12px}';
  (document.head || document.documentElement).appendChild(s);
  var MAP = {
    'home.html': 'home', 'orders.html': 'orders', 'planning.html': 'planning', 'allocation.html': 'allocation',
    'execution.html': 'execution', 'packing.html': 'packing', 'quality.html': 'quality', 'genealogy.html': 'genealogy',
    'integration.html': 'integration', 'support.html': 'support'
  };
  document.addEventListener('click', function (e) {
    var a = e.target.closest ? e.target.closest('a[href]') : null;
    if (!a) return;
    var href = (a.getAttribute('href') || '').split('#')[0].split('?')[0], hash = (a.getAttribute('href') || '').split('#')[1] || '';
    var id = MAP[href];
    if (id) { try { if (window.parent && window.parent.KHPHost) { e.preventDefault(); window.parent.KHPHost.open(id, hash); } } catch (err) {} }
  }, true);
})();
