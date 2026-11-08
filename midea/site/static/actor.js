/* 演員頁：介紹、作品、向演員提問（文字回覆標「AI 生成 · 虛擬演員」）、大家想問的（+1）、影片回答 */
(function () {
  var React = window.React, h = React.createElement, M = window.Midea, S = window.Site;
  var AI = 'AI 生成 · 虛擬演員';

  function handle() { return decodeURIComponent(location.pathname.split('/').pop() || ''); }

  function Actor() {
    var hd = handle(), me = S.useMe();
    var _d = React.useState(null), d = _d[0], set = _d[1];
    var _q = React.useState(null), qs = _q[0], setQs = _q[1];
    var _o = React.useState('top'), order = _o[0], setOrder = _o[1];
    function loadQ() { return S.api('/actors/' + hd + '/questions?order=' + order).then(setQs); }
    React.useEffect(function () { S.api('/actors/' + hd).then(function (j) { set(j); document.title = j.actor.name + ' · Midea'; }).catch(function () { set({ error: true }); }); }, [hd, me && me.account]);
    React.useEffect(function () { loadQ(); }, [hd, order, me && me.account]);
    // the actor's text reply is written in the background — check again while one is pending
    React.useEffect(function () {
      if (!qs || !qs.mine.some(function (q) { return q.reply_status === 'pending'; })) return;
      var t = setTimeout(loadQ, 8000); return function () { clearTimeout(t); };
    }, [qs]);
    if (!d) return h(M.Skeleton, { height: 420 });
    if (d.error) return h(M.EmptyState, { title: '找不到這位演員', action: h(M.Button, { variant: 'ghost', href: '/#actors' }, '看所有演員') });
    var a = d.actor;
    function ask(text) {
      return new Promise(function (ok) {
        S.requireWriter(function () {
          S.api('/actors/' + hd + '/questions', { method: 'POST', body: { text: text } }).then(function (j) {
            set(Object.assign({}, d, { left: j.left })); loadQ(); ok(true);
          }).catch(function (e) { S.toast(e.message); ok(false); });
        });
      });
    }
    function support(q) {
      S.requireWriter(function () {
        S.api('/questions/' + q.id + '/support', { method: q.supported ? 'DELETE' : 'POST' }).then(loadQ).catch(function (e) { S.toast(e.message); });
      });
    }
    var mine = (qs && qs.mine || []).slice(0, 3).map(function (q) {
      return { id: q.id, question: q.text, reply: q.reply_status === 'ready' ? q.reply : q.reply_status === 'declined' ? (q.reply || a.name + '這次沒有回答這個問題。') : null };
    });
    return h(React.Fragment, null,
      h('section', { className: 'actor-top', 'aria-labelledby': 'actor-name' },
        h('div', { className: 'panel actor-card' },
          h('div', { className: 'actor-id' }, h('img', { src: a.image, alt: a.name }),
            h('div', null, h(M.Badge, { tone: 'neutral', dot: false }, a.official ? '平台演員 · 虛擬角色' : '創作者演員 · 虛擬角色'),
              h('h1', { id: 'actor-name', className: 'actor-name' }, a.name), h('span', { className: 'md-meta' }, '@' + a.handle + (a.role ? ' · ' + a.role : '') + (a.age ? ' · ' + a.age + ' 歲' : '')))),
          a.bio ? h('p', { className: 'actor-bio' }, a.bio) : null,
          h('div', { className: 'stat-row' }, stat(d.counts.works, '部作品'), stat(d.counts.questions, '則提問'), stat(d.counts.answers, '支影片回答'))),
        d.intro ? h(M.VideoTile, { image: d.intro.image, title: d.intro.title, subtitle: d.intro.description, eyebrow: '自我介紹 · ' + d.intro.duration_label,
          href: '/watch/' + d.intro.id, size: 'md', focus: 'top', badge: h(M.Badge, { tone: 'neutral', dot: false }, 'AI 生成') }) : null),
      h('section', { className: 'sec ask-layout', 'aria-label': '提問' },
        h(M.AskActor, { title: '問' + a.name + '一個問題', inputLabel: '你的問題', placeholder: '例：下雨天店裡沒客人的時候，你都在做什麼？',
          leftLabel: d.left != null ? '今天還可以問 ' + d.left + ' 題' : '每天 3 題', footer: '以 CAFECA 身分發問 · 問題會公開顯示',
          signedIn: !!me, onSignIn: function () { S.openSignIn(); }, submitLabel: '送出', onAsk: ask, disabled: me && !!me.restriction,
          replies: mine, avatar: a.image, actorName: a.name, aiLabel: AI, youAskedLabel: '你問：', pendingLabel: a.name + '正在想…（通常一分鐘內回覆）',
          replyNote: '這是 AI 以演員設定寫的即時文字回覆，只有你看得到；這題被 +1 夠多，就可能在演員信箱拍成影片。' }),
        h('div', { className: 'panel' },
          h('div', { className: 'panel-head' }, h('h2', null, '大家想問的'),
            h(M.SegmentedTabs, { label: '排序', value: order, onChange: setOrder, options: [{ value: 'top', label: '最多 +1' }, { value: 'new', label: '最新' }, { value: 'answered', label: '已回答' }] })),
          h('span', { className: 'md-meta' }, '每週依 +1 數挑題，由' + a.name + '用自己的聲音拍成影片回答'),
          qs && qs.questions.length ? h('ol', { className: 'qlist' }, qs.questions.map(function (q, i) {
            return h('li', { key: q.id, className: 'qrow' },
              h('span', { className: 'qrank' + (i < 3 && order === 'top' ? ' is-top' : '') }, i + 1),
              h('span', { className: 'qbody' }, h('span', null, q.text), h('span', { className: 'md-meta' }, q.by + (q.picked ? ' · 入選影片回答' : ''))),
              q.reply ? h('span', { className: 'md-reply-label' }, AI) : null,
              h('button', { type: 'button', className: 'md-iconbtn', 'aria-label': '檢舉', title: '檢舉', onClick: function () { S.report('question', q.id); } }, h(M.Icon, { name: 'flag', size: 14 })),
              h('button', { type: 'button', className: 'md-chip md-chip-sm' + (q.supported ? ' is-on' : ''), 'aria-pressed': q.supported ? 'true' : 'false', onClick: function () { support(q); } },
                (q.supported ? '已 +1 · ' : '+1 · ') + q.supporters));
          })) : h(M.EmptyState, { title: order === 'answered' ? '還沒有影片回答' : '還沒有人提問', body: order === 'answered' ? '演員信箱上線後，入選的問題會在這裡出現。' : '當第一個發問的人。' }))),
      d.works.length ? h('section', { className: 'sec', 'aria-labelledby': 'works' },
        h(M.SectionHeader, { id: 'works', title: '演出作品', meta: d.works.length + ' 部' }),
        h('div', { className: 'related' }, d.works.map(function (v) {
          return h(M.VideoTile, { key: v.id, image: v.image, title: v.title, subtitle: S.videoLine(v), href: '/watch/' + v.id, size: 'sm' });
        }))) : null,
      h(M.AIDisclosure, null, a.name + '是 AI 製作的虛擬角色，不是真人。演員的回答由 AI 依角色設定產生。'));
  }
  function stat(n, label) { return h('span', { className: 'stat' }, h('b', null, n), label); }

  S.mount(Actor);
})();
