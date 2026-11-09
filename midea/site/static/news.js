/* 每日報導（設計稿 N1 晨報）：/news 列表與 /news/{slug} 文章頁
   文章頁：左邊長文（七種模板）、可點的 SVG 圖、選字提問／引用／想看這段做成影片、小測驗、讀者的問題；
   右欄「你覺得這篇？」與「接下來」（續作門檻、每週影片）。手機：底部固定反應列。 */
(function () {
  var React = window.React, h = React.createElement, M = window.Midea, S = window.Site;
  var slug = decodeURIComponent((location.pathname.match(/^\/news\/([^/]+)/) || [])[1] || '');

  /* ------------------------------------------------------------ /news */
  function Archive() {
    var _d = React.useState(null), d = _d[0], set = _d[1];
    React.useEffect(function () { S.api('/news').then(set).catch(function () { set({ days: [] }); }); }, []);
    if (!d) return h(M.BentoGrid, { row: 'hero' }, h(M.Skeleton, { cols: 2, rows: 2 }), h(M.Skeleton), h(M.Skeleton), h(M.Skeleton), h(M.Skeleton));
    return h(React.Fragment, null,
      h('header', { className: 'news-top' }, h('h1', null, '每日報導'),
        h('p', { className: 'md-meta' }, 'AI 每天 06:00 讀新聞、GitHub 熱門專案與新論文，寫成 5 篇附圖的報導。讀者的「想看續作」會變成隔天的續作；每週一從上週的報導選兩部做成影片。')),
      d.days.length ? d.days.map(function (day, i) {
        return h('section', { key: day.day, className: 'sec', 'aria-labelledby': 'd' + i },
          h(M.SectionHeader, { id: 'd' + i, title: (i === 0 ? '最新 · ' : '') + day.label, meta: day.articles.length + ' 篇' }),
          S.newsBento(day.articles));
      }) : h(M.EmptyState, { title: '第一批報導準備中', body: '每天 06:00 發佈；也可以先看看官方頻道。' }));
  }

  /* ------------------------------------------------------------ helpers */
  /* [1] [2][3] → links to the numbered sources */
  function rich(text) {
    var parts = String(text || '').split(/(\[\d{1,2}\])/);
    return parts.map(function (t, i) {
      var m = t.match(/^\[(\d{1,2})\]$/);
      return m ? h('a', { key: i, href: '#src-' + m[1], className: 'art-cite', 'aria-label': '來源 ' + m[1] }, m[1]) : t;
    });
  }
  function P(text, i, cls) { return h('p', { key: 'p' + i, className: cls || 'art-p', 'data-para': i }, rich(text)); }
  function Why(p) { return p.text ? h('div', { className: 'art-why' }, h('b', null, '為什麼重要'), h('span', null, p.text)) : null; }

  /* ------------------------------------------------------------ the seven templates */
  function Body(p) {
    var a = p.a, b = a.body || {}, fig = a.figure || {}, n = 0;
    function next() { return n++; }
    var figure = function (cap, extra) {
      return h(M.ArticleFigure, Object.assign({ wide: fig.wide, narrow: fig.narrow, caption: cap }, extra || {}));
    };
    var paras = (b.paragraphs || []).map(function (t) { return P(t, next()); });
    switch (a.template) {
      case 'brief':
        return h(React.Fragment, null,
          b.headline_number ? h('div', { className: 'art-big' }, h('b', { className: /^[−-]/.test(b.headline_number.display) ? 'is-down' : '' }, b.headline_number.display),
            h('span', { className: 'md-meta' }, b.headline_number.label)) : null,
          figure('點長條看數字'),
          b.points && b.points.length ? h('div', { className: 'art-points' }, h('b', null, '三個重點'), h('ol', null, b.points.map(function (t) { return h('li', { key: t, 'data-para': next() }, t); }))) : null,
          paras, h(Why, { text: b.why }));
      case 'story':
        return h(Story, { a: a, start: n });
      case 'ranking':
        return h(React.Fragment, null, b.intro ? P(b.intro, next(), 'art-p art-lead') : null, figure('點長條看說明'),
          h('ol', { className: 'art-rank' }, (b.items || []).map(function (it, i) {
            return h('li', { key: it.name + i, 'data-para': next() }, h('b', { className: 'art-rank-n' }, i + 1),
              h('span', null, it.url ? h('a', { href: it.url, target: '_blank', rel: 'noopener noreferrer' }, it.name) : h('b', null, it.name),
                it.desc && it.desc !== '—' ? h('span', { className: 'md-meta' }, it.desc) : null),
              h('b', { className: 'art-rank-v' }, it.display || it.value));
          })), paras, h(Why, { text: b.why }));
      case 'timeline':
        return h(React.Fragment, null, figure('點節點看那一天'),
          h('ol', { className: 'art-tl' }, (b.events || []).map(function (e, i) {
            return h('li', { key: i, 'data-para': next() }, h('b', null, e.date), h('span', null, e.text));
          })), paras, h(Why, { text: b.why }));
      case 'versus':
        return h(React.Fragment, null, figure(null),
          h('div', { className: 'art-vs' }, (b.sides || []).map(function (sd, i) {
            return h('div', { key: i, className: 'art-vs-side', 'data-para': next() }, h('b', null, sd.name), h('span', { className: 'md-meta' }, sd.desc),
              sd.display ? h('b', { className: 'art-vs-v' }, sd.display) : null,
              h('ul', null, (sd.points || []).filter(function (x) { return x && x !== '—'; }).map(function (x) { return h('li', { key: x }, h(M.Icon, { name: 'check', size: 14 }), x); })));
          })),
          b.same || b.diff ? h('div', { className: 'art-same' }, b.same ? h('p', { 'data-para': next() }, h('b', null, '一樣的地方　'), b.same) : null,
            b.diff ? h('p', { 'data-para': next() }, h('b', null, '不一樣的地方　'), b.diff) : null) : null,
          paras, h(Why, { text: b.why }));
      case 'howto':
        return h(React.Fragment, null, figure('點方塊看這一步'),
          h('ol', { className: 'art-steps' }, (b.steps || []).map(function (st, i) {
            return h('li', { key: i, 'data-para': next() }, h('b', { className: 'art-steps-n' }, i + 1), h('span', null, h('b', null, st.title), h('span', null, st.text)));
          })), paras, h(Why, { text: b.why }));
      case 'paper':
        return h(React.Fragment, null,
          h('div', { className: 'art-oneline', 'data-para': next() }, h('span', null, '一句話'), h('b', null, b.oneline)),
          figure('點任一類看重點'),
          h('dl', { className: 'art-dl' }, [['方法', b.method], ['發現', b.findings], ['限制', b.limits], ['對 Midea', b.midea]].filter(function (x) { return x[1]; }).map(function (x) {
            return h(React.Fragment, { key: x[0] }, h('dt', null, x[0]), h('dd', { 'data-para': next() }, x[1]));
          })), paras);
      default:
        return h(React.Fragment, null, figure(null), paras, h(Why, { text: b.why }));
    }
  }

  /* 深度分析（每篇都有）、程式碼導讀（GitHub）、接下來追蹤 */
  function Analysis(p) {
    var b = p.a.body || {}, n = 100;
    var secs = (b.sections || []).filter(function (x) { return x && x.heading; });
    var code = b.code || [];
    var repo = (p.a.sources || []).filter(function (x) { return /github\.com\/[^/]+\/[^/]+$/.test(x.url || ''); })[0];
    return h(React.Fragment, null,
      secs.map(function (sec, i) {
        return h('section', { key: i, className: 'art-sec', 'aria-labelledby': 'sec-' + i },
          h('h2', { id: 'sec-' + i, className: 'art-sec-h' }, sec.heading),
          (sec.paragraphs || []).map(function (t) { return P(t, n++); }));
      }),
      code.length ? h('section', { className: 'art-sec', 'aria-labelledby': 'code-h' }, h('h2', { id: 'code-h', className: 'art-sec-h' }, '程式碼導讀'),
        code.map(function (c, i) {
          return h(M.CodeExcerpt, { key: i, path: c.path, lang: c.lang, code: c.snippet, note: c.note,
            href: repo ? repo.url + '/blob/HEAD/' + c.path : null });
        })) : null,
      b.follow && b.follow.length ? h('div', { className: 'art-follow' }, h('b', null, '接下來追蹤'),
        h('ul', null, b.follow.map(function (f, i) { return h('li', { key: i }, f); })),
        h('span', { className: 'md-meta' }, '想看哪一個？按「想看續作」或在下方提問，+1 多的會寫成續作。')) : null);
  }

  /* 數據故事：圖固定在上方，段落捲到哪裡、圖就標到哪裡 */
  function Story(p) {
    var a = p.a, b = a.body || {}, fig = a.figure || {};
    var _s = React.useState(0), cur = _s[0], setCur = _s[1];
    var refs = React.useRef([]);
    React.useEffect(function () {
      if (!window.IntersectionObserver) return;
      var io = new IntersectionObserver(function (es) {
        es.forEach(function (e) { if (e.isIntersecting) setCur(Number(e.target.getAttribute('data-step'))); });
      }, { rootMargin: '-45% 0px -45% 0px' });
      refs.current.forEach(function (el) { if (el) io.observe(el); });
      return function () { io.disconnect(); };
    }, []);
    var steps = b.steps || [];
    var hl = steps[cur] && steps[cur].highlight != null ? steps[cur].highlight : cur;
    return h(React.Fragment, null,
      h('div', { className: 'art-story' },
        h('div', { className: 'art-story-fig' }, h(M.ArticleFigure, { wide: fig.wide, narrow: fig.narrow, selected: hl, caption: (cur + 1) + ' / ' + steps.length + ' · 隨段落切換重點，也可以直接點' })),
        h('div', { className: 'art-story-steps' }, steps.map(function (st, i) {
          return h('div', { key: i, ref: function (el) { refs.current[i] = el; }, 'data-step': i, 'data-para': i, className: 'art-step' + (i === cur ? ' is-on' : '') },
            h('span', { className: 'art-step-n' }, (i + 1) + ' / ' + steps.length), h('b', null, st.title), h('span', null, st.text));
        }))),
      (b.paragraphs || []).map(function (t, i) { return P(t, steps.length + i); }), h(Why, { text: b.why }));
  }

  /* ------------------------------------------------------------ select text → ask / quote / video */
  function SelectionBar(p) {
    var _p = React.useState(null), pos = _p[0], setPos = _p[1];
    React.useEffect(function () {
      function check() {
        var sel = window.getSelection && window.getSelection();
        if (!sel || sel.isCollapsed || !p.root.current) { setPos(null); return; }
        var t = sel.toString().trim();
        var node = sel.anchorNode && (sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement);
        var para = node && node.closest && node.closest('[data-para]');
        if (!t || t.length < 4 || !para || !p.root.current.contains(para)) { setPos(null); return; }
        var r = sel.getRangeAt(0).getBoundingClientRect(), box = p.root.current.getBoundingClientRect();
        setPos({ x: Math.max(0, Math.min(box.width - 300, r.left - box.left + r.width / 2 - 150)), y: r.top - box.top - 52, text: t.slice(0, 120), para: Number(para.getAttribute('data-para')) });
      }
      document.addEventListener('mouseup', check); document.addEventListener('touchend', check); document.addEventListener('keyup', check);
      return function () { document.removeEventListener('mouseup', check); document.removeEventListener('touchend', check); document.removeEventListener('keyup', check); };
    }, []);
    if (!pos) return null;
    function done() { setPos(null); if (window.getSelection) window.getSelection().removeAllRanges(); }
    return h('div', { className: 'art-selbar', style: { left: pos.x, top: pos.y }, role: 'toolbar', 'aria-label': '對選取的文字' },
      h('button', { type: 'button', className: 'md-chip md-chip-sm', onMouseDown: function (e) { e.preventDefault(); }, onClick: function () { p.onAsk(pos.text, pos.para); done(); } }, h(M.Icon, { name: 'chat', size: 14 }), '對這段提問'),
      h('button', { type: 'button', className: 'md-chip md-chip-sm', onMouseDown: function (e) { e.preventDefault(); }, onClick: function () {
        var q = '「' + pos.text + '」— ' + p.title + ' ' + location.origin + location.pathname;
        (navigator.clipboard ? navigator.clipboard.writeText(q) : Promise.resolve()).then(function () { S.toast('已複製引用'); }); done();
      } }, h(M.Icon, { name: 'quote', size: 14 }), '引用'),
      h('button', { type: 'button', className: 'md-chip md-chip-sm', onMouseDown: function (e) { e.preventDefault(); }, onClick: function () { p.onVideo(); done(); } }, h(M.Icon, { name: 'film', size: 14 }), '想看這段做成影片'));
  }

  /* ------------------------------------------------------------ questions */
  function Questions(p) {
    var a = p.a, qs = p.questions;
    var _t = React.useState(''), text = _t[0], setText = _t[1];
    var _b = React.useState(false), busy = _b[0], setBusy = _b[1];
    var draft = p.draft;
    React.useEffect(function () { if (draft && draft.focus) { var el = document.getElementById('ask-text'); if (el) { el.focus(); el.scrollIntoView({ block: 'center' }); } } }, [draft]);
    function send(e) {
      e.preventDefault();
      if (!text.trim()) return;
      S.requireWriter(function () {
        setBusy(true);
        S.api('/news/' + a.slug + '/questions', { method: 'POST', body: { text: text, para: draft ? draft.para : null, quote: draft ? draft.quote : null } })
          .then(function (j) { setText(''); p.onQuestions(j.questions, j.left); p.setDraft(null); S.toast('已送出，+1 多的問題會寫進續作'); })
          .catch(function (er) { S.toast(er.message); }).then(function () { setBusy(false); });
      });
    }
    function support(q) {
      S.requireWriter(function () {
        S.api('/news/questions/' + q.id + '/support', { method: q.supported ? 'DELETE' : 'POST' }).then(function (j) {
          p.onQuestions(qs.map(function (x) { return x.id === q.id ? Object.assign({}, x, { supporters: j.supporters, supported: !q.supported }) : x; }));
        }).catch(function (er) { S.toast(er.message); });
      });
    }
    return h('section', { className: 'art-qs', id: 'questions', 'aria-labelledby': 'qs-h' },
      h(M.SectionHeader, { id: 'qs-h', title: '讀者的問題', level: 2, meta: qs.length ? qs.length + ' 則 · 依 +1 排序' : null }),
      h('form', { className: 'art-ask', onSubmit: send },
        draft && draft.quote ? h('span', { className: 'art-ask-quote' }, '針對：「' + draft.quote + '」', h('button', { type: 'button', className: 'md-linkbtn', onClick: function () { p.setDraft(null); } }, '取消')) : null,
        h('label', { htmlFor: 'ask-text', className: 'md-sr' }, '你的問題'),
        h('textarea', { id: 'ask-text', className: 'md-input', rows: 2, maxLength: 80, value: text, placeholder: '看完有什麼想知道的？例：這和上個月的數字比起來如何？',
          onChange: function (e) { setText(e.target.value); } }),
        h('span', { className: 'art-ask-foot' }, h('span', { className: 'md-meta' }, (p.left != null ? '今天還可以問 ' + p.left + ' 題 · ' : '') + '以 CAFECA 身分發問 · 問題會公開顯示 · +1 達 ' + a.sequel_threshold + ' 優先寫進續作'),
          h(M.Button, { type: 'submit', disabled: busy || !text.trim() }, busy ? '送出中' : '送出'))),
      qs.length ? h('div', null, qs.map(function (q) {
        return h('div', { key: q.id, className: 'qrow' },
          h('span', { className: 'qtext' }, q.quote ? h('span', { className: 'md-meta art-q-quote' }, '「' + q.quote + '」') : null, h('span', null, q.text),
            h('span', { className: 'md-meta' }, q.by + (q.answered_in ? ' · ' : '')), q.answered_in ? h('a', { href: '/news/' + q.answered_in, className: 'md-meta' }, '已在續作回答') : null),
          h('span', { className: 'qacts' },
            h('button', { type: 'button', className: 'md-iconbtn', 'aria-label': '檢舉', onClick: function () { S.report('article_q', q.id); } }, h(M.Icon, { name: 'flag', size: 16 })),
            h('button', { type: 'button', className: 'md-chip md-chip-sm' + (q.supported ? ' is-on' : ''), 'aria-pressed': q.supported ? 'true' : 'false', onClick: function () { support(q); } },
              (q.supported ? '已 +1 · ' : '+1 · ') + q.supporters)));
      })) : h('p', { className: 'md-meta' }, '還沒有人提問。也可以在文章裡選一段文字，直接對那一段提問。'));
  }

  /* ------------------------------------------------------------ the article */
  function Article() {
    var _d = React.useState(null), d = _d[0], set = _d[1];
    var _q = React.useState(null), draft = _q[0], setDraft = _q[1];
    var me = S.useMe(), mobile = S.useMobile(), root = React.useRef(null), end = React.useRef(null);
    React.useEffect(function () {
      S.api('/news/' + encodeURIComponent(slug)).then(function (j) { set(j); document.title = j.title + ' · Midea 報導'; })
        .catch(function (e) { set({ error: e.message }); });
    }, [me && me.account]);
    React.useEffect(function () {
      if (!d || d.error) return;
      S.api('/news/' + d.slug + '/read', { method: 'POST', body: { done: false } }).catch(function () {});
      if (!window.IntersectionObserver || !end.current) return;
      var sent = false, io = new IntersectionObserver(function (es) {
        if (!sent && es[0].isIntersecting) { sent = true; S.api('/news/' + d.slug + '/read', { method: 'POST', body: { done: true } }).catch(function () {}); }
      });
      io.observe(end.current);
      return function () { io.disconnect(); };
    }, [d && d.slug]);
    React.useEffect(function () {
      document.body.classList.toggle('has-abar', !!mobile);
      return function () { document.body.classList.remove('has-abar'); };
    }, [mobile]);
    if (!d) return h('div', { className: 'art' }, h(M.Skeleton, { rows: 2 }));
    if (d.error) return h(M.EmptyState, { title: '找不到這篇報導', body: d.error, action: h(M.Button, { variant: 'secondary', href: '/news' }, '看其他報導') });

    function toggle(kind, on) {
      if (kind === 'question' && on) { setDraft({ focus: Date.now() }); }
      S.api('/news/' + d.slug + '/react', { method: 'POST', body: { kind: kind, on: on } })
        .then(function (j) { set(Object.assign({}, d, { counts: j.counts, mine: j.mine })); })
        .catch(function (e) { S.toast(e.message); });
    }
    function answer(i) {
      S.api('/news/' + d.slug + '/quiz', { method: 'POST', body: { choice: i } }).then(function (q) { set(Object.assign({}, d, { quiz: q })); });
    }
    var c = d.counts || {}, th = d.sequel_threshold;
    var reacts = h(M.ArticleReactions, { options: S.AREACT, counts: c, value: d.mine, onToggle: toggle });
    var src = d.sources[0] || {};
    var head = h('header', { className: 'art-head' },
      h('span', { className: 'art-chips' }, h(M.KindChip, { kind: d.kind }, d.kind_label), h(M.Tag, null, d.template_label),
        d.sequel_of ? h(M.InfluenceTag, null, '讀者想看的續作') : null),
      h('h1', { className: 'art-title' }, d.title),
      h('p', { className: 'art-dek' }, d.dek),
      d.sequel_of ? h('p', { className: 'md-meta' }, '續作 · ', d.body.readers ? '依 ' + d.body.readers + ' 位讀者的「想看續作」 · ' : '', '原文：', h('a', { href: '/news/' + d.sequel_of.slug }, d.sequel_of.title)) : null,
      h('span', { className: 'md-meta' }, 'Midea 報導 · ' + d.date_label + ' ' + d.published + ' · 閱讀 ' + d.minutes + ' 分鐘 · ' + d.sources.length + ' 個來源'),
      h(M.SourceList, { sources: d.sources }),
      h(M.ArticleCover, { image: d.cover, alt: '' }));
    var rail = h('aside', { className: 'art-rail', 'aria-label': '回饋與接下來' },
      h('div', { className: 'art-card' }, h('b', null, '你覺得這篇？'), reacts,
        h('span', { className: 'md-meta' }, '不用登入也可以按 · 你的反應會決定之後寫什麼、做什麼影片')),
      h('div', { className: 'art-card' }, h('b', null, '接下來'),
        d.sequels.length ? h('span', { className: 'art-done' }, h(M.Icon, { name: 'pen', size: 15 }), '已寫成續作：', h('a', { href: '/news/' + d.sequels[0].slug }, d.sequels[0].title))
          : h(M.FollowupMeter, { label: '寫續作', value: c.sequel || 0, max: th, note: (c.sequel || 0) >= th ? '已達標，下一次 06:00 會優先寫續作' : '「想看續作」達 ' + th + ' 人，隔天 06:00 優先寫續作，並回答 +1 最多的問題' }),
        d.video ? h('span', { className: 'art-done' }, h(M.Icon, { name: 'film', size: 15 }),
          d.video.status === 'ready' ? h('a', { href: '/watch/' + d.video.id }, '已做成影片（' + d.video.label + '）') : '本週影片製作中（' + d.video.label + '）')
          : h(M.FollowupMeter, { label: '做成影片', valueLabel: (c.video || 0) + ' 人想看', note: '每週一從上週的報導選兩部做成影片：一部編輯選、一部讀者反饋最高（「做成影片」的分數最高）' })),
      d.questions.length ? h('div', { className: 'art-card' }, h('b', null, '讀者的問題 · ' + d.questions.length),
        d.questions.slice(0, 2).map(function (q) { return h('a', { key: q.id, href: '#questions', className: 'art-rail-q' }, h('span', null, q.text), h('span', { className: 'md-meta' }, '+' + q.supporters)); })) : null);
    var after = h(React.Fragment, null,
      d.quiz ? h(M.QuizCard, { question: d.quiz.q, options: d.quiz.options, mine: d.quiz.mine, answer: d.quiz.answer, right: d.quiz.right, onAnswer: answer }) : null,
      h(M.AIDisclosure, null, '本文由 AI 依來源撰寫，數字取自來源並經過核對；有錯誤請在下方提問。演員皆為虛擬角色。'),
      h('div', { ref: end }),
      h(Questions, { a: d, questions: d.questions, left: d.left, draft: draft, setDraft: setDraft, onQuestions: function (qs, left) { set(Object.assign({}, d, { questions: qs, left: left != null ? left : d.left })); } }),
      d.related.length ? h('section', { className: 'sec', 'aria-labelledby': 'rel-h' }, h(M.SectionHeader, { id: 'rel-h', title: '同一天的報導', level: 2 }),
        h('div', { className: 'art-related' }, d.related.map(function (r) {
          return h('a', { key: r.slug, href: '/news/' + r.slug, className: 'art-rel' }, h(M.KindChip, { kind: r.kind }, r.kind_label), h('b', null, r.title), h('span', { className: 'md-meta' }, r.dek));
        }))) : null);
    return h(React.Fragment, null,
      h('div', { className: 'art' },
        h('article', { className: 'art-main', ref: root, style: { position: 'relative' } }, head,
          h('div', { className: 'art-body' }, h(Body, { a: d }), h(Analysis, { a: d })),
          h(SelectionBar, { root: root, title: d.title, onAsk: function (t, i) { setDraft({ quote: t, para: i, focus: Date.now() }); }, onVideo: function () { if ((d.mine || []).indexOf('video') < 0) toggle('video', true); S.toast('已記下：想看做成影片'); } }),
          mobile ? rail : null, after),
        mobile ? null : rail),
      mobile ? h('div', { className: 'art-abar' }, h(M.ArticleReactions, { bar: true, options: S.AREACT.slice(0, 3), counts: c, value: d.mine, onToggle: toggle }),
        h('a', { href: '#questions', className: 'md-iconbtn', 'aria-label': '讀者的問題' }, h(M.Icon, { name: 'chat', size: 20 }))) : null);
  }

  S.mount(slug ? Article : Archive);
})();
