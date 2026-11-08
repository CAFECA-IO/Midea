/* 主題頁：主題名稱、推薦理由、歸納時間與部數、全部影片 */
(function () {
  var React = window.React, h = React.createElement, M = window.Midea, S = window.Site;
  function Topic() {
    var key = decodeURIComponent(location.pathname.split('/').pop() || '');
    var _d = React.useState(null), d = _d[0], set = _d[1];
    React.useEffect(function () { S.api('/topics/' + encodeURIComponent(key)).then(function (j) { set(j); document.title = j.title + ' · Midea'; }).catch(function (e) { set({ error: e.message }); }); }, [key]);
    if (!d) return h(M.Skeleton, { height: 360 });
    if (d.error) return h(M.EmptyState, { title: '這個主題已經重新歸納', body: d.error, action: h(M.Button, { variant: 'ghost', href: '/#topics' }, '看最新的主題') });
    var vs = d.videos;
    return h(React.Fragment, null,
      h(M.TopicHeader, { eyebrow: '主題', title: d.title, meta: d.meta,
        tags: [d.influence ? h(M.InfluenceTag, { key: 'i' }, d.influence) : null, d.reason ? h(M.Tag, { key: 't' }, d.reason) : null] }),
      h(M.TopicBento, { title: '精選', level: 2, videos: vs.slice(0, 5).map(function (v) { return { image: v.image, title: v.title, subtitle: S.videoLine(v), href: '/watch/' + v.id, focus: v.aspect === '4:5' ? 'top' : null }; }) }),
      vs.length > 5 ? h('div', { className: 'sec related' }, vs.slice(5).map(function (v) {
        return h(M.VideoTile, { key: v.id, image: v.image, title: v.title, subtitle: S.videoLine(v), href: '/watch/' + v.id, size: 'sm' });
      })) : null,
      h('p', { className: 'md-meta sec-meta' }, '主題由 AI 每 6 小時（02:00、08:00、14:00、20:00）依觀看與反應重新歸納。'));
  }
  S.mount(Topic);
})();
