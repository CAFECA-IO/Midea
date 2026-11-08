/* 首頁（A3 拼貼）＋第一期互動：直播磚的「N 人正在看」、觀眾決定投票磚、主打時段的影響標籤 */
(function () {
  var React = window.React, h = React.createElement, M = window.Midea, S = window.Site;

  function useHome() {
    var _d = React.useState(null), d = _d[0], set = _d[1];
    var me = S.useMe();
    React.useEffect(function () { S.api('/home').then(set).catch(function () { set({ error: true }); }); }, [me && me.account]);
    return [d, set];
  }

  function useViewers() {
    var _v = React.useState(null), v = _v[0], set = _v[1];
    React.useEffect(function () {
      if (!window.EventSource) return;
      var es = new EventSource('/api/public/v1/live/stream');
      es.onmessage = function (e) { try { var j = JSON.parse(e.data); if ('viewers' in j) set(j.viewers); } catch (x) {} };
      return function () { es.close(); };
    }, []);
    return v;
  }

  /* ------------------------------------------------------------ 首屏 */
  function Hero(p) {
    var d = p.d, live = d.live || {}, item = live.item, slot = live.slot, viewers = useViewers();
    var tiles = [];
    if (item) {
      tiles.push(h(M.VideoTile, { key: 'live', size: 'hero', cols: 2, rows: 2, href: '/live', image: item.image, alt: item.title,
        badge: h(M.Badge, { tone: 'now' }, '官方頻道 · 現正播放'),
        corner: h(M.ViewerCount, { count: viewers, onImage: true, label: function (n) { return n + ' 人正在看'; } }),
        eyebrow: slot.range + '　' + slot.title + ' · 第 ' + (live.index + 1) + ' / ' + live.of + ' 部',
        title: item.title,
        action: h('span', { className: 'hero-act' }, h(M.Button, { variant: 'light', size: 'lg', icon: 'play', href: '/live' }, '收看直播'),
          h('span', { className: 'md-vtile-sub' }, '直播中可以按即時反應，時段結束前可以決定下週要不要再播')) }));
    } else {
      tiles.push(h(M.EmptyState, { key: 'live', cols: 2, rows: 2, title: '官方頻道準備中', body: '平台上還沒有可以播出的影片。' }));
    }
    var nx = live.next;
    if (nx) tiles.push(h(M.VideoTile, { key: 'next', image: nx.image, title: nx.title, eyebrow: '下一個時段 ' + nx.range.split('–')[0],
      subtitle: nx.count + ' 部', href: '/schedule' }));
    var poll = d.poll, vert = d.verticals && d.verticals[0];
    if (poll && !poll.closed) {
      tiles.push(h(HeroPoll, { key: 'poll', poll: poll, onPoll: p.onPoll }));
      if (vert) tiles.push(h(M.VideoTile, { key: 'vert', image: vert.image, title: '滑著看的 ' + (vert.length === '15s' ? '15 秒' : vert.duration_label),
        eyebrow: '直式短片 · ' + d.verticals.length + ' 部', href: '/watch/' + vert.id, focus: 'top' }));
    } else {
      if (vert) tiles.push(h(M.VideoTile, { key: 'vert', rows: 2, image: vert.image, title: vert.title, eyebrow: '直式短片 · ' + d.verticals.length + ' 部',
        href: '/watch/' + vert.id, focus: 'top' }));
      var t = d.topics && d.topics[0];
      if (poll && poll.closed && poll.winner) {
        var w = poll.options.filter(function (o) { return o.id === poll.winner; })[0];
        tiles.push(h(M.ThemeTile, { key: 'theme', eyebrow: '觀眾投票選出 · ' + (poll.slot_label || ''), title: w ? w.title : '', note: '第 1 名 ' + (w && w.votes) + ' 票，共 ' + poll.votes + ' 票', href: '/schedule' }));
      } else if (t) {
        tiles.push(h(M.ThemeTile, { key: 'theme', eyebrow: '本週主題', title: t.title, note: t.meta, href: '#topics' }));
      }
    }
    return h(M.BentoGrid, { row: 'hero' }, tiles);
  }

  function HeroPoll(p) {
    var poll = p.poll, me = S.useMe();
    var _b = React.useState(false), busy = _b[0], setBusy = _b[1];
    function vote(id) {
      S.requireLogin(function () {
        setBusy(true);
        S.api('/polls/' + poll.id + '/vote', { method: 'POST', body: { option: id } }).then(function (j) { p.onPoll(j.poll); })
          .catch(function (e) { S.toast(e.message); }).then(function () { setBusy(false); });
      });
    }
    var voted = poll.mine != null;
    var choice = voted && poll.options.filter(function (o) { return o.id === poll.mine; })[0];
    return h(M.PollCard, { variant: 'tile', rows: 2, eyebrow: '觀眾決定 · ' + (poll.slot_label || ''), title: poll.title.replace(/^.*，/, ''),
      optionsLabel: '候選時段', value: poll.mine,
      options: poll.options.map(function (o) { return { id: o.id, title: o.title, sub: o.why, images: o.images, share: o.share }; }),
      cta: busy ? '送出中' : (me ? '投這一個' : '投這一個（以 CAFECA 登入）'), onVote: vote,
      note: voted ? '已投給「' + (choice && choice.title) + '」· 共 ' + poll.votes + ' 票 · ' + poll.closes_label + ' 截止，結果寫在節目表上'
        : '投票中 · ' + poll.closes_label + ' 截止 · 每個 CAFECA 身分一票' });
  }

  /* ------------------------------------------------------------ 本週每晚 */
  function Nightly(p) {
    var d = p.d;
    if (!d.nightly || !d.nightly.length) return null;
    return h('section', { className: 'sec', 'aria-labelledby': 'nightly' },
      h(M.SectionHeader, { id: 'nightly', title: '本週每晚的主打時段', action: h('a', { href: '/schedule', className: 'md-nav-a' }, '整週節目表') }),
      h('div', { className: 'days' }, d.nightly.map(function (n) {
        return h(M.DaySlot, { key: n.id, day: (n.today ? '今晚 · ' : '') + n.day, title: n.title, time: n.time, today: n.today, href: '/schedule',
          tag: n.influence ? h(M.InfluenceTag, null, n.influence) : null });
      })),
      d.schedule_note ? h('p', { className: 'md-meta sec-meta' }, d.schedule_note + ' · 下週節目表每週一 09:00 公布') : null);
  }

  /* ------------------------------------------------------------ 最多人看 */
  function Ranking(p) {
    var _t = React.useState('week'), per = _t[0], setPer = _t[1];
    var r = p.d.ranking[per] || { rows: [] }, rows = r.rows;
    var top = rows.slice(0, 5), rest = rows.slice(5, 10);
    var tabs = h(M.SegmentedTabs, { label: '排行期間', value: per, onChange: setPer,
      options: [{ value: 'today', label: '今天' }, { value: 'week', label: '本週' }, { value: 'month', label: '本月' }] });
    return h('section', { className: 'sec', 'aria-labelledby': 'rank' },
      h(M.SectionHeader, { id: 'rank', title: '最多人看', tag: '大家都在看', action: tabs }),
      rows.length ? h(M.BentoGrid, { row: 'rank' }, top.map(function (x, i) {
        return h(M.RankTile, { key: x.id, rank: x.rank, image: x.image, title: x.title, subtitle: i === 0 ? M_line(x) : x.duration_label,
          move: x.move, cols: i === 0 ? 2 : 1, rows: i === 0 ? 2 : 1, href: '/watch/' + x.id });
      })) : h(M.EmptyState, { title: '還沒有足夠的觀看紀錄', body: '最多人看只計算完整看完的次數，每小時更新一次。' }),
      rest.length ? h('div', { className: 'rank-rows' }, rest.map(function (x) {
        return h(M.RankRow, { key: x.id, rank: x.rank, image: x.image, title: x.title, move: x.move, href: '/watch/' + x.id });
      })) : null,
      h('p', { className: 'md-meta sec-meta' }, '依完整看完的次數排序 · 每小時更新 · 上次更新 ' + r.at));
  }
  function M_line(x) { return [x.kind, x.duration_label, x.views + ' 次看完'].join(' · '); }

  /* ------------------------------------------------------------ 主題 */
  function Topics(p) {
    var ts = (p.d.topics || []).slice(0, 3);
    if (!ts.length) return null;
    return h('section', { className: 'sec', id: 'topics', 'aria-label': '依興趣的主題' }, ts.map(function (t, i) {
      return h(M.TopicBento, { key: t.key, id: 'topic-' + i, title: t.title, meta: t.meta, level: 2,
        tagNode: t.personal ? h(M.Tag, null, t.reason) : (t.reason ? h(M.Tag, null, t.reason) : null),
        videos: t.videos.map(function (v) { return { image: v.image, title: v.title, subtitle: S.videoLine(v), href: '/watch/' + v.id, focus: v.aspect === '4:5' ? 'top' : null }; }) });
    }));
  }

  /* ------------------------------------------------------------ 演員與登入 */
  function Actors(p) {
    var me = S.useMe(), as = p.d.actors || [];
    return h('section', { className: 'sec', id: 'actors', 'aria-labelledby': 'cast' },
      h(M.SectionHeader, { id: 'cast', title: '平台演員', meta: '演員皆為虛擬角色' }),
      h('div', { className: 'actors' }, as.map(function (a) {
        return h(M.ActorCard, { key: a.handle, image: a.image, name: a.name, handle: a.handle, role: a.role,
          works: a.works ? a.works + ' 部作品' : '自我介紹', href: a.intro ? '/watch/' + a.intro : '#' });
      }).concat(me ? [] : [h('div', { key: 'signin', className: 'signin-card' },
        h('b', null, '登入後，主題會依你的觀看歸納'),
        h('p', null, '以 CAFECA 登入：用裝置上的通行金鑰，不需要密碼、不必另外註冊。登入後可以收藏、參加「觀眾決定」投票，主題與觀看紀錄跨裝置同步。'),
        h(M.SignInButton, { variant: 'outline', onClick: function () { S.openSignIn(); } }))])));
  }

  function Favorites() {
    var me = S.useMe();
    var _f = React.useState(null), favs = _f[0], set = _f[1];
    React.useEffect(function () { if (me) S.api('/me/favorites').then(function (j) { set(j.videos); }).catch(function () {}); else set(null); }, [me && me.account]);
    if (!me || !favs || !favs.length) return null;
    return h('section', { className: 'sec', id: 'favorites', 'aria-labelledby': 'fav' },
      h(M.SectionHeader, { id: 'fav', title: '我的收藏', meta: favs.length + ' 部' }),
      h('div', { className: 'related' }, favs.map(function (v) {
        return h(M.VideoTile, { key: v.id, image: v.image, title: v.title, subtitle: S.videoLine(v), href: '/watch/' + v.id, size: 'sm' });
      })));
  }

  function Home() {
    var _h = useHome(), d = _h[0], set = _h[1];
    if (!d) return h(M.BentoGrid, { row: 'hero' }, h(M.Skeleton, { cols: 2, rows: 2 }), h(M.Skeleton), h(M.Skeleton, { rows: 2 }), h(M.Skeleton));
    if (d.error) return h(M.EmptyState, { title: '暫時載入不了', body: '請稍後重新整理。' });
    function onPoll(poll) { set(Object.assign({}, d, { poll: poll })); }
    return h(React.Fragment, null,
      h('h1', { className: 'md-sr' }, 'Midea 首頁'),
      h(Hero, { d: d, onPoll: onPoll }), h(Nightly, { d: d }), h(Ranking, { d: d }), h(Topics, { d: d }), h(Favorites), h(Actors, { d: d }));
  }

  S.mount(Home);
})();
