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
    ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'gclid', 'fbclid']
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
