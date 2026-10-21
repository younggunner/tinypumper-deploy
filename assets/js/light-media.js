/* light-media.js: the one loader for looping videos and thumbnails on tinypumper.com.
   WHY (Greg, 2026-10-21): many prospects open these pages on phones in rural and remote areas
   with weak signal. A muted loop is decoration, so it plays only on a good connection and only
   while on screen; everyone else sees its still (poster). Thumbnails load as they scroll in.
   Enforced on every push by scripts/check-page-weight.py (page-weight gate workflow). Same code as
   greasebook.com's assets/js/gb-light-media.js, whose behavior tests live in greasebook-deploy
   (tests/test_light_media.py); change both together.

   Markup it handles:
     <video data-light-video muted loop playsinline preload="none" poster="still.webp">
       <source data-src="clip.mp4" type="video/mp4"></video>
     (data-lazy-autoplay is the older name for the same thing and is still honored)
     <div data-bg="thumb.webp"></div>  -> background-image set when it nears the screen
   Page scripts that add elements later call window.gbLight.observe(el). */
(function () {
  if (window.gbLight) return;

  function fast() {
    try {
      if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
      var c = navigator.connection;
      if (!c) return true;            // browsers that don't report the connection get the loop
      if (c.saveData) return false;   // data saver on
      return !c.effectiveType || c.effectiveType === '4g';
    } catch (e) { return true; }
  }

  var onScreen = [];                  // videos currently visible

  function startVideo(v) {
    if (!fast()) return;              // rechecked every time: the signal can drop after load
    if (!v.dataset.lightOn) {
      if (v.dataset.src) v.src = v.dataset.src;
      v.querySelectorAll('source[data-src]').forEach(function (s) { s.src = s.dataset.src; });
      v.load();
      v.dataset.lightOn = '1';
    }
    var p = v.play && v.play();
    if (p && p.catch) p.catch(function () {});
  }
  function stopVideo(v) { if (v.dataset.lightOn) v.pause(); }
  function showBg(el) { el.style.backgroundImage = "url('" + el.dataset.bg + "')"; }

  var hasIO = 'IntersectionObserver' in window;
  // Videos: only while actually on screen (no margin), so an unseen loop never downloads or plays.
  var videoIO = hasIO ? new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      var v = e.target, i = onScreen.indexOf(v);
      if (e.isIntersecting) { if (i < 0) onScreen.push(v); startVideo(v); }
      else { if (i >= 0) onScreen.splice(i, 1); stopVideo(v); }
    });
  }) : null;
  // Thumbnails: a little early, so they are there when the visitor arrives.
  var bgIO = hasIO ? new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) { showBg(e.target); bgIO.unobserve(e.target); }
    });
  }, { rootMargin: '300px' }) : null;

  function observe(root) {
    var scope = root && root.querySelectorAll ? root : document;
    var els = [];
    if (root && root.matches && root.matches('video[data-light-video], video[data-lazy-autoplay], [data-bg]')) els.push(root);
    scope.querySelectorAll('video[data-light-video], video[data-lazy-autoplay], [data-bg]').forEach(function (el) { els.push(el); });
    els.forEach(function (el) {
      if (el.tagName === 'VIDEO') videoIO ? videoIO.observe(el) : startVideo(el);
      else bgIO ? bgIO.observe(el) : showBg(el);
    });
  }

  // Signal got worse (or better) after the page opened: pause or resume what is on screen.
  try {
    if (navigator.connection && navigator.connection.addEventListener) {
      navigator.connection.addEventListener('change', function () {
        onScreen.forEach(function (v) { fast() ? startVideo(v) : stopVideo(v); });
      });
    }
  } catch (e) {}

  window.gbLight = { fast: fast, observe: observe };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { observe(); });
  else observe();
})();
