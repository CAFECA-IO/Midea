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
          disabled: !!(me && me.restriction), notice: chatNote, hint: '每 5 秒 1 則 · 訊息先經過審核才顯示 · 可以檢舉不當內容',
          collapseLabel: '收起', expandLabel: '展開聊天室', defaultOpen: window.innerWidth >= 640 }),
        h('div', { className: 'panel' }, h('h2', null, '這個時段'),
          (now.playlist || []).map(function (id, i) { return h(UpNext, { key: id + i, id: id, now: i === now.index }); })),
        now.next ? h('div', { className: 'panel' }, h('h2', null, '接下來 ' + now.next.range),
          h('b', null, now.next.title), h('span', { className: 'md-meta' }, now.next.count + ' 部 · ' + now.next.reason),
          now.next.influence ? h(M.InfluenceTag, null, now.next.influence) : null,
          h('a', { href: '/schedule', className: 'md-nav-a' }, '整週節目表')) : null));
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
