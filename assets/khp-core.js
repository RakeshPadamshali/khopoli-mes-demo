/* Khopoli NextGen MES demo — shared runtime over window.KHP (data/khp-data.js).
   Lookups, genealogy traversal, date formatting, badges, a multi-day gantt renderer, a JSON pretty-printer,
   toasts, and the live-demo state overlay (localStorage) so an action on one page is visible on the others. */
(function () {
  var D = window.KHP; if (!D) { console.error('KHP data not loaded'); return; }
  var ASOF = new Date(D.meta.asOf), BASE = new Date(D.meta.baseDate);
  var WD = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'], MO = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function dt(x) { return x instanceof Date ? x : x ? new Date(x) : null; }

  // ---- lookups ----
  var by = {};
  function index(name, coll, key) { by[name] = {}; (D[coll] || []).forEach(function (r) { by[name][r[key || 'id']] = r; }); }
  index('materials', 'materials'); index('items', 'items'); index('orders', 'orders'); index('lines', 'lines'); index('equipment', 'equipment'); index('stages', 'stages');
  index('pos', 'productionOrders'); index('pdi', 'pdi'); index('pdo', 'pdo'); index('confs', 'confirmations'); index('defects', 'defects'); index('messages', 'messages');
  index('interfaces', 'interfaces'); index('incidents', 'incidents'); index('runbooks', 'runbooks'); index('certs', 'certificates'); index('packs', 'packs'); index('dispatches', 'dispatches');
  index('schedules', 'schedules'); index('free', 'freeStock'); index('alerts', 'alerts'); index('contracts', 'contracts'); index('holds', 'holds'); index('decisions', 'decisions');
  index('tdcs', 'tdcs'); index('routes', 'routes', 'itemId'); index('threads', 'threads'); index('customers', 'customers'); index('grades', 'grades'); index('coatings', 'coatings');
  index('paints', 'paints'); index('delays', 'delays'); index('slitPlans', 'slitPlans'); index('suggestions', 'maSuggestions'); index('actions', 'actionCatalogue'); index('defectCodes', 'defectCodes', 'code');
  var kids = {}, parentOf = {};
  D.edges.forEach(function (e) { if (e.rel === 'consumesInput') { (kids[e.to] = kids[e.to] || []).push(e.from); parentOf[e.from] = e.to; } });

  function unit(id) { return by.materials[id] || by.free[id] || null; }
  function parents(id) { var out = [], u = unit(id), guard = 0; while (u && guard++ < 20) { out.push(u); var p = parentOf[u.id] || u.parentId; u = p ? unit(p) : null; } return out; }
  function children(id) { var out = [], stack = [id]; while (stack.length) { var x = stack.pop(); (kids[x] || []).forEach(function (k) { if (out.indexOf(k) < 0) { out.push(k); stack.push(k); } }); } return out.map(unit).filter(Boolean); }
  function threadOf(id) { var u = unit(id); return u && u.threadId ? by.threads[u.threadId] : null; }

  // ---- formatting ----
  function fmt(x) { var d = dt(x); return d ? WD[d.getDay()] + ' ' + d.getDate() + ' ' + MO[d.getMonth()] + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()) : '—'; }
  function fmtDT(x) { var d = dt(x); return d ? d.getDate() + ' ' + MO[d.getMonth()] + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()) : '—'; }
  function fmtD(x) { var d = dt(x); return d ? WD[d.getDay()] + ' ' + d.getDate() + ' ' + MO[d.getMonth()] : '—'; }
  function fmtT(x) { var d = dt(x); return d ? pad(d.getHours()) + ':' + pad(d.getMinutes()) : '—'; }
  function ago(x) { var d = dt(x); if (!d) return '—'; var mn = Math.round((ASOF - d) / 60000); if (mn < 0) return 'in ' + dur(-mn); if (mn < 60) return mn + ' min ago'; if (mn < 1440) return Math.floor(mn / 60) + ' h ' + (mn % 60) + ' m ago'; return Math.floor(mn / 1440) + ' d ago'; }
  function dur(mn) { mn = Math.round(mn); if (mn < 60) return mn + ' min'; var h = Math.floor(mn / 60), m = mn % 60; return h + ' h' + (m ? ' ' + m + ' m' : ''); }
  function n(x, d) { if (x == null || isNaN(x)) return '—'; return Number(x).toLocaleString('en-IN', { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  var BADGE = { DONE: 'b-green', OK: 'b-green', ACKED: 'b-green', ACCEPTED: 'b-green', PASS: 'b-green', PRIME: 'b-green', CLEARED: 'b-green', RESOLVED: 'b-green', RELEASED: 'b-green', DISPATCHED: 'b-green', PACKED: 'b-green', CONFIRMED: 'b-green', ACTIVE: 'b-green', APPROVED: 'b-green', AVAILABLE: 'b-green', EXECUTED: 'b-green', POSTED: 'b-green', CLOSED: 'b-grey', RUNNING: 'b-blue',
    IN_PROGRESS: 'b-blue', IN_PROCESS: 'b-blue', SENT: 'b-blue', ALLOCATED: 'b-blue', PACKING: 'b-blue', OPEN: 'b-blue', SUGGESTED: 'b-blue', PLANNED: 'b-grey', RELEASED_PO: 'b-grey', IDLE: 'b-grey', PENDING: 'b-amber', AWAITING_APPROVAL: 'b-amber', IN_QUEUE: 'b-amber',
    ACCEPTED_WITH_DEVIATION: 'b-amber', HOLD: 'b-amber', ON_HOLD: 'b-amber', DOWNGRADE: 'b-amber', DOWNGRADED: 'b-amber', REPLAYED: 'b-amber', STOPPED: 'b-red', FAILED: 'b-red', FAIL: 'b-red', IMBALANCE: 'b-red', REWORK: 'b-purple', SCRAP: 'b-red', SCRAPPED: 'b-red', OVERRIDDEN: 'b-purple', CONSUMED: 'b-grey', BEHIND: 'b-red', ON_TRACK: 'b-green', AUTO_FLAGGED: 'b-red', S1: 'b-red', S2: 'b-amber', S3: 'b-blue', S4: 'b-grey', AUTONOMOUS: 'b-green', APPROVAL: 'b-amber', PROHIBITED: 'b-red', DELIVERED: 'b-green', PARTIALLY_DISPATCHED: 'b-blue', IN_TRANSIT: 'b-grey', FREE: 'b-green', TRANSIT: 'b-grey', RETIRED: 'b-grey', FAILED_IDOC: 'b-red', Major: 'b-amber', Minor: 'b-grey', Critical: 'b-red' };
  function badge(s, label) { return '<span class="badge ' + (BADGE[s] || 'b-grey') + '">' + esc(label || String(s || '—').replace(/_/g, ' ')) + '</span>'; }

  var PAL = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#4a3aa7', '#008300', '#e34948'];
  function color(i) { return PAL[((i % PAL.length) + PAL.length) % PAL.length]; }
  function hash(s) { var h = 0; s = String(s || ''); for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0; return h; }
  function colorFor(id) { return color(hash(id) % PAL.length); }
  var LINE_COLOR = { HRS: '#8a93a0', PKL: '#eda100', CRM: '#2a78d6', CGL: '#1baf7a', CCL: '#e87ba4', SLT: '#4a3aa7', RWL: '#008300', PKG: '#eb6834' };

  // ---- gantt: lanes = [{id,label,sub}], bars = [{lane,start,end,label,color,cls,tip}] ISO strings; opts {from,to,laneW,minPx,laneTitle,showNow} ----
  function gantt(el, lanes, bars, opts) {
    opts = opts || {}; var from = dt(opts.from) || new Date(Math.min.apply(null, bars.map(function (b) { return +dt(b.start); }))), to = dt(opts.to) || new Date(Math.max.apply(null, bars.map(function (b) { return +dt(b.end); })));
    if (!opts.exactFrom) from = new Date(from.getFullYear(), from.getMonth(), from.getDate()); to = new Date(to.getTime() + 3600000 * 2);
    var laneW = opts.laneW || 160, hours = (to - from) / 3600000, avail = Math.max(300, el.clientWidth - laneW - 2), px = Math.max(opts.minPx || 7, avail / hours), W = Math.round(hours * px);
    function x(d) { return Math.round((dt(d) - from) / 3600000 * px); }
    var grid = '', head = '';
    var g0 = new Date(from.getFullYear(), from.getMonth(), from.getDate(), Math.ceil(from.getHours() / 6) * 6);   // gridlines stay on 00 / 06 / 12 / 18 h even when the window starts mid-day
    for (var t = g0; t <= to; t = new Date(t.getTime() + 6 * 3600000)) {
      var isDay = t.getHours() === 0; grid += '<div class="g-grid' + (isDay ? ' day' : '') + '" style="left:' + x(t) + 'px"></div>';
      if (isDay) head += '<div class="g-day" style="left:' + (x(t) + Math.min(px * 12, 60)) + 'px">' + WD[t.getDay()] + '<span class="dm">' + t.getDate() + ' ' + MO[t.getMonth()] + '</span></div>';
    }
    var now = (opts.showNow !== false && ASOF >= from && ASOF <= to) ? '<div class="g-now" style="left:' + x(ASOF) + 'px"></div>' : '';
    var html = '<div class="g-row head"><div class="g-lane head-lane" style="width:' + laneW + 'px">' + esc(opts.laneTitle || 'Line') + '</div><div class="g-track" style="min-width:' + W + 'px">' + grid + head + now + '</div></div>';
    lanes.forEach(function (ln) {
      var bs = bars.filter(function (b) { return b.lane === ln.id; }).map(function (b) {
        var l = x(b.start), w = Math.max(3, x(b.end) - l);
        return '<div class="g-bar ' + (b.cls || '') + '" style="left:' + l + 'px;width:' + w + 'px;background:' + (b.color || '#2a78d6') + '" title="' + esc(b.tip || b.label || '') + '"' + (b.data ? ' data-id="' + esc(b.data) + '"' : '') + '>' + (w > 34 ? esc(b.label || '') : '') + '</div>';
      }).join('');
      html += '<div class="g-row"><div class="g-lane" style="width:' + laneW + 'px" title="' + esc(ln.label) + '">' + esc(ln.label) + (ln.sub ? ' <span class="hint" style="text-transform:none;font-weight:400">' + esc(ln.sub) + '</span>' : '') + '</div><div class="g-track" style="min-width:' + W + 'px">' + grid + now + bs + '</div></div>';
    });
    el.innerHTML = html;
  }

  // ---- JSON pretty print with highlighting ----
  function json(obj) {
    var s = JSON.stringify(obj, null, 2);
    return '<div class="json">' + esc(s).replace(/"([^"]+)":/g, '<span class="key">"$1"</span>:').replace(/: "([^"]*)"/g, ': <span class="str">"$1"</span>').replace(/: (-?\d+\.?\d*)/g, ': <span class="num">$1</span>') + '</div>';
  }
  function toast(msg, icon) { var t = document.createElement('div'); t.className = 'toast'; t.innerHTML = '<i class="fa-solid ' + (icon || 'fa-circle-check') + '"></i><span>' + msg + '</span>'; document.body.appendChild(t); setTimeout(function () { t.remove(); }, 3800); }

  // ---- live-demo state overlay (per browser) ----
  var KEY = 'khp-demo-state';
  var State = {
    all: function () { try { return JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { return {}; } },
    get: function (k, d) { var a = State.all(); return k in a ? a[k] : d; },
    set: function (k, v) { var a = State.all(); a[k] = v; try { localStorage.setItem(KEY, JSON.stringify(a)); } catch (e) {} return v; },
    reset: function () { try { localStorage.removeItem(KEY); } catch (e) {} }
  };
  window.KHPState = State;
  // header "as of" always reflects the dataset's as-of moment (the generator re-bases it to the current date)
  document.querySelectorAll('.bm-header .asof').forEach(function (el) { el.innerHTML = '<i class="fa-regular fa-clock"></i> as of ' + fmt(ASOF) + ' · Shift ' + ((D.live && D.live.shift) || 'A'); });

  window.KHPX = { D: D, ASOF: ASOF, BASE: BASE, by: by, unit: unit, item: function (id) { return by.items[id]; }, order: function (id) { return by.orders[id]; }, line: function (id) { return by.lines[id]; },
    equip: function (id) { return by.equipment[id]; }, route: function (id) { return by.routes[id]; }, tdc: function (id) { return by.tdcs[id]; }, thread: function (id) { return by.threads[id]; },
    parents: parents, children: children, threadOf: threadOf, kids: kids, fmt: fmt, fmtDT: fmtDT, fmtD: fmtD, fmtT: fmtT, ago: ago, dur: dur, n: n, esc: esc, badge: badge, color: color, colorFor: colorFor, LINE_COLOR: LINE_COLOR,
    gantt: gantt, json: json, toast: toast, state: State, hashParam: function () { return decodeURIComponent((location.hash || '').slice(1)); },
    hero: D.meta.hero, isHero: function (id) { return D.meta.hero.units.indexOf(id) >= 0 || id === D.meta.hero.itemId || id === D.meta.hero.soId; } };
})();
