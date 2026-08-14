/* tp-attr.js — cross-domain attribution + page-journey breadcrumb for tinypumper.com.
   Parallel to gb-attr.js on greasebook.com. Same shape, different cookie/domain.
   Mechanism: first-party cookie tp_attr on .tinypumper.com (read by quiz subdomain)
              + tp_journey in localStorage (FIFO 20). Origin referrer never overwritten
              once set (90-day TTL).
   Read by:   instapage-embed-snippet-tinypumper.html on quiz.tinypumper.com → Typeform
              hidden fields origin_referrer + page_journey → typeform-ga4-relay v15
              → visitor_attribution.{origin_referrer,page_journey}. */
(function () {
  try {
    var COOKIE = 'tp_attr';
    var JOURNEY_KEY = 'tp_journey';
    var TTL_DAYS = 90;
    var MAX_J = 20;
    var MAX_COOKIE_J = 6;
    var DOMAIN = '.tinypumper.com';

    function readCookie(n) {
      var m = document.cookie.match(new RegExp('(?:^|; )' + n + '=([^;]*)'));
      return m ? decodeURIComponent(m[1]) : '';
    }
    function writeCookie(n, v) {
      var exp = new Date(Date.now() + TTL_DAYS * 86400000).toUTCString();
      document.cookie = n + '=' + encodeURIComponent(v) + ';expires=' + exp +
        ';domain=' + DOMAIN + ';path=/;SameSite=Lax';
    }

    var now = Date.now();
    var ref = document.referrer || '';
    var refHost = '';
    try { refHost = ref ? new URL(ref).hostname : ''; } catch (e) {}
    var sameSite = refHost.indexOf('tinypumper.com') >= 0;

    var prev = {};
    var raw = readCookie(COOKIE);
    if (raw) { try { prev = JSON.parse(raw); } catch (e) { prev = {}; } }

    if (!prev.origin_referrer && ref && !sameSite) {
      prev.origin_referrer = ref;
      prev.origin_at = now;
    }

    var p = new URLSearchParams(window.location.search);
    ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'gclid', 'msclkid', 'fbclid']
      .forEach(function (k) {
        var v = p.get(k);
        if (v && !prev[k]) prev[k] = v;
      });

    var journey = [];
    try {
      var j = localStorage.getItem(JOURNEY_KEY);
      if (j) journey = JSON.parse(j) || [];
    } catch (e) { journey = []; }
    // Pathname only — query strings (utm_*, comet_*, embed=, gclid, fbclid) are
    // captured separately on prev.* and would otherwise make the journey
    // breadcrumb unreadable (e.g. "/?utm_source=google&utm_medium=paid…").
    var path = window.location.pathname || '/';
    var last = journey[journey.length - 1];
    if (!last || last.u !== path) {
      journey.push({ u: path, t: now });
      if (journey.length > MAX_J) journey = journey.slice(-MAX_J);
      try { localStorage.setItem(JOURNEY_KEY, JSON.stringify(journey)); } catch (e) {}
    }

    prev.journey = journey.slice(-MAX_COOKIE_J).map(function (x) {
      return { u: x.u.length > 120 ? x.u.slice(0, 120) : x.u, t: x.t };
    });

    writeCookie(COOKIE, JSON.stringify(prev));
  } catch (e) { /* never break the page */ }
})();

/* --- KVS engagement telemetry (added 2026-07-14, Greg-approved) ---
   /ppc/ landers only. Measures ACTIVE dwell (visibility + recent-interaction
   gated heartbeat — a tab left open 14h records only real attention), max
   scroll %, and the page's own word count (for read-ratio scoring server-side).
   Beacons to the lander-engagement Supabase edge function on tab-hide/pagehide;
   text/plain avoids CORS preflight with sendBeacon. Never breaks the page. */
(function () {
  try {
    // Site-wide since 2026-07-14 (was /ppc/-only): platform traffic-quality
    // scoring needs homepage + lead-magnet + BOF pages too. Note: #pricing
    // anchor arrivals register instant deep scroll (Capterra Pricing CTA).
    var EP = 'https://nhdethynnmgrqlswqiqj.supabase.co/functions/v1/lander-engagement';
    var BRAND = 'tp';
    var vid = 'v' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
    var active = 0, lastAct = Date.now(), maxScroll = 0, words = 0;
    function onAct() { lastAct = Date.now(); }
    ['scroll', 'mousemove', 'keydown', 'touchstart', 'click'].forEach(function (e) {
      window.addEventListener(e, onAct, { passive: true });
    });
    setInterval(function () {
      if (document.visibilityState === 'visible' && Date.now() - lastAct < 60000) {
        active += 5;
        if (active > 1800) active = 1800;
      }
    }, 5000);
    function measure() {
      var d = document.documentElement;
      var h = Math.max(d.scrollHeight, document.body ? document.body.scrollHeight : 0);
      if (h > 0) {
        var pct = Math.round(100 * (window.scrollY + window.innerHeight) / h);
        if (pct > maxScroll) maxScroll = pct > 100 ? 100 : pct;
      }
    }
    window.addEventListener('scroll', measure, { passive: true });
    function send() {
      try {
        measure();
        if (!words && document.body) {
          words = (document.body.innerText || '').split(/\s+/).filter(Boolean).length;
        }
        var p = new URLSearchParams(window.location.search);
        // Attribution: URL utms first; else fall back to the first-touch
        // attribution cookie this same file maintains (added 2026-08-14 —
        // before this, every follow-on pageview landed unattributed, ~53% of
        // all rows, and deep reading mostly happens on the second page).
        // attr_from tells the analysis which path attributed the row.
        var us = p.get('utm_source') || '', uc = p.get('utm_campaign') || '',
            ut = p.get('utm_term') || '', af = (us || uc) ? 'url' : '';
        if (!af) {
          try {
            var cm = document.cookie.match(/(?:^|; )tp_attr=([^;]*)/);
            if (cm) {
              var ck = JSON.parse(decodeURIComponent(cm[1])) || {};
              us = ck.utm_source || ''; uc = ck.utm_campaign || '';
              ut = ck.utm_term || '';
              if (us || uc) af = 'cookie';
            }
          } catch (e) {}
        }
        // 404 pages set window.__attrPageOverride='/404/' so dead URLs stop
        // logging phantom page paths (they still count as a 404 hit).
        var payload = JSON.stringify({
          visit_id: vid, brand: BRAND,
          page: window.__attrPageOverride || window.location.pathname,
          utm_term: ut, utm_source: us, utm_campaign: uc, attr_from: af,
          max_scroll_pct: maxScroll, active_seconds: active, word_count: words,
          entry_hash: (window.location.hash || '').slice(0, 40)
        });
        if (navigator.sendBeacon) {
          navigator.sendBeacon(EP, new Blob([payload], { type: 'text/plain' }));
        }
      } catch (e) {}
    }
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') send();
    });
    window.addEventListener('pagehide', send);
  } catch (e) { /* never break the page */ }
})();
