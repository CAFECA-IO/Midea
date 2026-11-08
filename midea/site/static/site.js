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
    { label: '主題', href: '/#topics' }, { label: '演員', href: '/#actors' }, { label: '許願牆', href: '/wishes' }];

  function Account() {
    var v = useMe();
    if (v === undefined) return h('span', { style: { width: 120 } });
    if (!v) return h(M.SignInButton, { onClick: function () { openSignIn(); } });
    var kyc = v.kyc_level == null ? 'CAFECA 身分' : 'CAFECA 身分 · 驗證等級 ' + v.kyc_level;
    return h(M.AccountMenu, { name: v.nickname, sub: kyc + (v.restriction ? ' · ' + v.restriction : ''), items: [
      { label: '製作後台（我的演員與影片）', href: '/studio' },
      { label: '我的收藏', href: '/#favorites' },
      { label: '修改暱稱', onClick: function () { askNickname(); } },
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
        { label: '主題', href: '/#topics', icon: 'grid' },
        { label: '許願', href: '/wishes', icon: 'star', active: path === '/wishes' }] }),
      h(SignIn), h(AskDialog));
  }

  function mount(App) {
    ReactDOM.createRoot(document.getElementById('root')).render(h(Shell, null, h(App)));
    // /?signin=studio — the studio sends signed-out visitors here; after signing in they go back to /studio
    if (new URLSearchParams(location.search).get('signin') === 'studio') {
      api('/me').then(function (j) {
        if (j.me) location.replace('/studio');
        else openSignIn(function () { location.replace('/studio'); });
      });
    }
  }

  /* a small in-page dialog: text input or a choice list, styled like SignInDialog */
  var ask = { open: null, subs: [] };
  function askUser(cfg) {
    return new Promise(function (ok) { ask.open = Object.assign({}, cfg, { done: ok }); ask.subs.forEach(function (f) { f(ask.open); }); });
  }
  function AskDialog() {
    var _c = React.useState(null), c = _c[0], set = _c[1];
    var _v = React.useState(''), val = _v[0], setVal = _v[1];
    var ref = React.useRef(null);
    React.useEffect(function () { ask.subs.push(function (x) { set(x); setVal(x && x.value || ''); }); }, []);
    React.useEffect(function () { var d = ref.current; if (!d) return; if (c && !d.open) d.showModal(); if (!c && d.open) d.close(); }, [c]);
    function end(v) { var f = c && c.done; set(null); if (f) f(v); }
    return h('dialog', { ref: ref, className: 'md-dialog', 'aria-labelledby': 'ask-t', onCancel: function (e) { e.preventDefault(); end(null); } },
      c ? h('form', { onSubmit: function (e) { e.preventDefault(); end(val.trim() || null); } },
        h('div', { className: 'md-dialog-head' }, h('h2', { id: 'ask-t', className: 'md-dialog-title' }, c.title),
          h('button', { type: 'button', className: 'md-iconbtn', 'aria-label': '關閉', onClick: function () { end(null); } }, h(M.Icon, { name: 'x', size: 18 }))),
        c.body ? h('p', { className: 'md-dialog-body' }, c.body) : null,
        c.choices ? h('div', { className: 'md-reactbar-opts', role: 'radiogroup', 'aria-label': c.title, style: { marginBottom: 16 } }, c.choices.map(function (x) {
          return h('button', { key: x, type: 'button', role: 'radio', 'aria-checked': val === x ? 'true' : 'false', className: 'md-chip md-chip-sm' + (val === x ? ' is-on' : ''), onClick: function () { setVal(x); } }, x);
        })) : h('input', { className: 'md-input', autoFocus: true, value: val, maxLength: c.max || 40, onChange: function (e) { setVal(e.target.value); }, style: { marginBottom: 16 } }),
        h('div', { className: 'md-dialog-actions' }, h(M.Button, { type: 'submit', disabled: !val.trim() }, c.ok || '確定'), h(M.Button, { variant: 'ghost', onClick: function () { end(null); } }, '取消'))) : null);
  }

  /* 公開暱稱：first time someone writes, or from the account menu */
  function askNickname(then) {
    var cur = me.value && me.value.nickname || '';
    return askUser({ title: '設定公開暱稱', body: '在聊天室、許願牆與提問時顯示。2–16 字，不能用演員姓名、@代號、「Midea」或「官方」。', value: cur, max: 16, ok: '儲存' }).then(function (n) {
      if (n === null) return false;
      return api('/me/nickname', { method: 'POST', body: { nickname: n } }).then(function (j) {
      setMe(Object.assign({}, me.value, { nickname: j.nickname, has_nickname: true })); if (then) then(); return true;
      }).catch(function (e) { toast(e.message); return false; });
    });
  }
  /* writing (chat, wishes, questions): signed in, has a nickname, not muted */
  function requireWriter(fn) {
    requireLogin(function () {
      var v = me.value;
      if (v && v.restriction) return toast(v.restriction);
      if (v && !v.has_nickname) return askNickname(fn);
      fn();
    });
  }
  var REPORT_REASONS = ['騷擾', '仇恨', '色情', '個資', '廣告', '真實人物', '其他'];
  function report(kind, id) {
    requireLogin(function () {
      askUser({ title: '檢舉這則內容', body: '被 3 位不同的觀眾檢舉就會先隱藏，再由管理者處理。', choices: REPORT_REASONS, ok: '送出檢舉' }).then(function (r) {
      if (r === null) return;
      api('/reports', { method: 'POST', body: { kind: kind, id: id, reason: r } })
        .then(function (j) { toast(j.hidden ? '已檢舉，這則內容已先隱藏，等待管理者處理' : '已檢舉，謝謝你'); })
        .catch(function (e) { toast(e.message); });
      });
    });
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

  /* ------------------------------------------------------------ immersive (phones): shared by live and watch */
  function useMobile() {
    var q = window.matchMedia ? window.matchMedia('(max-width: 639px)') : null;
    var _m = React.useState(!!(q && q.matches)), m = _m[0], set = _m[1];
    React.useEffect(function () {
      if (!q) return;
      var f = function () { set(q.matches); };
      if (q.addEventListener) q.addEventListener('change', f); else q.addListener(f);
      return function () { if (q.removeEventListener) q.removeEventListener('change', f); else q.removeListener(f); };
    }, []);
    return m;
  }
  function reducedMotion() { return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); }
  /* the blurred light around the picture: a 32×18 copy of the current frame, scaled up and blurred by CSS */
  function Ambient(p) {
    var cref = React.useRef(null);
    React.useEffect(function () {
      if (reducedMotion()) return;
      var id = setInterval(function () {
        var v = p.video && p.video.current, c = cref.current;
        if (!v || !c || v.readyState < 2) return;
        try { c.getContext('2d').drawImage(v, 0, 0, c.width, c.height); } catch (e) {}
      }, 700);
      return function () { clearInterval(id); };
    }, [p.video]);
    return h(React.Fragment, null,
      h('div', { className: 'imv-amb', 'aria-hidden': 'true', style: { backgroundImage: 'url(' + p.image + ')' } }, h('canvas', { ref: cref, width: 32, height: 18 })),
      h('div', { className: 'imv-shade', 'aria-hidden': 'true' }));
  }
  /* interface visibility: tap toggles, 3 s without input hides, `busy` keeps it up; the site shell steps aside */
  function useImmersive(busy) {
    var _u = React.useState(false), ui = _u[0], setUi = _u[1];
    var timer = React.useRef(null), busyRef = React.useRef(busy);
    busyRef.current = busy;
    React.useEffect(function () { document.body.classList.add('is-immersive'); return function () { document.body.classList.remove('is-immersive'); clearTimeout(timer.current); }; }, []);
    function poke() {
      setUi(true); clearTimeout(timer.current);
      timer.current = setTimeout(function () { if (!busyRef.current) setUi(false); }, 3000);
    }
    function hide() { clearTimeout(timer.current); setUi(false); }
    React.useEffect(function () { if (busy) clearTimeout(timer.current); else if (ui) poke(); }, [busy]);
    return { ui: ui, poke: poke, hide: hide, toggle: function () { if (ui) hide(); else poke(); } };
  }
  /* tap vs long-press on one element (pointer events; long-press = 500 ms) */
  // a hook: call it unconditionally during render. The timer lives in a ref so a
  // re-render mid-press (timeupdate, SSE) doesn't forget that the long press fired.
  function pressHandlers(onTap, onLong, ms) {
    var r = React.useRef({ t: null, fired: false, down: false });
    var cb = React.useRef({}); cb.current = { tap: onTap, long: onLong };
    return {
      onPointerDown: function (e) { var s = r.current; s.fired = false; s.down = true; clearTimeout(s.t); s.t = setTimeout(function () { s.fired = true; cb.current.long(e); }, ms || 500); },
      onPointerUp: function (e) { var s = r.current; clearTimeout(s.t); if (s.down && !s.fired) cb.current.tap(e); s.down = false; },
      onPointerLeave: function () { var s = r.current; clearTimeout(s.t); s.down = false; },
      onContextMenu: function (e) { e.preventDefault(); }
    };
  }
  function fmtTime(s) { s = Math.max(0, Math.floor(s || 0)); return Math.floor(s / 60) + ':' + ('0' + s % 60).slice(-2); }

  window.Site = { useMobile: useMobile, reducedMotion: reducedMotion, Ambient: Ambient, useImmersive: useImmersive, pressHandlers: pressHandlers, fmtTime: fmtTime,
    askNickname: askNickname, requireWriter: requireWriter, report: report, toast: toast, api: api, useMe: useMe, setMe: setMe, openSignIn: openSignIn, requireLogin: requireLogin, mount: mount,
    cast: cast, videoLine: videoLine, viewTracker: viewTracker, share: share, finishLogin: finish };
})();
