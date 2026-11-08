/* 節目表：本週／下週每晚 20:00–24:00，觀眾決定的投票，影響標籤 */
(function () {
  var React = window.React, h = React.createElement, M = window.Midea, S = window.Site;

  function monday(offsetWeeks) {
    var d = new Date(); var wd = (d.getDay() + 6) % 7;
    d.setDate(d.getDate() - wd + 7 * offsetWeeks);
    return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
  }

  function Schedule() {
    var _w = React.useState('this'), wk = _w[0], setWk = _w[1];
    var _d = React.useState(null), d = _d[0], set = _d[1];
    var _p = React.useState(null), poll = _p[0], setPoll = _p[1];
    var me = S.useMe();
    React.useEffect(function () { set(null); S.api('/schedule?week=' + monday(wk === 'this' ? 0 : 1)).then(set).catch(function () { set({ days: [] }); }); }, [wk, poll && poll.mine]);
    React.useEffect(function () { S.api('/polls/current').then(function (j) { setPoll(j.poll); }).catch(function () {}); }, [me && me.account]);

    function vote(id) {
      S.requireLogin(function () {
        S.api('/polls/' + poll.id + '/vote', { method: 'POST', body: { option: id } }).then(function (j) { setPoll(j.poll); S.toast('已投票'); })
          .catch(function (e) { S.toast(e.message); });
      });
    }
    var tabs = h(M.SegmentedTabs, { label: '週次', value: wk, onChange: setWk, options: [{ value: 'this', label: '本週' }, { value: 'next', label: '下週' }] });
    return h(React.Fragment, null,
      h(M.SectionHeader, { title: '官方頻道節目表', level: 1, action: tabs }),
      poll && !poll.closed ? h(M.PollCard, { variant: 'full', eyebrow: '觀眾決定 · ' + (poll.slot_label || ''), title: poll.title, optionsLabel: '候選時段',
        value: poll.mine, allowChange: true,
        options: poll.options.map(function (o) { return { id: o.id, title: o.title, sub: o.why, images: o.images, share: o.share }; }),
        cta: me ? '投這一個' : '投這一個（以 CAFECA 登入）', onVote: vote,
        note: '候選由 AI 依本週熱度提出 · ' + poll.closes_label + ' 截止 · 每個 CAFECA 身分一票，截止前可以改投' +
          (poll.mine ? ' · 目前共 ' + poll.votes + ' 票' + kycNote(poll) : '') }) : null,
      !d ? h(M.Skeleton, { height: 320 }) :
        !d.days.length ? h(M.EmptyState, { title: '節目表還沒公布', body: d.note || '下週節目表每週一 09:00 公布。' }) :
          h('div', { className: 'sec' },
            d.published ? h('p', { className: 'md-meta' }, d.published + ' 由 AI 排定 · 每晚 20:00–24:00 主打時段，其餘時間全天輪播') : null,
            d.days.map(function (day) {
              return h('div', { key: day.day, className: 'sched-day' + (day.today ? ' is-today' : '') },
                h('h3', null, (day.today ? '今天 ' : '') + day.day),
                h('div', { className: 'sched-slots' }, day.slots.map(function (s) {
                  return h(M.DaySlot, { key: s.id, day: s.range + (s.now ? ' · 現正播放' : ''), title: s.title, time: s.count + ' 部' + (s.influence ? ' · ' + s.reason : ''),
                    today: s.now, href: s.now ? '/live' : '#', tag: s.influence ? h(M.InfluenceTag, null, s.influence) : null });
                })));
            })));
  }

  function kycNote(p) {
    var b = p.by_kyc; if (!b) return '';
    var verified = 0; Object.keys(b).forEach(function (k) { if (k !== 'unknown' && k !== '0') Object.keys(b[k]).forEach(function (o) { verified += b[k][o]; }); });
    return '（其中 ' + verified + ' 票來自通過 KYC 驗證的身分）';
  }

  S.mount(Schedule);
})();
