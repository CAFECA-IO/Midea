/* 官方頻道直播：即時反應、同時在看、時段結束投票、換片時的反應列 */
(function () {
  var React = window.React, h = React.createElement, M = window.Midea, S = window.Site;
  var LIVE = [{ value: 'like', label: '喜歡', icon: 'heart' }, { value: 'beautiful', label: '美', icon: 'sparkle' },
    { value: 'funny', label: '好笑', icon: 'smile' }, { value: 'moving', label: '感動', icon: 'tear' }, { value: 'more', label: '想看更多', icon: 'plus' }];
  var REACT = [{ value: 'like', label: '喜歡', icon: 'heart' }, { value: 'more', label: '想看更多這類', icon: 'plus' },
    { value: 'not_interested', label: '不感興趣', icon: 'x', askReason: true }];
  var REASONS = [{ value: 'topic', label: '主題不合' }, { value: 'seen', label: '看過了' }, { value: 'quality', label: '品質不好' }, { value: 'other', label: '其他' }];

  function hiddenPref() { try { return localStorage.getItem('midea_hide_live_reactions') === '1'; } catch (e) { return false; } }

  function Live() {
    var _n = React.useState(null), now = _n[0], setNow = _n[1];
    var _t = React.useState({}), tick = _t[0], setTick = _t[1];
    var _h = React.useState(hiddenPref()), hidden = _h[0], setHidden = _h[1];
    var _p = React.useState(null), prev = _p[0], setPrev = _p[1];          // the video that just finished (for ReactionBar)
    var _r = React.useState(null), prevReaction = _r[0], setPrevReaction = _r[1];
    var _v = React.useState({}), slotVotes = _v[0], setSlotVotes = _v[1];
    var _f = React.useState(false), fav = _f[0], setFav = _f[1];
    var tracker = React.useRef(null), started = React.useRef(0), me = S.useMe();
    var _c = React.useState({ messages: [], pinned: null, slot: null }), chat = _c[0], setChat = _c[1];
    var _cn = React.useState(''), chatNote = _cn[0], setChatNote = _cn[1];
    var mobile = useMobile();

    function load() { return S.api('/live/now').then(function (j) { setNow(j); return j; }); }
    var slotId = now && now.slot && now.slot.id;
    React.useEffect(function () { if (slotId) S.api('/live/chat').then(setChat).catch(function () {}); }, [slotId]);
    function sendChat(text) {
      return new Promise(function (ok) {
        S.requireWriter(function () {
          S.api('/live/chat', { method: 'POST', body: { text: text } }).then(function (j) {
            if (j.status === 'rejected') { setChatNote(j.message); ok(false); return; }
            setChatNote(''); if (j.item) setChat(function (c) { return c.messages.some(function (x) { return x.id === j.item.id; }) ? c : Object.assign({}, c, { messages: c.messages.concat([j.item]) }); });
            ok(true);
          }).catch(function (e) { setChatNote(e.message); ok(false); });
        });
      });
    }
    React.useEffect(function () { load(); }, []);
    React.useEffect(function () {
      if (!window.EventSource) return;
      var es = new EventSource('/api/public/v1/live/stream');
      es.onmessage = function (e) {
        try {
          var j = JSON.parse(e.data); setTick(j);
          if (j.chat || j.chat_removed) setChat(function (c) {
            var gone = j.chat_removed || [];
            var add = (j.chat || []).filter(function (m) { return m.slot === c.slot && !c.messages.some(function (x) { return x.id === m.id; }); });
            return Object.assign({}, c, { messages: c.messages.concat(add).filter(function (m) { return gone.indexOf(m.id) < 0; }).slice(-200) });
          });
        } catch (x) {}
      };
      return function () { es.close(); };
    }, []);
    // a new item: start tracking how much of it this viewer actually watches
    var item = now && now.item;
    React.useEffect(function () {
      if (!item) return;
      started.current = now.offset || 0;
      tracker.current = S.viewTracker(item.id);
      setFav(false);
      if (me) S.api('/videos/' + item.id).then(function (j) { setFav(j.favorite); }).catch(function () {});
      return function () { if (tracker.current) tracker.current.stop(); };
    }, [item && item.id, now && now.slot && now.slot.id]);

    function ended() {
      if (item && tracker.current && watched.current >= 0.9 * item.duration) tracker.current.progress(item.duration, item.duration, true);
      watched.current = 0;
      if (item) {
        setPrev(item); setPrevReaction(null);
        S.api('/videos/' + item.id).then(function (j) { setPrevReaction(j.reaction); }).catch(function () {});
      }
      load();
    }
    var watched = React.useRef(0);
    function onTime(t) {
      // seconds actually watched in this sitting; 「完整看完」 = at least 90 % of the video
      watched.current = Math.max(0, t - started.current);
      if (tracker.current) tracker.current.progress(watched.current, item.duration, false);
    }
    function react(kind) {
      S.api('/live/reactions', { method: 'POST', body: { kind: kind } }).catch(function () {});
    }
    function toggleHidden() {
      var v = !hidden; setHidden(v);
      try { localStorage.setItem('midea_hide_live_reactions', v ? '1' : '0'); } catch (e) {}
    }
    function slotVote(want) {
      var sp = tick.slot_poll; if (!sp) return;
      S.requireLogin(function () {
        S.api('/live/slot-vote', { method: 'POST', body: { slot: sp.slot, want: want === 'want' } })
          .then(function () { var o = {}; o[sp.slot] = want; setSlotVotes(Object.assign({}, slotVotes, o)); })
          .catch(function (e) { S.toast(e.message); });
      });
    }
    function setReaction(kind, reason) {
      if (!prev) return;
      setPrevReaction(kind);
      (kind ? S.api('/videos/' + prev.id + '/reaction', { method: 'POST', body: { kind: kind, reason: reason } })
        : S.api('/videos/' + prev.id + '/reaction', { method: 'DELETE' })).catch(function (e) { S.toast(e.message); });
    }
    function toggleFav() {
      if (!item) return;
      S.requireLogin(function () {
        var on = !fav; setFav(on);
        S.api('/videos/' + item.id + '/favorite', { method: on ? 'POST' : 'DELETE' }).then(function () { S.toast(on ? '已加入收藏' : '已移出收藏'); })
          .catch(function (e) { setFav(!on); S.toast(e.message); });
      });
    }

    if (!now) return h(M.Skeleton, { height: 420 });
    if (!item) return h(M.EmptyState, { title: '官方頻道準備中', body: '平台上還沒有可以播出的影片。' });
    var slot = now.slot, sp = tick.slot_poll;
    var cast = S.cast(item);
    if (mobile) return h(Immersive, { now: now, item: item, slot: slot, tick: tick, sp: sp, cast: cast, me: me, chat: chat, chatNote: chatNote, sendChat: sendChat,
      ended: ended, onTime: onTime, react: react, hidden: hidden, toggleHidden: toggleHidden, slotVotes: slotVotes, slotVote: slotVote,
      prev: prev, prevReaction: prevReaction, setReaction: setReaction, fav: fav, toggleFav: toggleFav });
    return h('div', { className: 'live-layout' },
      h('div', { className: 'live-main' },
        h(M.LivePlayer, { src: item.src, poster: item.image, offset: now.offset, onEnded: ended, onTime: onTime, label: '官方頻道直播：' + item.title,
          unmuteLabel: '開啟聲音', muteLabel: '靜音', fullscreenLabel: '全螢幕',
          badge: h(React.Fragment, null, h(M.Badge, { tone: 'live' }), h(M.Badge, { tone: 'neutral', dot: false }, 'Midea 官方頻道')),
          topRight: h(M.ViewerCount, { count: tick.viewers, onImage: true, label: function (n) { return n + ' 人正在看'; } }) },
          h(M.LiveReactions, { options: LIVE, label: '即時反應', burst: tick.reactions, onReact: react, hidden: hidden, onToggleHidden: toggleHidden,
            toggleLabel: hidden ? '顯示畫面上的反應' : '關閉畫面上的反應' }),
          sp ? h('div', { className: 'overlay-poll' }, h(M.PollCard, { variant: 'overlay', eyebrow: '這個時段再 ' + sp.ends_in + ' 秒結束',
            title: '下週還想看「' + sp.title + '」嗎？', value: slotVotes[sp.slot] || null,
            options: [{ id: 'want', title: '想' }, { id: 'no', title: '不想' }], onVote: slotVote,
            note: slotVotes[sp.slot] ? '已收到，結果會進下週排程' : '「想」過半就重播或做續集 · 需以 CAFECA 登入' })) : null),
        h(M.VideoMeta, { eyebrow: slot.range + '　' + slot.title + ' · 第 ' + (now.index + 1) + ' / ' + now.of + ' 部', title: item.title,
          meta: [item.kind, item.duration_label, cast].filter(Boolean).join(' · '),
          tags: [slot.influence ? h(M.InfluenceTag, { key: 'i' }, slot.influence) : null, slot.reason ? h(M.Tag, { key: 'r' }, 'AI 排入理由：' + slot.reason) : null].filter(Boolean),
          actions: [h(M.Button, { key: 'f', variant: 'ghost', icon: 'bookmark', onClick: toggleFav }, fav ? '已收藏' : '收藏'),
            h(M.Button, { key: 's', variant: 'ghost', icon: 'share', onClick: function () { S.share('/watch/' + item.id).then(function () { S.toast('已複製連結'); }); } }, '分享')] }),
        prev ? h(M.ReactionBar, { title: '剛播完《' + prev.title + '》，你覺得？', options: REACT, value: prevReaction, onChange: setReaction,
          reasons: REASONS, reasonPrompt: '可以告訴我們原因（可略過）', skipLabel: '略過',
          note: '不用登入也可以按 · 你的反應會影響你看到的主題' }) : null,
        h(M.AIDisclosure, null, '官方頻道的節目由 AI 從平台影片排定；影片由 AI 製作，演員皆為虛擬角色。')),
      h('div', { className: 'live-side' },
        h(M.ChatPanel, { title: '聊天室', meta: tick.viewers ? tick.viewers + ' 人正在看' : null, pinned: chat.pinned, pinnedLabel: '官方',
          messages: chat.messages, onReport: function (m) { S.report('chat', m.id); }, reportLabel: '檢舉這則訊息',
          signedIn: !!me, onSignIn: function () { S.openSignIn(); }, signInLabel: '以 CAFECA 登入後聊天',
          placeholder: me && me.restriction ? me.restriction : '說點什麼（最多 100 字）', inputLabel: '聊天訊息', sendLabel: '送出', max: 100,
          disabled: !!(me && me.restriction), notice: chatNote, hint: '每 5 秒 1 則 · 訊息先經過審核才顯示 · 可以檢舉不當內容', onSend: sendChat,
          collapseLabel: '收起', expandLabel: '展開聊天室', defaultOpen: window.innerWidth >= 640 }),
        h('div', { className: 'panel' }, h('h2', null, '這個時段'),
          (now.playlist || []).map(function (id, i) { return h(UpNext, { key: id + i, id: id, now: i === now.index }); })),
        now.next ? h('div', { className: 'panel' }, h('h2', null, '接下來 ' + now.next.range),
          h('b', null, now.next.title), h('span', { className: 'md-meta' }, now.next.count + ' 部 · ' + now.next.reason),
          now.next.influence ? h(M.InfluenceTag, null, now.next.influence) : null,
          h('a', { href: '/schedule', className: 'md-nav-a' }, '整週節目表')) : null));
  }

  /* ---------------------------------------------------------------- 手機：環境光沉浸（設計稿 M1）
     16:9 畫面置中，上下是同一畫面的模糊光暈；介面預設隱藏，點一下淡入、3 秒沒動作淡出；
     反應收成一顆「喜歡」，長按展開五種；長按畫面也送出喜歡。 */
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
  var ICON = {}; LIVE.forEach(function (o) { ICON[o.value] = o.icon; });

  function Immersive(p) {
    var item = p.item, now = p.now, slot = p.slot;
    var vref = React.useRef(null), cref = React.useRef(null), timer = React.useRef(null), press = React.useRef(null), seq = React.useRef(0);
    var _ui = React.useState(false), ui = _ui[0], setUi = _ui[1];
    var _sh = React.useState(null), sheet = _sh[0], setSheet = _sh[1];          // 'chat' | 'more' | null
    var _ex = React.useState(false), expanded = _ex[0], setExpanded = _ex[1];
    var _mu = React.useState(true), muted = _mu[0], setMuted = _mu[1];
    var _cc = React.useState(false), cc = _cc[0], setCc = _cc[1];
    var _fl = React.useState([]), floats = _fl[0], setFloats = _fl[1];
    var _hint = React.useState(true), hint = _hint[0], setHint = _hint[1];
    var _pr = React.useState(false), showPrev = _pr[0], setShowPrev = _pr[1];
    var _cool = React.useState(false), cool = _cool[0], setCool = _cool[1];
    var vertical = item.aspect === '9:16' || item.aspect === '4:5';

    // the site shell (header, footer, bottom nav) steps aside while watching
    React.useEffect(function () { document.body.classList.add('is-immersive'); return function () { document.body.classList.remove('is-immersive'); }; }, []);
    React.useEffect(function () { var t = setTimeout(function () { setHint(false); }, 4000); return function () { clearTimeout(t); }; }, []);

    // play from the schedule position
    React.useEffect(function () {
      var v = vref.current; if (!v) return;
      var off = now.offset || 0;
      function seek() { try { if (Math.abs(v.currentTime - off) > 1.5) v.currentTime = off; } catch (e) {} var pr = v.play(); if (pr && pr.catch) pr.catch(function () {}); }
      if (v.readyState >= 1) seek(); else v.addEventListener('loadedmetadata', seek, { once: true });
    }, [item.src, now.offset]);
    React.useEffect(function () { var v = vref.current; if (v && v.textTracks && v.textTracks[0]) v.textTracks[0].mode = cc ? 'showing' : 'hidden'; }, [cc, item.id]);

    // ambient light: a tiny copy of the current frame, blurred by CSS
    React.useEffect(function () {
      if (reducedMotion()) return;
      var id = setInterval(function () {
        var v = vref.current, c = cref.current;
        if (!v || !c || v.readyState < 2) return;
        try { c.getContext('2d').drawImage(v, 0, 0, c.width, c.height); } catch (e) {}
      }, 700);
      return function () { clearInterval(id); };
    }, [item.id]);

    // auto-hide after 3 s unless something is open
    var busy = !!sheet || expanded;
    function poke() {
      setUi(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(function () { if (!busy) setUi(false); }, 3000);
    }
    React.useEffect(function () { if (busy) clearTimeout(timer.current); else if (ui) poke(); }, [busy]);
    React.useEffect(function () { return function () { clearTimeout(timer.current); }; }, []);

    // the video that just finished asks for a reaction for 8 s
    React.useEffect(function () {
      if (!p.prev) return;
      setShowPrev(true);
      var t = setTimeout(function () { setShowPrev(false); }, 8000);
      return function () { clearTimeout(t); };
    }, [p.prev && p.prev.id]);

    function spawn(map, mine) {
      if (p.hidden || reducedMotion() || !map) return;
      var add = [];
      Object.keys(map).forEach(function (k) {
        for (var i = 0; i < Math.min(map[k], 12); i++) add.push({ id: ++seq.current, icon: ICON[k] || 'heart', x: Math.round(Math.random() * 56), d: Math.round(Math.random() * 500), mine: mine });
      });
      if (!add.length) return;
      setFloats(function (f) { return f.concat(add).slice(-36); });
      var ids = add.map(function (a) { return a.id; });
      setTimeout(function () { setFloats(function (f) { return f.filter(function (x) { return ids.indexOf(x.id) < 0; }); }); }, 2700);
    }
    React.useEffect(function () { spawn(p.tick.reactions, false); }, [p.tick.reactions]);

    function send(kind) {
      if (cool) return;
      setCool(true); setTimeout(function () { setCool(false); }, 2000);
      var m = {}; m[kind] = 1; spawn(m, true);
      p.react(kind);
    }

    // tap the picture = show / hide the interface; long-press = like
    function stageDown() { press.current = setTimeout(function () { press.current = 'fired'; send('like'); }, 500); }
    function stageUp() {
      if (press.current === 'fired') { press.current = null; return; }
      clearTimeout(press.current); press.current = null;
      if (expanded) { setExpanded(false); return; }
      if (ui) { clearTimeout(timer.current); setUi(false); } else poke();
    }
    // the heart: tap = like, long-press = the five reactions
    function heartDown(e) { e.stopPropagation(); press.current = setTimeout(function () { press.current = 'fired'; setExpanded(true); }, 450); }
    function heartUp(e) {
      e.stopPropagation();
      if (press.current === 'fired') { press.current = null; return; }
      clearTimeout(press.current); press.current = null;
      send('like'); poke();
    }
    function rotate() {
      var el = document.documentElement;
      var go = el.requestFullscreen ? el.requestFullscreen() : null;
      Promise.resolve(go).then(function () { if (screen.orientation && screen.orientation.lock) return screen.orientation.lock('landscape'); }).catch(function () {});
    }

    var span = slot.end - slot.start, done = Math.max(0, Math.min(1, ((p.tick.at || now.server_time || Date.now() / 1000) - slot.start) / span));
    var msgs = (p.chat.messages || []).slice(-3);
    var sp = p.sp, voted = sp && p.slotVotes[sp.slot];
    var iconBtn = function (name, label, onClick, extra) {
      return h('button', Object.assign({ type: 'button', className: 'imv-ibtn', 'aria-label': label, title: label, onClick: function (e) { e.stopPropagation(); poke(); onClick(); } }, extra || {}), h(M.Icon, { name: name, size: 18 }));
    };

    return h('div', { className: 'imv' + (ui ? ' is-ui' : '') + (vertical ? ' is-vertical' : '') },
      h('h1', { className: 'md-sr' }, '官方頻道直播：' + item.title),
      h('div', { className: 'imv-amb', 'aria-hidden': 'true', style: { backgroundImage: 'url(' + item.image + ')' } }, h('canvas', { ref: cref, width: 32, height: 18 })),
      h('div', { className: 'imv-shade', 'aria-hidden': 'true' }),
      h('div', { className: 'imv-stage', onPointerDown: stageDown, onPointerUp: stageUp, onPointerLeave: function () { if (press.current && press.current !== 'fired') clearTimeout(press.current); } },
        h('video', { ref: vref, className: 'imv-video', src: item.src, poster: item.image, muted: muted, playsInline: true, autoPlay: true, preload: 'auto',
          onEnded: p.ended, onTimeUpdate: function (e) { p.onTime(e.target.currentTime); }, 'aria-label': '官方頻道直播：' + item.title },
          item.captions ? h('track', { kind: 'subtitles', src: item.captions, srcLang: 'zh-Hant', label: '字幕' }) : null)),

      // always on: LIVE, the slot progress line, floating reactions, the first-time hint
      h('span', { className: 'imv-live' }, h(M.Badge, { tone: 'live' })),
      h('div', { className: 'imv-progress', role: 'progressbar', 'aria-label': '這個時段的進度', 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': Math.round(done * 100) },
        h('span', { style: { width: (done * 100) + '%' } })),
      h('div', { className: 'imv-floats', 'aria-hidden': 'true' }, floats.map(function (f) {
        return h('span', { key: f.id, className: 'md-float' + (f.mine ? ' is-mine' : ''), style: { left: f.x + 'px', animationDelay: f.d + 'ms' } }, h(M.Icon, { name: f.icon, size: 22 }));
      })),
      hint && !ui ? h('span', { className: 'imv-hint' }, '點一下畫面顯示資訊　·　長按送出喜歡') : null,
      muted && !ui ? h('button', { type: 'button', className: 'imv-unmute', onPointerDown: function (e) { e.stopPropagation(); }, onPointerUp: function (e) { e.stopPropagation(); },
        onClick: function (e) { e.stopPropagation(); setMuted(false); } }, h(M.Icon, { name: 'sound-off', size: 16 }), '開啟聲音') : null,

      // revealed on tap
      h('div', { className: 'imv-top' },
        iconBtn('back', '離開直播', function () { if (history.length > 1) history.back(); else location.href = '/'; }, { className: 'imv-ibtn imv-back' }),
        h('span', { className: 'imv-top-badges' }, h(M.Badge, { tone: 'live' }), h(M.Badge, { tone: 'neutral', dot: false }, 'Midea 官方頻道')),
        h(M.ViewerCount, { count: p.tick.viewers, onImage: true, label: function (n) { return n + ' 人正在看'; } })),
      h('div', { className: 'imv-title' },
        h('span', { className: 'imv-eyebrow' }, slot.range + '　' + slot.title + ' · 第 ' + (now.index + 1) + ' / ' + now.of + ' 部'),
        h('span', { className: 'imv-name' }, item.title),
        h('span', { className: 'imv-meta' }, [item.kind, item.duration_label, p.cast].filter(Boolean).join(' · ')),
        slot.influence ? h(M.InfluenceTag, null, slot.influence) : null),
      h('div', { className: 'imv-ctl' },
        h('span', { className: 'imv-ctl-l' },
          iconBtn(muted ? 'sound-off' : 'sound', muted ? '開啟聲音' : '靜音', function () { setMuted(!muted); }),
          item.captions ? iconBtn('cc', cc ? '關閉字幕' : '開啟字幕', function () { setCc(!cc); }, { 'aria-pressed': cc ? 'true' : 'false' }) : null),
        iconBtn('rotate', '橫向全螢幕', rotate)),
      h('ol', { className: 'imv-ticker', 'aria-label': '最新聊天', onClick: function (e) { e.stopPropagation(); setSheet('chat'); } }, msgs.map(function (m, i) {
        return h('li', { key: m.id, style: { opacity: [0.45, 0.7, 1][i + 3 - msgs.length] } }, h('b', null, m.nickname), m.text);
      })),
      h('div', { className: 'imv-bar' },
        h('button', { type: 'button', className: 'imv-say', onClick: function (e) { e.stopPropagation(); setSheet('chat'); } }, p.me && p.me.restriction ? p.me.restriction : '說點什麼…'),
        h('button', { type: 'button', className: 'imv-heart', 'aria-label': '喜歡（長按換其他反應）', disabled: cool,
          onPointerDown: heartDown, onPointerUp: heartUp, onContextMenu: function (e) { e.preventDefault(); } }, h(M.Icon, { name: 'heart', size: 22 })),
        iconBtn('list', '更多：收藏、分享、這個時段', function () { setSheet('more'); })),

      // long-press the heart: the five reactions
      expanded ? h('div', { className: 'imv-reacts', role: 'group', 'aria-label': '即時反應' }, LIVE.map(function (o) {
        return h('button', { key: o.value, type: 'button', className: 'imv-react', 'aria-label': o.label, title: o.label,
          onClick: function (e) { e.stopPropagation(); send(o.value); setExpanded(false); poke(); } }, h(M.Icon, { name: o.icon, size: 21 }));
      })) : null,

      // the last 60 seconds of a slot: will you watch it again next week?
      expanded ? null : sp ? h('div', { className: 'imv-card', onClick: function (e) { e.stopPropagation(); } },
        h('span', { className: 'imv-card-eyebrow' }, '這個時段再 ' + sp.ends_in + ' 秒結束'),
        h('span', { className: 'imv-card-title' }, '下週還想看「' + sp.title + '」嗎？'),
        voted ? h('span', { className: 'md-meta' }, '已收到，結果會進下週排程') :
          h('span', { className: 'imv-card-row' }, h(M.Button, { onClick: function () { p.slotVote('want'); } }, '想'), h(M.Button, { variant: 'ghost', onClick: function () { p.slotVote('no'); } }, '不想')))
      : (showPrev && p.prev ? h('div', { className: 'imv-card', onClick: function (e) { e.stopPropagation(); } },
        h('span', { className: 'imv-card-eyebrow' }, '剛播完'),
        h('span', { className: 'imv-card-title' }, '《' + p.prev.title + '》，你覺得？'),
        h(M.ReactionBar, { compact: true, options: REACT, value: p.prevReaction, onChange: function (k, r) { p.setReaction(k, r); setShowPrev(!!(k === 'not_interested' && !r)); },
          reasons: REASONS, reasonPrompt: '可以告訴我們原因（可略過）', skipLabel: '略過' })) : null),

      // sheets
      sheet ? h('div', { className: 'imv-backdrop', onClick: function () { setSheet(null); } }) : null,
      sheet === 'chat' ? h('div', { className: 'imv-sheet', role: 'dialog', 'aria-label': '聊天室' },
        h(M.ChatPanel, { title: '聊天室', meta: p.tick.viewers ? p.tick.viewers + ' 人正在看' : null, pinned: p.chat.pinned, pinnedLabel: '官方',
          messages: p.chat.messages, onReport: function (m) { S.report('chat', m.id); }, reportLabel: '檢舉這則訊息',
          signedIn: !!p.me, onSignIn: function () { S.openSignIn(); }, signInLabel: '以 CAFECA 登入後聊天',
          placeholder: p.me && p.me.restriction ? p.me.restriction : '說點什麼（最多 100 字）', inputLabel: '聊天訊息', sendLabel: '送出', max: 100,
          disabled: !!(p.me && p.me.restriction), notice: p.chatNote, hint: '每 5 秒 1 則 · 訊息先經過審核才顯示', onSend: p.sendChat,
          collapseLabel: '收起', expandLabel: '展開', defaultOpen: true }),
        h('button', { type: 'button', className: 'imv-ibtn imv-sheet-x', 'aria-label': '關閉聊天室', onClick: function () { setSheet(null); } }, h(M.Icon, { name: 'x', size: 18 }))) : null,
      sheet === 'more' ? h('div', { className: 'imv-sheet imv-more', role: 'dialog', 'aria-label': '更多' },
        h('div', { className: 'imv-sheet-head' }, h('b', null, item.title), h('button', { type: 'button', className: 'imv-ibtn', 'aria-label': '關閉', onClick: function () { setSheet(null); } }, h(M.Icon, { name: 'x', size: 18 }))),
        h('div', { className: 'imv-more-acts' },
          h(M.Button, { variant: 'ghost', icon: 'bookmark', onClick: p.toggleFav }, p.fav ? '已收藏' : '收藏'),
          h(M.Button, { variant: 'ghost', icon: 'share', onClick: function () { S.share('/watch/' + item.id).then(function () { S.toast('已複製連結'); }); } }, '分享'),
          h(M.Button, { variant: 'ghost', onClick: p.toggleHidden }, p.hidden ? '顯示畫面上的反應' : '關閉畫面上的反應')),
        slot.reason ? h(M.Tag, null, 'AI 排入理由：' + slot.reason) : null,
        h('h2', null, '這個時段'),
        (now.playlist || []).map(function (id, i) { return h(UpNext, { key: id + i, id: id, now: i === now.index }); }),
        now.next ? h('div', { className: 'imv-next' }, h('span', { className: 'md-meta' }, '接下來 ' + now.next.range), h('b', null, now.next.title),
          now.next.influence ? h(M.InfluenceTag, null, now.next.influence) : null, h('a', { href: '/schedule', className: 'md-nav-a' }, '整週節目表')) : null,
        h(M.AIDisclosure, null, '官方頻道的節目由 AI 從平台影片排定；影片由 AI 製作，演員皆為虛擬角色。')) : null);
  }

  var cache = {};
  function UpNext(p) {
    var _v = React.useState(cache[p.id] || null), v = _v[0], set = _v[1];
    React.useEffect(function () { if (!v) S.api('/videos/' + p.id).then(function (j) { cache[p.id] = j.video; set(j.video); }).catch(function () {}); }, [p.id]);
    if (!v) return null;
    return h('a', { className: 'upnext' + (p.now ? ' is-now' : ''), href: '/watch/' + v.id, 'aria-current': p.now ? 'true' : undefined },
      h('img', { src: v.image, alt: '' }), h('span', null, h('b', null, v.title), h('span', { className: 'md-meta' }, (p.now ? '現正播放 · ' : '') + v.duration_label)));
  }

  S.mount(Live);
})();
