/* 影片頁：播放、反應（匿名可用）、收藏（CAFECA）、分享、觀眾最有反應的片段 */
(function () {
  var React = window.React, h = React.createElement, M = window.Midea, S = window.Site;
  var REACT = [{ value: 'like', label: '喜歡', icon: 'heart' }, { value: 'more', label: '想看更多這類', icon: 'plus' },
    { value: 'not_interested', label: '不感興趣', icon: 'x', askReason: true }];
  var REASONS = [{ value: 'topic', label: '主題不合' }, { value: 'seen', label: '看過了' }, { value: 'quality', label: '品質不好' }, { value: 'other', label: '其他' }];

  function vid() { return decodeURIComponent(location.pathname.split('/').pop() || ''); }

  function versionLabel(v) {
    var len = v.length === '60s' ? '60 秒' : v.length === '15s' ? '15 秒' : v.duration_label;
    var asp = { '16:9': '橫式', '9:16': '直式', '1:1': '方形', '4:5': '直式' }[v.aspect] || v.aspect;
    return len + ' · ' + asp;
  }

  function Watch() {
    var _d = React.useState(null), d = _d[0], set = _d[1];
    var _r = React.useState(null), reaction = _r[0], setReaction = _r[1];
    var _f = React.useState(false), fav = _f[0], setFav = _f[1];
    var _e = React.useState(false), ended = _e[0], setEnded = _e[1];
    var me = S.useMe(), tracker = React.useRef(null), pos = React.useRef(0);
    var id = vid(), mobile = S.useMobile();

    React.useEffect(function () {
      S.api('/videos/' + id).then(function (j) {
        set(j); setReaction(j.reaction); setFav(j.favorite);
        document.title = j.video.title + ' · Midea';
      }).catch(function () { set({ error: true }); });
      tracker.current = S.viewTracker(id);
      return function () { tracker.current.stop(); };
    }, [id, me && me.account]);

    // ?t=37 from a shared link
    React.useEffect(function () {
      var t = Number(new URLSearchParams(location.search).get('t') || 0);
      if (!d || !t) return;
      var v = document.querySelector('.md-vplayer video');
      if (v) v.addEventListener('loadedmetadata', function () { v.currentTime = t; }, { once: true });
    }, [d && d.video && d.video.id]);

    if (!d) return h(M.Skeleton, { height: 480 });
    if (d.error) return h(M.EmptyState, { title: '找不到這部影片', body: '它可能已經下架。', action: h(M.Button, { variant: 'ghost', href: '/' }, '回到首頁') });
    var v = d.video;

    function react(kind, reason) {
      setReaction(kind);
      (kind ? S.api('/videos/' + v.id + '/reaction', { method: 'POST', body: { kind: kind, reason: reason } })
        : S.api('/videos/' + v.id + '/reaction', { method: 'DELETE' })).catch(function (e) { S.toast(e.message); });
    }
    function toggleFav() {
      S.requireLogin(function () {
        var on = !fav; setFav(on);
        S.api('/videos/' + v.id + '/favorite', { method: on ? 'POST' : 'DELETE' }).then(function () { S.toast(on ? '已加入收藏' : '已移出收藏'); })
          .catch(function (e) { setFav(!on); S.toast(e.message); });
      });
    }

    if (mobile) return h(ImmersiveWatch, { d: d, reaction: reaction, react: react, fav: fav, toggleFav: toggleFav, tracker: tracker, pos: pos });
    return h('div', { className: 'watch-layout' },
      h(M.VideoPlayer, { src: v.src, poster: v.image, captions: v.captions, captionsLabel: '字幕', vertical: v.aspect === '9:16', autoPlay: true,
        duration: v.duration, label: v.title, highlights: d.highlights, highlightsLabel: '圓點是直播時觀眾最有反應的片段，點一下就跳過去',
        onProgress: function (t, dur, end) { pos.current = t; tracker.current.progress(t, dur, end); if (end) setEnded(true); } }),
      h(M.ReactionBar, { title: ended ? '看完了，你覺得？' : '你覺得這部片？', options: REACT, value: reaction, onChange: react,
        reasons: REASONS, reasonPrompt: '可以告訴我們原因（可略過）', skipLabel: '略過',
        note: '不用登入也可以按 · 「不感興趣」只會讓你少看到這類影片' }),
      h(M.VideoMeta, { eyebrow: v.subtitle || v.kind, title: v.title,
        meta: [v.duration_label, S.cast(v), v.created ? new Date(v.created * 1000).getMonth() + 1 + '/' + new Date(v.created * 1000).getDate() + ' 上架' : ''].filter(Boolean).join(' · '),
        tags: d.highlights && d.highlights.length ? [h(M.InfluenceTag, { key: 'h' }, '觀眾最有反應的片段 · ' + d.highlights.length + ' 段')] : null,
        actions: [h(M.Button, { key: 'f', variant: 'ghost', icon: 'bookmark', onClick: toggleFav }, fav ? '已收藏' : '收藏'),
          h(M.Button, { key: 's', variant: 'ghost', icon: 'share', onClick: function () { S.share('/watch/' + v.id, pos.current).then(function () { S.toast('已複製連結（從目前的秒數開始）'); }); } }, '分享')] }),
      d.versions.length > 1 ? h('div', { className: 'versions', role: 'group', 'aria-label': '版本' }, d.versions.map(function (x) {
        return h('a', { key: x.id, href: '/watch/' + x.id, className: 'md-chip md-chip-sm' + (x.id === v.id ? ' is-on' : ''), 'aria-current': x.id === v.id ? 'page' : undefined }, versionLabel(x));
      })) : null,
      v.description ? h('p', { className: 'body', style: { margin: 0, color: 'var(--ink-muted)' } }, v.description) : null,
      h(M.AIDisclosure, null, '本片由 AI 製作，演員皆為虛擬角色。畫面、聲音與配樂由 Midea 的本地模型生成。'),
      d.related.length ? h('section', { 'aria-labelledby': 'rel' },
        h(M.SectionHeader, { id: 'rel', title: '同主題的影片' }),
        h('div', { className: 'related' }, d.related.map(function (x) {
          return h(M.VideoTile, { key: x.id, image: x.image, title: x.title, subtitle: S.videoLine(x), href: '/watch/' + x.id, size: 'sm', focus: x.aspect === '4:5' ? 'top' : null });
        }))) : null);
  }

  /* ---------------------------------------------------------------- 手機：沉浸模式（與直播頁 M1 同一套）
     影像置中＋環境光；介面預設隱藏，點一下淡入（返回、片名、播放／暫停、聲音、字幕、橫向、進度與精華點、
     喜歡、更多），3 秒淡出。單擊喜歡＝喜歡（再按取消），長按＝喜歡／想看更多這類／不感興趣。
     播完出現小卡：你覺得？＋下一部（6 秒後自動播放，碰一下就取消）。 */
  function ImmersiveWatch(p) {
    var d = p.d, v = d.video;
    var vref = React.useRef(null);
    var _sh = React.useState(null), sheet = _sh[0], setSheet = _sh[1];
    var _ex = React.useState(false), expanded = _ex[0], setExpanded = _ex[1];
    var _rs = React.useState(false), askReason = _rs[0], setAskReason = _rs[1];
    var _mu = React.useState(true), muted = _mu[0], setMuted = _mu[1];
    var _cc = React.useState(false), cc = _cc[0], setCc = _cc[1];
    var _pl = React.useState(true), playing = _pl[0], setPlaying = _pl[1];
    var _t = React.useState({ t: 0, d: v.duration || 0 }), tm = _t[0], setTm = _t[1];
    var _end = React.useState(false), ended = _end[0], setEnded = _end[1];
    var _cd = React.useState(null), countdown = _cd[0], setCountdown = _cd[1];
    var _hint = React.useState(true), hint = _hint[0], setHint = _hint[1];
    var _scrub = React.useState(false), scrubbing = _scrub[0], setScrubbing = _scrub[1];
    var im = S.useImmersive(!!sheet || expanded || askReason || scrubbing || !playing);
    var vertical = v.aspect === '9:16' || v.aspect === '4:5';
    var next = d.related && d.related[0];

    React.useEffect(function () { var t = setTimeout(function () { setHint(false); }, 4000); return function () { clearTimeout(t); }; }, []);
    React.useEffect(function () {
      var el = vref.current; if (!el) return;
      var t0 = Number(new URLSearchParams(location.search).get('t') || 0);
      function start() { if (t0) { try { el.currentTime = t0; } catch (e) {} } var pr = el.play(); if (pr && pr.catch) pr.catch(function () { setPlaying(false); }); }
      if (el.readyState >= 1) start(); else el.addEventListener('loadedmetadata', start, { once: true });
    }, [v.id]);
    React.useEffect(function () { var el = vref.current; if (el && el.textTracks && el.textTracks[0]) el.textTracks[0].mode = cc ? 'showing' : 'hidden'; }, [cc, v.id]);
    // 下一部 in 6 seconds, unless the viewer touches anything
    React.useEffect(function () {
      if (countdown == null) return;
      if (countdown <= 0) { if (next) location.href = '/watch/' + next.id; return; }
      var t = setTimeout(function () { setCountdown(countdown - 1); }, 1000);
      return function () { clearTimeout(t); };
    }, [countdown]);

    function onTime(e) {
      var el = e.target; setTm({ t: el.currentTime, d: el.duration || v.duration || 0 });
      p.pos.current = Math.max(p.pos.current, el.currentTime);
      if (p.tracker.current) p.tracker.current.progress(p.pos.current, el.duration || 0, false);
    }
    function onEnded(e) {
      if (p.tracker.current) p.tracker.current.progress(e.target.duration, e.target.duration, true);
      setEnded(true); setPlaying(false); setExpanded(false); if (next) setCountdown(6);
    }
    function togglePlay() {
      var el = vref.current; if (!el) return;
      if (el.paused) { if (ended) { el.currentTime = 0; setEnded(false); setCountdown(null); } el.play(); setPlaying(true); } else { el.pause(); setPlaying(false); }
    }
    function seek(t) { var el = vref.current; if (el) { el.currentTime = t; setTm({ t: t, d: tm.d }); } }
    function react(kind, reason) {
      p.react(kind, reason);
      if (kind === 'not_interested' && !reason) setAskReason(true); else setAskReason(false);
      setExpanded(false);
      if (kind) S.toast(kind === 'like' ? '已按喜歡' : kind === 'more' ? '會多排這類影片給你' : '會少推這類影片給你');
    }
    function rotate() {
      var el = document.documentElement, go = el.requestFullscreen ? el.requestFullscreen() : null;
      Promise.resolve(go).then(function () { if (screen.orientation && screen.orientation.lock) return screen.orientation.lock('landscape'); }).catch(function () {});
    }
    var stage = S.pressHandlers(function () { if (expanded) { setExpanded(false); return; } setCountdown(null); im.toggle(); },
      function () { react(p.reaction === 'like' ? null : 'like'); });
    var heart = S.pressHandlers(function (e) { e.stopPropagation(); react(p.reaction === 'like' ? null : 'like'); im.poke(); },
      function (e) { e.stopPropagation(); setExpanded(true); }, 450);
    var ib = function (name, label, onClick, extra) {
      return h('button', Object.assign({ type: 'button', className: 'imv-ibtn', 'aria-label': label, title: label, onClick: function (e) { e.stopPropagation(); im.poke(); onClick(); } }, extra || {}), h(M.Icon, { name: name, size: 18 }));
    };
    var dur = tm.d || v.duration || 1;
    var liked = p.reaction === 'like', rKind = p.reaction;

    return h('div', { className: 'imv imv-vod' + (im.ui ? ' is-ui' : '') + (vertical ? ' is-vertical' : '') },
      h('h1', { className: 'md-sr' }, v.title),
      h(S.Ambient, { video: vref, image: v.image }),
      h('div', Object.assign({ className: 'imv-stage' }, stage),
        h('video', { ref: vref, className: 'imv-video', src: v.src, poster: v.image, muted: muted, playsInline: true, autoPlay: true, preload: 'auto', crossOrigin: 'anonymous',
          onTimeUpdate: onTime, onEnded: onEnded, onPlay: function () { setPlaying(true); }, onPause: function () { setPlaying(false); }, 'aria-label': v.title },
          v.captions ? h('track', { kind: 'subtitles', src: v.captions, srcLang: 'zh-Hant', label: '字幕' }) : null)),

      // always on: a thin playback line, the sound hint while muted
      h('div', { className: 'imv-progress', 'aria-hidden': 'true' }, h('span', { style: { width: Math.min(100, 100 * tm.t / dur) + '%' } })),
      muted && !im.ui ? h('button', { type: 'button', className: 'imv-unmute', onClick: function (e) { e.stopPropagation(); setMuted(false); } },
        h(M.Icon, { name: 'sound-off', size: 16 }), '開啟聲音') : null,
      hint && !im.ui ? h('span', { className: 'imv-hint' }, '點一下畫面顯示控制　·　長按喜歡') : null,

      // revealed on tap
      h('div', { className: 'imv-top' },
        ib('back', '返回', function () { if (history.length > 1) history.back(); else location.href = '/'; }),
        h('span', { className: 'imv-top-badges' }, h(M.Badge, { tone: 'neutral', dot: false }, v.subtitle || v.kind)),
        ib('list', '更多：版本、收藏、分享、同主題的影片', function () { setSheet('more'); })),
      h('div', { className: 'imv-title' },
        h('span', { className: 'imv-eyebrow' }, [v.kind, v.length === '15s' ? '15 秒版' : v.length === '60s' ? '60 秒版' : ''].filter(Boolean).join(' · ')),
        h('span', { className: 'imv-name' }, v.title),
        h('span', { className: 'imv-meta' }, [v.duration_label, S.cast(v)].filter(Boolean).join(' · ')),
        d.highlights && d.highlights.length ? h(M.InfluenceTag, null, '觀眾最有反應的片段 · ' + d.highlights.length + ' 段') : null),
      ended ? null : h('button', { type: 'button', className: 'imv-play', 'aria-label': playing ? '暫停' : (ended ? '重播' : '播放'),
        onClick: function (e) { e.stopPropagation(); im.poke(); togglePlay(); } }, h(M.Icon, { name: playing ? 'pause' : 'play', size: 30 })),
      h('div', { className: 'imv-ctl' },
        h('span', { className: 'imv-ctl-l' },
          ib(muted ? 'sound-off' : 'sound', muted ? '開啟聲音' : '靜音', function () { setMuted(!muted); }),
          v.captions ? ib('cc', cc ? '關閉字幕' : '開啟字幕', function () { setCc(!cc); }, { 'aria-pressed': cc ? 'true' : 'false' }) : null),
        vertical ? null : ib('rotate', '橫向全螢幕', rotate)),
      h('div', { className: 'imv-seek', onClick: function (e) { e.stopPropagation(); } },
        h('span', { className: 'imv-time' }, S.fmtTime(tm.t)),
        h('div', { className: 'imv-track' },
          h('input', { type: 'range', min: 0, max: dur, step: 0.1, value: tm.t, 'aria-label': '播放進度',
            onPointerDown: function () { setScrubbing(true); }, onPointerUp: function () { setScrubbing(false); im.poke(); },
            onChange: function (e) { seek(Number(e.target.value)); }, style: { '--p': Math.min(100, 100 * tm.t / dur) + '%' } }),
          (d.highlights || []).map(function (x, i) {
            return h('button', { key: i, type: 'button', className: 'imv-mark', style: { left: Math.min(100, 100 * ((x.start + x.end) / 2) / dur) + '%' },
              'aria-label': x.label + ' ' + S.fmtTime(x.start), title: x.label, onClick: function () { seek(x.start); im.poke(); } });
          })),
        h('span', { className: 'imv-time' }, S.fmtTime(dur))),
      h('div', { className: 'imv-bar imv-bar-vod' },
        h('button', Object.assign({ type: 'button', className: 'imv-heart' + (liked ? '' : ' is-off'), 'aria-pressed': liked ? 'true' : 'false',
          'aria-label': liked ? '已喜歡（再按取消；長按看其他反應）' : '喜歡（長按看其他反應）' }, heart), h(M.Icon, { name: 'heart', size: 22 })),
        h('span', { className: 'imv-react-note' }, rKind === 'more' ? '想看更多這類' : rKind === 'not_interested' ? '不感興趣' : liked ? '已喜歡' : '長按看其他反應'),
        ib('bookmark', p.fav ? '已收藏' : '收藏', p.toggleFav, { 'aria-pressed': p.fav ? 'true' : 'false' }),
        ib('share', '分享（從目前的秒數開始）', function () { S.share('/watch/' + v.id, tm.t).then(function () { S.toast('已複製連結'); }); })),

      // long-press the heart
      expanded ? h('div', { className: 'imv-reacts imv-reacts-vod', role: 'group', 'aria-label': '你覺得這部片？' }, REACT.map(function (o) {
        return h('button', { key: o.value, type: 'button', className: 'md-chip' + (rKind === o.value ? ' is-on' : ''), 'aria-pressed': rKind === o.value ? 'true' : 'false',
          onClick: function (e) { e.stopPropagation(); react(rKind === o.value ? null : o.value); im.poke(); } }, h(M.Icon, { name: o.icon, size: 16 }), o.label);
      })) : null,
      askReason ? h('div', { className: 'imv-card', onClick: function (e) { e.stopPropagation(); } },
        h('span', { className: 'imv-card-eyebrow' }, '不感興趣'), h('span', { className: 'imv-card-title' }, '可以告訴我們原因嗎？（可略過）'),
        h('div', { className: 'md-reactbar-opts' }, REASONS.map(function (r) {
          return h('button', { key: r.value, type: 'button', className: 'md-chip md-chip-sm', onClick: function () { react('not_interested', r.value); } }, r.label);
        }), h('button', { type: 'button', className: 'md-linkbtn', onClick: function () { setAskReason(false); } }, '略過'))) : null,

      // finished: how was it, and what plays next
      ended && !askReason ? h('div', { className: 'imv-card imv-endcard', onClick: function (e) { e.stopPropagation(); setCountdown(null); } },
        h('span', { className: 'imv-card-eyebrow' }, '看完了'),
        h('span', { className: 'imv-card-title' }, '《' + v.title + '》，你覺得？'),
        h(M.ReactionBar, { compact: true, options: REACT, value: rKind, onChange: function (k, r) { react(k, r); } }),
        next ? h('a', { className: 'imv-next-up', href: '/watch/' + next.id },
          h('img', { src: next.image, alt: '' }),
          h('span', null, h('span', { className: 'md-meta' }, countdown != null ? countdown + ' 秒後播放下一部' : '下一部'), h('b', null, next.title))) : null) : null,

      // more
      sheet ? h('div', { className: 'imv-backdrop', onClick: function () { setSheet(null); } }) : null,
      sheet === 'more' ? h('div', { className: 'imv-sheet imv-more', role: 'dialog', 'aria-label': '更多' },
        h('div', { className: 'imv-sheet-head' }, h('b', null, v.title), h('button', { type: 'button', className: 'imv-ibtn', 'aria-label': '關閉', onClick: function () { setSheet(null); } }, h(M.Icon, { name: 'x', size: 18 }))),
        v.description ? h('p', { className: 'imv-desc' }, v.description) : null,
        d.versions.length > 1 ? h('div', { className: 'versions', role: 'group', 'aria-label': '版本' }, d.versions.map(function (x) {
          return h('a', { key: x.id, href: '/watch/' + x.id, className: 'md-chip md-chip-sm' + (x.id === v.id ? ' is-on' : ''), 'aria-current': x.id === v.id ? 'page' : undefined }, versionLabel(x));
        })) : null,
        h(M.AIDisclosure, null, '本片由 AI 製作，演員皆為虛擬角色。'),
        d.related.length ? h('h2', null, '同主題的影片') : null,
        d.related.map(function (x) {
          return h('a', { key: x.id, className: 'upnext', href: '/watch/' + x.id }, h('img', { src: x.image, alt: '' }),
            h('span', null, h('b', null, x.title), h('span', { className: 'md-meta' }, S.videoLine(x))));
        })) : null);
  }

  S.mount(Watch);
})();
