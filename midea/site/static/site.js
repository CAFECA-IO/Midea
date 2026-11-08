/* Midea public site — shared shell: API, CAFECA sign-in, header/footer, view tracking.
   Pages are plain React 18 (no build step) on top of the design system (window.Midea). */
(function () {
  var React = window.React, h = React.createElement, M = window.Midea;
  var API = '/api/public/v1';

  function api(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || 'GET', credentials: 'same-origin', headers: {} };
    if (init.method !== 'GET') init.headers['X-Midea'] = '1';
    if (opts.body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(opts.body); }
    if (opts.keepalive) init.keepalive = true;
    return fetch(API + path, init).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) { var e = new Error(j.detail || j.error || ('HTTP ' + r.status)); e.status = r.status; e.body = j; throw e; }
        return j;
      });
    });
  }

  /* ------------------------------------------------------------ session (tiny store shared by all components) */
  var me = { value: undefined, subs: [] };
  function setMe(v) { me.value = v; me.subs.forEach(function (f) { f(v); }); }
  function useMe() {
    var _s = React.useState(me.value), v = _s[0], set = _s[1];
    React.useEffect(function () {
      me.subs.push(set);
      if (me.value === undefined) api('/me').then(function (j) { setMe(j.me); }).catch(function () { setMe(null); });
      return function () { me.subs = me.subs.filter(function (f) { return f !== set; }); };
    }, []);
    return v;
  }

  /* ------------------------------------------------------------ CAFECA sign-in */
  var sdk = null, sdkLoading = null, dialog = { open: false, subs: [], after: null };
  function loadSdk() {
    if (sdk) return Promise.resolve(sdk);
    if (sdkLoading) return sdkLoading;
    sdkLoading = api('/auth/nonce').then(function (n) {
      return new Promise(function (ok, bad) {
        var s = document.createElement('script');
        s.src = n.wallet + '/sdk/cafeca-connect.js';
        s.onload = function () { sdk = { c: window.CafecaConnect.create({ wallet: n.wallet }), cfg: n }; ok(sdk); };
        s.onerror = function () { sdkLoading = null; bad(new Error('無法連到 CAFECA，請稍後再試')); };
        document.head.appendChild(s);
      });
    });
    return sdkLoading;
  }
  function nonce() { return api('/auth/nonce').then(function (n) { return n.nonce; }); }
  function finish(res) {
    return api('/auth/cafeca', { method: 'POST', body: res }).then(function (j) { setMe(j.me); return j.me; });
  }
  var ERR = { access_denied: '你取消了登入', closed: '登入視窗已關閉', popup_blocked: '瀏覽器擋下了登入視窗，請改用「在這個分頁登入」',
    timeout: '登入逾時，請再試一次', invalid_nonce: '登入請求無效，請重新整理後再試' };

  function openSignIn(after) { dialog.after = after || null; dialog.open = true; dialog.subs.forEach(function (f) { f(true); }); loadSdk().catch(function () {}); }
  function closeSignIn() { dialog.open = false; dialog.subs.forEach(function (f) { f(false); }); }
  /* Run `fn` now if signed in, else after signing in. */
  function requireLogin(fn) { if (me.value) return fn(); openSignIn(fn); }

  function SignIn() {
    var _o = React.useState(dialog.open), open = _o[0], setOpen = _o[1];
    var _e = React.useState(''), err = _e[0], setErr = _e[1];
    var _q = React.useState(null), qr = _q[0], setQr = _q[1];
    React.useEffect(function () { dialog.subs.push(setOpen); return function () { dialog.subs = dialog.subs.filter(function (f) { return f !== setOpen; }); }; }, []);
    React.useEffect(function () {
      if (!open) { setErr(''); setQr(null); return; }
      var stop = false, n = null;
      // QR (cross-device, "post" mode): the CAFECA app posts the response to our server; we poll for it
      loadSdk().then(function (s) {
        return nonce().then(function (x) { n = x; return s.c.authLink({ nonce: x, mode: 'post', responseUri: s.cfg.responseUri, statement: s.cfg.statement, claims: s.cfg.claims, ttl: 300 }); });
      }).then(function (link) {
        if (stop || !window.qrcode) return;
        var q = window.qrcode(0, 'M'); q.addData(link); q.make();
        setQr(q.createSvgTag({ cellSize: 3, margin: 0, scalable: true }));
        (function poll() {
          if (stop) return;
          api('/auth/post/claim', { method: 'POST', body: { nonce: n } }).then(function (j) {
            if (j && j.me) { setMe(j.me); done(); } else setTimeout(poll, 2000);
          }).catch(function (e) { if (e.status === 400) setErr(e.message); else setTimeout(poll, 3000); });
        })();
      }).catch(function () {});
      return function () { stop = true; };
    }, [open]);
    function done() { var f = dialog.after; closeSignIn(); if (f) setTimeout(f, 0); }
    function popup() {
      setErr('');
      if (!sdk) { setErr('正在連線到 CAFECA，請再按一次'); loadSdk(); return; }
      sdk.c.signIn({ nonce: nonce, statement: sdk.cfg.statement, claims: sdk.cfg.claims })
        .then(finish).then(done)
        .catch(function (e) { setErr(ERR[e && e.code] || (e && e.message) || '登入失敗'); });
    }
    function redirect() {
      if (!sdk) { setErr('正在連線到 CAFECA，請再按一次'); loadSdk(); return; }
      try { sessionStorage.setItem('midea_return', location.pathname + location.search); } catch (e) {}
      nonce().then(function (x) { return sdk.c.redirect({ nonce: x, redirectUri: sdk.cfg.redirectUri, statement: sdk.cfg.statement, claims: sdk.cfg.claims }); })
        .catch(function (e) { setErr(ERR[e && e.code] || e.message); });
    }
    return h(M.SignInDialog, {
      open: open, onClose: closeSignIn, title: '以 CAFECA 登入', closeLabel: '關閉',
      body: '用裝置上的通行金鑰登入，不需要密碼，也不必另外註冊。登入後可以收藏、投票，主題與觀看紀錄會在各裝置同步。',
      popupLabel: '以 CAFECA 登入', onPopup: popup, redirectLabel: '在這個分頁登入', onRedirect: redirect,
      qr: qr ? h('span', { dangerouslySetInnerHTML: { __html: qr } }) : null, qrLabel: '用手機上的 CAFECA App 掃描，也可以登入這台電腦。',
      error: err, footer: 'Midea 只會收到你的 CAFECA 身分與你同意分享的資料（代號、驗證等級），不會收到密碼。'
    });
  }

  /* ------------------------------------------------------------ shell */
  var NAV = [{ label: '首頁', href: '/' }, { label: '直播', href: '/live' }, { label: '節目表', href: '/schedule' },
    { label: '主題', href: '/#topics' }, { label: '演員', href: '/#actors' }];

  function Account() {
    var v = useMe();
    if (v === undefined) return h('span', { style: { width: 120 } });
    if (!v) return h(M.SignInButton, { onClick: function () { openSignIn(); } });
    var kyc = v.kyc_level == null ? 'CAFECA 身分' : 'CAFECA 身分 · 驗證等級 ' + v.kyc_level;
    return h(M.AccountMenu, { name: v.nickname, sub: kyc, items: [
      { label: '我的收藏', href: '/#favorites' },
      { label: '登出', onClick: function () { api('/auth/logout', { method: 'POST' }).then(function () { setMe(null); }); } }] });
  }

  function Shell(p) {
    var path = location.pathname;
    var items = NAV.map(function (n) { return Object.assign({}, n, { active: n.href === path }); });
    return h('div', { className: 'site' },
      h('div', { className: 'site-wrap' },
        h(M.SiteHeader, { items: items, search: false, account: h(Account) }),
        h('main', { id: 'main' }, p.children),
        h('div', { className: 'site-foot' }, h(M.SiteFooter, null))),
      h(M.BottomNav, { label: '主選單', items: [
        { label: '首頁', href: '/', icon: 'home', active: path === '/' },
        { label: '直播', href: '/live', icon: 'play', active: path === '/live' },
        { label: '節目表', href: '/schedule', icon: 'calendar', active: path === '/schedule' },
        { label: '主題', href: '/#topics', icon: 'grid' }] }),
      h(SignIn));
  }

  function mount(App) {
    ReactDOM.createRoot(document.getElementById('root')).render(h(Shell, null, h(App)));
  }

  /* ------------------------------------------------------------ helpers */
  function cast(v) { return (v.cast || []).map(function (c) { return c.name + ' @' + c.handle; }).join('、'); }
  function videoLine(v) { return [v.kind, v.duration_label, cast(v)].filter(Boolean).join(' · '); }

  /* 最多人看 counts completed views: report the furthest point watched, once at the end and once when leaving. */
  function viewTracker(videoId) {
    var best = 0, sent = false, done = false;
    function send(completed, keep) {
      if (sent && !completed) return;
      if (completed) { if (done) return; done = true; }
      sent = true;
      api('/videos/' + videoId + '/view', { method: 'POST', body: { seconds: best, completed: !!completed }, keepalive: !!keep }).catch(function () {});
    }
    function onHide() { if (best > 1) send(false, true); }
    window.addEventListener('pagehide', onHide);
    return {
      progress: function (seconds, duration, ended) { best = Math.max(best, seconds || 0); if (ended) send(true); },
      stop: function () { window.removeEventListener('pagehide', onHide); onHide(); }
    };
  }

  function share(path, t) {
    var url = location.origin + path + (t ? '?t=' + Math.floor(t) : '');
    if (navigator.share) return navigator.share({ url: url }).catch(function () {});
    return navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.resolve();
  }

  function toast(text) {
    var el = document.createElement('div');
    el.className = 'toast'; el.setAttribute('role', 'status'); el.textContent = text;
    document.body.appendChild(el);
    setTimeout(function () { el.remove(); }, 3000);
  }

  window.Site = { toast: toast, api: api, useMe: useMe, setMe: setMe, openSignIn: openSignIn, requireLogin: requireLogin, mount: mount,
    cast: cast, videoLine: videoLine, viewTracker: viewTracker, share: share, finishLogin: finish };
})();
