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
    var id = vid();

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

  S.mount(Watch);
})();
