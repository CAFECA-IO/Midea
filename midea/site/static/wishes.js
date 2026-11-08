/* 許願牆：許願（主題或演員組合）、+1、狀態篩選、檢舉 */
(function () {
  var React = window.React, h = React.createElement, M = window.Midea, S = window.Site;
  var STATUS = { open: '征求中', topic: '已成為主題', producing: '製作中', done: '已完成' };
  var KIND = { topic: '主題', cast: '演員組合' };

  function cardProps(c, onChange, names) {
    var cast = (c.actors || []).map(function (hd) { return (names[hd] || hd) + ' @' + hd; }).join('、');
    return {
      key: c.id, kindLabel: KIND[c.kind] + (cast ? ' · ' + cast : ''), text: c.text, status: c.status, statusLabel: STATUS[c.status],
      progress: c.progress, progressLabel: '+1 進度', note: c.merged > 1 ? '合併了 ' + c.merged + ' 個相似的許願' : null,
      countLabel: c.supporters >= c.threshold ? c.supporters + ' 人 +1' : c.supporters + ' / ' + c.threshold + ' 人 +1',
      supported: c.mine, supportLabel: '+1', supportedLabel: '已 +1', reportLabel: '檢舉',
      onReport: function () { S.report('wish', c.id); },
      onSupport: function () {
        S.requireWriter(function () {
          S.api('/wishes/' + c.id + '/support', { method: c.mine ? 'DELETE' : 'POST' }).then(onChange).catch(function (e) { S.toast(e.message); });
        });
      }
    };
  }

  function Wishes() {
    var _d = React.useState(null), d = _d[0], set = _d[1];
    var _f = React.useState('all'), f = _f[0], setF = _f[1];
    var me = S.useMe();
    function load() { return S.api('/wishes' + (f === 'all' ? '' : '?status=' + f)).then(set); }
    React.useEffect(function () { load(); }, [f, me && me.account]);
    if (!d) return h(M.Skeleton, { height: 360 });
    var names = {}; d.actors.forEach(function (a) { names[a.handle] = a.name; });
    function submit(w) {
      return new Promise(function (ok) {
        S.requireWriter(function () {
          S.api('/wishes', { method: 'POST', body: w }).then(function (j) {
            S.toast(j.merged ? '已合併到相似的許願卡，並幫你 +1' : '已送出你的願望'); load(); ok(true);
          }).catch(function (e) { S.toast(e.message); ok(false); });
        });
      });
    }
    return h(React.Fragment, null,
      h(M.SectionHeader, { title: '許願牆', level: 1, meta: '+1 達 ' + d.threshold + ' 人，管理者核准後排進製作 · 平台已經有相關影片的，會在下一次主題歸納成為主題' }),
      h('div', { className: 'wish-layout' },
        h(M.WishComposer, { title: '我要許願', actors: d.actors, left: d.left, leftLabel: d.left == null ? '' : '本週還可以許 ' + d.left + ' 個',
          kindLabel: '許願類型', topicLabel: '主題', castLabel: '演員組合', castPick: '選 1–2 位演員',
          topicTextLabel: '想看什麼主題', topicPlaceholder: '例：下雨天的城市', castTextLabel: '一句情境', castPlaceholder: '例：在舊書店遇見',
          rules: '不接受真人（含公眾人物）、實際商品品牌與違反平台規則的內容。AI 會把意思相近的願望合併成一張卡。',
          footer: me ? '以 ' + me.nickname + ' 的身分許願' : '需要以 CAFECA 登入', submitLabel: '送出', onSubmit: submit, disabled: me && !!me.restriction }),
        h('div', { className: 'panel' }, h('h2', null, '願望會怎麼走'),
          h('ol', { className: 'wish-steps' },
            h('li', null, h('b', null, '征求中'), '大家 +1，AI 把意思相近的願望合併成同一張卡。'),
            h('li', null, h('b', null, '已成為主題'), '平台已經有相關影片時，下一次主題歸納（每 6 小時）就會排成主題，標「依觀眾許願」。'),
            h('li', null, h('b', null, '製作中'), '+1 達 ' + d.threshold + ' 人，管理者核准後用 Midea 的管線製作。'),
            h('li', null, h('b', null, '已完成'), '影片上架，許願與 +1 的人都會在這裡看到。')))),
      h('div', { className: 'sec' },
        h(M.SectionHeader, { title: '大家的願望', level: 2, action: h(M.SegmentedTabs, { label: '狀態', value: f, onChange: setF,
          options: [{ value: 'all', label: '全部' }, { value: 'open', label: '征求中' }, { value: 'topic', label: '已成為主題' }, { value: 'producing', label: '製作中' }, { value: 'done', label: '已完成' }] }) }),
        d.cards.length ? h('div', { className: 'wish-grid' }, d.cards.map(function (c) { return h(M.WishCard, cardProps(c, load, names)); }))
          : h(M.EmptyState, { title: '還沒有這類的願望', body: '寫下你想看的主題或演員組合，就會出現在這裡。' })));
  }

  window.WishCardProps = cardProps;
  if (document.getElementById('root') && /^\/wishes/.test(location.pathname)) S.mount(Wishes);
})();
