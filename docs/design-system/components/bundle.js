/* @ds-bundle: {"format":4,"namespace":"Midea","components":[{"name":"Logo"},{"name":"Icon"},{"name":"Button"},{"name":"SignInButton"},{"name":"SearchField"},{"name":"SegmentedTabs"},{"name":"SiteHeader"},{"name":"SiteFooter"},{"name":"Badge"},{"name":"Tag"},{"name":"ProgressBar"},{"name":"SectionHeader"},{"name":"BentoGrid"},{"name":"VideoTile"},{"name":"ThemeTile"},{"name":"RankTile"},{"name":"RankRow"},{"name":"DaySlot"},{"name":"ActorCard"},{"name":"InfluenceTag"},{"name":"ViewerCount"},{"name":"ReactionBar"},{"name":"LiveReactions"},{"name":"PollCard"},{"name":"LivePlayer"},{"name":"VideoPlayer"},{"name":"VideoMeta"},{"name":"AIDisclosure"},{"name":"SignInDialog"},{"name":"AccountMenu"},{"name":"Skeleton"},{"name":"EmptyState"},{"name":"TopicBento"},{"name":"BottomNav"},{"name":"ChatPanel"},{"name":"WishCard"},{"name":"WishComposer"},{"name":"AskActor"},{"name":"AnswerTile"},{"name":"TopicHeader"},{"name":"ScheduleDay"},{"name":"ScheduleWeek"}]} */
(function () {
  var React = window.React;
  var h = React.createElement;
  function cx() { return Array.prototype.filter.call(arguments, Boolean).join(' '); }
  function span(cols, rows) { return cx(cols > 1 && 'md-c' + cols, rows > 1 && 'md-r' + rows); }

  var PATHS = {
    search: [['circle', { cx: 11, cy: 11, r: 7 }], ['path', { d: 'm20 20-3.5-3.5' }]],
    key: [['circle', { cx: 8, cy: 15, r: 4 }], ['path', { d: 'm11 12 9-9M17 6l3 3M15 8l2 2' }]],
    'sound-off': [['path', { d: 'M11 5 6 9H2v6h4l5 4z' }], ['path', { d: 'm23 9-6 6M17 9l6 6' }]],
    'arrow-right': [['path', { d: 'M5 12h14M13 6l6 6-6 6' }]],
    'chevron-right': [['path', { d: 'm9 6 6 6-6 6' }]]
  };
  function Icon(p) {
    var size = p.size || 18;
    if (p.name === 'play') {
      return h('svg', { width: size, height: size, viewBox: '0 0 24 24', 'aria-hidden': 'true', className: 'md-icon' },
        h('path', { d: 'M7 4v16l13-8z', fill: 'currentColor' }));
    }
    var parts = PATHS[p.name] || [];
    return h('svg', { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2,
      strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': 'true', className: 'md-icon' },
      parts.map(function (q, i) { return h(q[0], Object.assign({ key: i }, q[1])); }));
  }

  function Logo(p) {
    var size = p.size || 28;
    return h('a', { href: p.href || '#', className: 'md-logo', 'aria-label': 'Midea 首頁' },
      h('svg', { width: size, height: size, viewBox: '0 0 30 30', 'aria-hidden': 'true' },
        h('rect', { x: 1, y: 1, width: 28, height: 28, rx: 8, fill: 'none', stroke: 'currentColor', strokeWidth: 2 }),
        h('path', { d: 'M12 9.5v11l9-5.5z', fill: 'currentColor' })),
      p.mark ? null : h('span', { className: 'md-logo-word', style: { fontSize: Math.round(size * 0.75) } }, 'Midea'));
  }

  function Button(p) {
    var variant = p.variant || 'primary', size = p.size || 'md';
    var cls = cx('md-btn', 'md-btn-' + variant, size === 'lg' && 'md-btn-lg', p.className);
    var kids = [p.icon ? h(Icon, { key: 'i', name: p.icon, size: size === 'lg' ? 18 : 16 }) : null, p.children];
    if (p.href) return h('a', { href: p.href, className: cls }, kids);
    return h('button', { type: p.type || 'button', className: cls, onClick: p.onClick, disabled: p.disabled }, kids);
  }

  function SignInButton(p) {
    return h(Button, { variant: p.variant === 'outline' ? 'secondary' : 'primary', icon: 'key', onClick: p.onClick, href: p.href },
      p.children || '以 CAFECA 登入');
  }

  function SearchField(p) {
    return h('label', { className: 'md-search' },
      h(Icon, { name: 'search', size: 16 }),
      h('span', { className: 'md-sr' }, p.label || '搜尋'),
      h('input', { type: 'search', placeholder: p.placeholder || '搜尋影片、演員、主題', value: p.value, onChange: p.onChange }));
  }

  function SegmentedTabs(p) {
    var opts = p.options || [];
    var _s = React.useState(p.defaultValue || (opts[0] && opts[0].value));
    var cur = p.value !== undefined ? p.value : _s[0];
    return h('div', { className: 'md-seg', role: 'group', 'aria-label': p.label || '切換' },
      opts.map(function (o) {
        var on = o.value === cur;
        return h('button', { key: o.value, type: 'button', 'aria-pressed': on ? 'true' : 'false', className: cx('md-seg-btn', on && 'is-on'),
          onClick: function () { _s[1](o.value); if (p.onChange) p.onChange(o.value); } }, o.label);
      }));
  }

  function SiteHeader(p) {
    var items = p.items || [];
    return h('header', { className: 'md-header' },
      h(Logo, null),
      h('nav', { 'aria-label': '主選單', className: 'md-nav' },
        items.map(function (it, i) {
          return h('a', { key: i, href: it.href || '#', className: cx('md-nav-a', it.active && 'is-on'), 'aria-current': it.active ? 'page' : undefined }, it.label);
        })),
      h('div', { className: 'md-header-end' },
        p.search === false ? null : h(SearchField, { placeholder: p.searchPlaceholder }),
        p.account || h(SignInButton, null)));
  }

  function SiteFooter(p) {
    var links = p.links || [{ label: '關於', href: '#' }, { label: '授權與出處', href: '#' }, { label: '隱私', href: '#' }];
    return h('footer', { className: 'md-footer' },
      h('span', null, p.note || '© 2026 CAFECA · Midea　影片由 AI 製作，演員皆為虛擬角色'),
      h('span', { className: 'md-footer-links' }, links.map(function (l, i) { return h('a', { key: i, href: l.href }, l.label); })));
  }

  var MOVE = { new: '新上榜', up: '▲ 上升', down: '▼ 下降', same: '— 持平' };
  function Badge(p) {
    var tone = p.tone || 'neutral';
    var dot = p.dot !== undefined ? p.dot : (tone === 'live' || tone === 'now');
    var text = p.children !== undefined ? p.children : (MOVE[tone] || (tone === 'live' ? 'LIVE' : ''));
    return h('span', { className: cx('md-badge', 'md-badge-' + tone) }, dot ? h('span', { className: 'md-dot', 'aria-hidden': 'true' }) : null, text);
  }

  function Tag(p) { return h('span', { className: 'md-tag' }, p.children); }

  function ProgressBar(p) {
    var v = Math.max(0, Math.min(1, p.value || 0));
    return h('div', { className: 'md-progress', role: 'progressbar', 'aria-label': p.label || '進度', 'aria-valuemin': 0, 'aria-valuemax': 100,
      'aria-valuenow': Math.round(v * 100) }, h('span', { style: { width: (v * 100) + '%' } }));
  }

  function SectionHeader(p) {
    var Tagname = 'h' + (p.level || 2);
    return h('div', { className: 'md-sechead' },
      h('div', { className: 'md-sechead-main' }, h(Tagname, { className: 'md-sechead-title', id: p.id }, p.title), p.tag ? h(Tag, null, p.tag) : null),
      p.action ? p.action : (p.meta ? h('span', { className: 'md-meta' }, p.meta) : null));
  }

  function BentoGrid(p) {
    return h('div', { className: cx('md-bento', 'md-bento-' + (p.row || 'topic')) }, p.children);
  }

  function VideoTile(p) {
    var size = p.size || 'md';
    var pos = p.focus === 'top' ? 'center 25%' : (p.focus || 'center');
    return h('a', { href: p.href || '#', className: cx('md-tile', 'md-vtile', 'md-vtile-' + size, span(p.cols, p.rows)) },
      h('img', { src: p.image, alt: p.alt || '', style: { objectPosition: pos } }),
      h('span', { className: 'md-scrim', 'aria-hidden': 'true' }),
      p.badge ? h('span', { className: 'md-vtile-badge' }, p.badge) : null,
      p.corner ? h('span', { className: 'md-vtile-corner' }, p.corner) : null,
      h('span', { className: 'md-vtile-body' },
        p.eyebrow ? h('span', { className: 'md-vtile-eyebrow' }, p.eyebrow) : null,
        h('span', { className: 'md-vtile-title' }, p.title),
        p.subtitle ? h('span', { className: 'md-vtile-sub' }, p.subtitle) : null,
        p.action ? h('span', { className: 'md-vtile-action' }, p.action) : null));
  }

  function ThemeTile(p) {
    return h('a', { href: p.href || '#', className: cx('md-tile', 'md-theme', span(p.cols, p.rows)) },
      h('span', { className: 'md-theme-eyebrow' }, p.eyebrow),
      h('span', { className: 'md-theme-title' }, p.title),
      p.note ? h('span', { className: 'md-theme-note' }, p.note) : null);
  }

  function RankTile(p) {
    var first = String(p.rank) === '1';
    return h('a', { href: p.href || '#', className: cx('md-tile', 'md-rank', first && 'md-rank-1', span(p.cols, p.rows)),
      'aria-label': '第 ' + p.rank + ' 名：' + p.title },
      h('img', { src: p.image, alt: '', style: { objectPosition: p.focus === 'top' ? 'center 25%' : (p.focus || 'center') } }),
      h('span', { className: first ? 'md-scrim-side' : 'md-scrim', 'aria-hidden': 'true' }),
      h('span', { className: 'md-rank-n', 'aria-hidden': 'true' }, p.rank),
      first ? null : h('span', { className: 'md-rank-move' }, h(Badge, { tone: p.move || 'same' })),
      h('span', { className: 'md-rank-body' },
        first ? h(Badge, { tone: p.move || 'same' }) : null,
        h('span', { className: 'md-rank-title' }, p.title),
        p.subtitle ? h('span', { className: 'md-vtile-sub' }, p.subtitle) : null));
  }

  function RankRow(p) {
    var move = p.move || 'same';
    return h('a', { href: p.href || '#', className: 'md-rankrow' },
      h('span', { className: 'md-rankrow-n' }, p.rank),
      h('img', { src: p.image, alt: '', style: { objectPosition: p.focus === 'top' ? 'center 25%' : 'center' } }),
      h('span', { className: 'md-rankrow-body' }, h('span', { className: 'md-rankrow-title' }, p.title),
        h('span', { className: 'md-rankrow-move md-move-' + move }, MOVE[move])));
  }

  function DaySlot(p) {
    return h('a', { href: p.href || '#', className: cx('md-day', p.today && 'is-today'), 'aria-current': p.today ? 'date' : undefined },
      h('span', { className: 'md-day-d' }, p.day),
      h('span', { className: 'md-day-t' }, p.title),
      h('span', { className: 'md-meta' }, p.time),
      p.tag ? h('span', { className: 'md-day-tag' }, p.tag) : null);
  }

  function ActorCard(p) {
    return h('a', { href: p.href || '#', className: 'md-actor' },
      h('img', { src: p.image, alt: '' }),
      h('span', { className: 'md-actor-body' },
        h('span', { className: 'md-actor-name' }, p.name),
        h('span', { className: 'md-meta' }, '@' + p.handle + (p.role ? ' · ' + p.role : '')),
        p.works ? h('span', { className: 'md-actor-works' }, p.works) : null));
  }


  /* ---------------------------------------------------------------- v2: playback, sign-in, feedback & interaction */
  Object.assign(PATHS, {
    heart: [['path', { d: 'M12 21s-7-4.4-9.3-8.6C1 9 3 5 6.6 5c2 0 3.3 1 5.4 3.1C14.1 6 15.4 5 17.4 5 21 5 23 9 21.3 12.4 19 16.6 12 21 12 21z' }]],
    sparkle: [['path', { d: 'M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18' }]],
    smile: [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01' }]],
    tear: [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M8 15s1.5-1.5 4-1.5 4 1.5 4 1.5M9 9h.01M15 9h.01M16 11v2' }]],
    plus: [['path', { d: 'M12 5v14M5 12h14' }]],
    x: [['path', { d: 'M6 6l12 12M18 6 6 18' }]],
    bookmark: [['path', { d: 'M6 3h12v18l-6-4-6 4z' }]],
    share: [['path', { d: 'M4 12v7h16v-7M12 3v12M7 8l5-5 5 5' }]],
    eye: [['path', { d: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z' }], ['circle', { cx: 12, cy: 12, r: 3 }]],
    people: [['circle', { cx: 9, cy: 8, r: 3.5 }], ['path', { d: 'M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5M16 4.8a3.5 3.5 0 0 1 0 6.4M18.5 14.8c1.6.7 2.6 2.4 3 5.2' }]],
    sound: [['path', { d: 'M11 5 6 9H2v6h4l5 4z' }], ['path', { d: 'M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13' }]],
    expand: [['path', { d: 'M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5' }]],
    home: [['path', { d: 'M3 11 12 4l9 7M5 10v10h14V10' }]],
    calendar: [['rect', { x: 3, y: 5, width: 18, height: 16, rx: 2 }], ['path', { d: 'M3 10h18M8 3v4M16 3v4' }]],
    grid: [['rect', { x: 4, y: 4, width: 7, height: 7, rx: 1.5 }], ['rect', { x: 13, y: 4, width: 7, height: 7, rx: 1.5 }], ['rect', { x: 4, y: 13, width: 7, height: 7, rx: 1.5 }], ['rect', { x: 13, y: 13, width: 7, height: 7, rx: 1.5 }]],
    user: [['circle', { cx: 12, cy: 8, r: 4 }], ['path', { d: 'M4 21c1-4 4-6 8-6s7 2 8 6' }]],
    check: [['path', { d: 'm5 12 5 5 9-10' }]]
  });

  function reduced() { return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); }

  /* InfluenceTag — where the audience changed something: 「觀眾投票選出」「觀眾想再看」… */
  function InfluenceTag(p) {
    return h('span', { className: 'md-tag md-tag-influence' }, h(Icon, { name: 'people', size: 13 }), p.children);
  }

  /* ViewerCount — 「N 人正在看」; renders nothing below the threshold (default 10) */
  function ViewerCount(p) {
    var min = p.min == null ? 10 : p.min;
    if (p.count == null || p.count < min) return null;
    return h('span', { className: cx('md-viewers', p.onImage && 'on-image'), 'aria-live': 'off' }, h(Icon, { name: 'eye', size: 14 }),
      typeof p.label === 'function' ? p.label(p.count) : (p.label || p.count));
  }

  /* ReactionBar — after a video: like / want more / not interested (+ optional, skippable reason) */
  function ReactionBar(p) {
    var opts = p.options || [];
    var _r = React.useState(false), asking = _r[0], setAsking = _r[1];
    var cur = p.value || null;
    function pick(o) {
      var next = cur === o.value ? null : o.value;
      setAsking(!!(next && o.askReason && p.reasons && p.reasons.length));
      if (p.onChange) p.onChange(next, null);
    }
    return h('div', { className: cx('md-reactbar', p.compact && 'is-compact'), role: 'group', 'aria-label': p.label || p.title },
      p.title ? h('span', { className: 'md-reactbar-title' }, p.title) : null,
      h('div', { className: 'md-reactbar-opts' }, opts.map(function (o) {
        var on = cur === o.value;
        return h('button', { key: o.value, type: 'button', className: cx('md-chip', on && 'is-on'), 'aria-pressed': on ? 'true' : 'false',
          onClick: function () { pick(o); } }, o.icon ? h(Icon, { name: o.icon, size: 16 }) : null, o.label);
      })),
      asking ? h('div', { className: 'md-reactbar-reasons', role: 'group', 'aria-label': p.reasonPrompt },
        h('span', { className: 'md-meta' }, p.reasonPrompt),
        p.reasons.map(function (r) {
          return h('button', { key: r.value, type: 'button', className: 'md-chip md-chip-sm', onClick: function () { setAsking(false); if (p.onChange) p.onChange(cur, r.value); } }, r.label);
        }),
        p.skipLabel ? h('button', { type: 'button', className: 'md-linkbtn', onClick: function () { setAsking(false); } }, p.skipLabel) : null) : null,
      p.note ? h('span', { className: 'md-meta md-reactbar-note' }, p.note) : null);
  }

  /* LiveReactions — fixed reactions on the live picture, floating icons for ~2 s, can be hidden.
     `burst` = {kind: n} from the latest tick (already capped at 20 per second by the server). */
  function LiveReactions(p) {
    var opts = p.options || [];
    var _f = React.useState([]), floats = _f[0], setFloats = _f[1];
    var _c = React.useState(false), cool = _c[0], setCool = _c[1];
    var seq = React.useRef(0);
    var icons = {}; opts.forEach(function (o) { icons[o.value] = o.icon; });
    function spawn(map, mine) {
      if (p.hidden || reduced() || !map) return;
      var add = [];
      Object.keys(map).forEach(function (k) {
        for (var i = 0; i < Math.min(map[k], 20); i++) add.push({ id: ++seq.current, icon: icons[k] || 'heart', x: Math.round(Math.random() * 70), d: Math.round(Math.random() * 400), mine: mine });
      });
      if (!add.length) return;
      setFloats(function (f) { return f.concat(add).slice(-40); });
      var ids = add.map(function (a) { return a.id; });
      setTimeout(function () { setFloats(function (f) { return f.filter(function (x) { return ids.indexOf(x.id) < 0; }); }); }, 2600);
    }
    React.useEffect(function () { spawn(p.burst, false); }, [p.burst]);
    function press(o) {
      if (cool) return;
      setCool(true); setTimeout(function () { setCool(false); }, p.cooldownMs || 2000);
      spawn((function () { var m = {}; m[o.value] = 1; return m; })(), true);
      if (p.onReact) p.onReact(o.value);
    }
    return h('div', { className: 'md-lreact' },
      h('div', { className: 'md-lreact-floats', 'aria-hidden': 'true' }, p.hidden ? null : floats.map(function (f) {
        return h('span', { key: f.id, className: cx('md-float', f.mine && 'is-mine'), style: { left: f.x + 'px', animationDelay: f.d + 'ms' } }, h(Icon, { name: f.icon, size: 22 }));
      })),
      h('div', { className: 'md-lreact-bar' },
        h('div', { className: 'md-lreact-btns', role: 'group', 'aria-label': p.label }, opts.map(function (o) {
          return h('button', { key: o.value, type: 'button', className: 'md-lreact-btn', 'aria-label': o.label, title: o.label, disabled: cool,
            onClick: function () { press(o); } }, h(Icon, { name: o.icon, size: 20 }));
        })),
        p.toggleLabel ? h('button', { type: 'button', className: 'md-lreact-toggle', 'aria-pressed': p.hidden ? 'true' : 'false', onClick: p.onToggleHidden }, p.toggleLabel) : null));
  }

  /* PollCard — the 「觀眾決定」 vote. variant "tile" (amber Bento tile), "full" (page), "overlay" (end-of-slot 想／不想) */
  function PollCard(p) {
    var variant = p.variant || 'tile';
    var opts = p.options || [];
    var _s = React.useState(null), picked = _s[0], setPicked = _s[1];
    var voted = p.value != null;
    var sel = voted ? p.value : picked;
    var showResults = voted || p.closed;
    if (variant === 'overlay') {
      return h('div', { className: 'md-poll md-poll-overlay', role: 'group', 'aria-label': p.title },
        p.eyebrow ? h('span', { className: 'md-poll-eyebrow' }, p.eyebrow) : null,
        h('span', { className: 'md-poll-title' }, p.title),
        h('div', { className: 'md-poll-pair' }, opts.map(function (o, i) {
          var on = voted && p.value === o.id;
          return h('button', { key: o.id, type: 'button', className: cx('md-btn', i === 0 ? 'md-btn-primary' : 'md-btn-ghost', on && 'is-on'),
            'aria-pressed': on ? 'true' : 'false', onClick: function () { if (p.onVote) p.onVote(o.id); } }, on ? h(Icon, { name: 'check', size: 16 }) : null, o.title);
        })),
        p.note ? h('span', { className: 'md-meta' }, p.note) : null);
    }
    return h('div', { className: cx('md-poll', 'md-poll-' + variant, variant === 'tile' && 'md-tile', span(p.cols, p.rows)), role: 'group', 'aria-label': p.title },
      p.eyebrow ? h('span', { className: 'md-poll-eyebrow' }, p.eyebrow) : null,
      h('span', { className: 'md-poll-title' }, p.title),
      h('div', { className: 'md-poll-opts', role: 'radiogroup', 'aria-label': p.optionsLabel || p.title }, opts.map(function (o) {
        var on = sel === o.id;
        var win = p.closed && p.winner === o.id;
        return h('button', { key: o.id, type: 'button', role: 'radio', 'aria-checked': on ? 'true' : 'false', disabled: voted && !p.allowChange || p.closed,
          className: cx('md-poll-opt', on && 'is-on', win && 'is-win'), onClick: function () { setPicked(o.id); if (voted && p.allowChange && p.onVote) p.onVote(o.id); } },
          showResults ? h('span', { className: 'md-poll-bar', style: { width: (o.share || 0) + '%' }, 'aria-hidden': 'true' }) : null,
          o.images && o.images.length ? h('span', { className: 'md-poll-thumbs' }, o.images.slice(0, variant === 'full' ? 3 : 1).map(function (src, i) { return h('img', { key: i, src: src, alt: '' }); })) : null,
          h('span', { className: 'md-poll-opt-body' },
            h('span', { className: 'md-poll-opt-title' }, o.title),
            h('span', { className: 'md-poll-opt-sub' }, [o.sub, showResults && o.share != null ? o.share + '%' : null].filter(Boolean).join(' · '))));
      })),
      p.closed || voted ? null : h('button', { type: 'button', className: 'md-poll-submit', disabled: !picked, onClick: function () { if (picked && p.onVote) p.onVote(picked); } }, p.cta),
      p.note ? h('span', { className: 'md-poll-note' }, p.note) : null);
  }

  /* LivePlayer — official channel: starts at the schedule position, cannot seek; overlays go in children */
  function LivePlayer(p) {
    var ref = React.useRef(null);
    var _m = React.useState(p.muted !== false), muted = _m[0], setMuted = _m[1];
    React.useEffect(function () {
      var v = ref.current; if (!v) return;
      var off = p.offset || 0;
      function seek() { try { if (Math.abs(v.currentTime - off) > 1.5) v.currentTime = off; } catch (e) {} var pr = v.play(); if (pr && pr.catch) pr.catch(function () {}); }
      if (v.readyState >= 1) seek(); else v.addEventListener('loadedmetadata', seek, { once: true });
    }, [p.src, p.offset]);
    function full() { var el = ref.current && ref.current.parentNode; if (el && el.requestFullscreen) el.requestFullscreen(); }
    return h('div', { className: cx('md-player', 'md-player-live', p.className) },
      h('video', { ref: ref, src: p.src, poster: p.poster, muted: muted, playsInline: true, autoPlay: true, preload: 'auto',
        onEnded: p.onEnded, onTimeUpdate: p.onTime ? function (e) { p.onTime(e.target.currentTime); } : undefined, 'aria-label': p.label }),
      h('span', { className: 'md-scrim md-player-scrim', 'aria-hidden': 'true' }),
      p.badge ? h('span', { className: 'md-player-tl' }, p.badge) : null,
      p.topRight ? h('span', { className: 'md-player-tr' }, p.topRight) : null,
      h('div', { className: 'md-player-ctl' },
        h('button', { type: 'button', className: 'md-iconbtn', 'aria-label': muted ? p.unmuteLabel : p.muteLabel, onClick: function () { setMuted(!muted); } }, h(Icon, { name: muted ? 'sound-off' : 'sound', size: 18 })),
        h('button', { type: 'button', className: 'md-iconbtn', 'aria-label': p.fullscreenLabel, onClick: full }, h(Icon, { name: 'expand', size: 18 }))),
      p.children);
  }

  /* VideoPlayer — on-demand video with captions; highlight markers come from live reaction peaks */
  function VideoPlayer(p) {
    var ref = React.useRef(null);
    var _t = React.useState({ t: 0, d: p.duration || 0 }), tm = _t[0], setTm = _t[1];
    var maxT = React.useRef(0);
    React.useEffect(function () { maxT.current = 0; }, [p.src]);
    function onTime(e) {
      var v = e.target; maxT.current = Math.max(maxT.current, v.currentTime);
      setTm({ t: v.currentTime, d: v.duration || p.duration || 0 });
      if (p.onProgress) p.onProgress(maxT.current, v.duration || 0, false);
    }
    var d = tm.d || 1;
    return h('div', { className: 'md-vplayer' },
      h('div', { className: cx('md-player', p.vertical && 'is-vertical') },
        h('video', { ref: ref, src: p.src, poster: p.poster, controls: true, playsInline: true, autoPlay: p.autoPlay, preload: 'metadata', crossOrigin: 'anonymous',
          onTimeUpdate: onTime, onEnded: function (e) { if (p.onProgress) p.onProgress(e.target.duration, e.target.duration, true); if (p.onEnded) p.onEnded(); }, 'aria-label': p.label },
          p.captions ? h('track', { kind: 'subtitles', src: p.captions, srcLang: p.captionsLang || 'zh-Hant', label: p.captionsLabel || '字幕', default: true }) : null)),
      p.highlights && p.highlights.length ? h('div', { className: 'md-hl' },
        h('div', { className: 'md-hl-track' },
          h('span', { className: 'md-hl-fill', style: { width: Math.min(100, 100 * tm.t / d) + '%' } }),
          p.highlights.map(function (x, i) {
            return h('button', { key: i, type: 'button', className: 'md-hl-mark', style: { left: Math.min(100, 100 * ((x.start + x.end) / 2) / d) + '%' }, title: x.label, 'aria-label': x.label + ' ' + fmt(x.start),
              onClick: function () { if (ref.current) { ref.current.currentTime = x.start; ref.current.play(); } } });
          })),
        h('span', { className: 'md-meta' }, p.highlightsLabel)) : null);
  }
  function fmt(s) { s = Math.round(s || 0); return Math.floor(s / 60) + ':' + ('0' + s % 60).slice(-2); }

  /* VideoMeta / AIDisclosure */
  function VideoMeta(p) {
    return h('div', { className: 'md-vmeta' },
      p.eyebrow ? h('span', { className: 'md-vmeta-eyebrow' }, p.eyebrow) : null,
      h(p.as || 'h1', { className: 'md-vmeta-title' }, p.title),
      p.meta ? h('span', { className: 'md-vmeta-line' }, p.meta) : null,
      p.tags && p.tags.length ? h('div', { className: 'md-vmeta-tags' }, p.tags) : null,
      p.actions ? h('div', { className: 'md-vmeta-actions' }, p.actions) : null);
  }
  function AIDisclosure(p) {
    return h('p', { className: 'md-aidisc' }, h(Icon, { name: 'sparkle', size: 14 }), h('span', null, p.children));
  }

  /* SignInDialog — CAFECA: popup (desktop), redirect (mobile / in-app browsers), QR (another device) */
  function SignInDialog(p) {
    var ref = React.useRef(null);
    React.useEffect(function () {
      var d = ref.current; if (!d) return;
      if (p.open && !d.open) { if (d.showModal) d.showModal(); else d.setAttribute('open', ''); }
      if (!p.open && d.open) d.close();
    }, [p.open]);
    return h('dialog', { ref: ref, className: 'md-dialog', 'aria-labelledby': 'md-signin-t', onClose: p.onClose, onCancel: p.onClose },
      h('div', { className: 'md-dialog-head' },
        h('h2', { id: 'md-signin-t', className: 'md-dialog-title' }, p.title),
        h('button', { type: 'button', className: 'md-iconbtn', 'aria-label': p.closeLabel, onClick: p.onClose }, h(Icon, { name: 'x', size: 18 }))),
      p.body ? h('p', { className: 'md-dialog-body' }, p.body) : null,
      h('div', { className: 'md-dialog-actions' },
        h(SignInButton, { onClick: p.onPopup }, p.popupLabel),
        p.redirectLabel ? h(Button, { variant: 'ghost', onClick: p.onRedirect }, p.redirectLabel) : null),
      p.qr ? h('div', { className: 'md-dialog-qr' }, h('div', { className: 'md-dialog-qrbox' }, p.qr), p.qrLabel ? h('span', { className: 'md-meta' }, p.qrLabel) : null) : null,
      p.error ? h('p', { className: 'md-dialog-error', role: 'alert' }, p.error) : null,
      p.footer ? h('p', { className: 'md-meta' }, p.footer) : null);
  }

  /* AccountMenu — signed-in avatar menu */
  function AccountMenu(p) {
    var _o = React.useState(false), open = _o[0], setOpen = _o[1];
    var root = React.useRef(null);
    React.useEffect(function () {
      if (!open) return;
      function off(e) { if (root.current && !root.current.contains(e.target)) setOpen(false); }
      function esc(e) { if (e.key === 'Escape') setOpen(false); }
      document.addEventListener('mousedown', off); document.addEventListener('keydown', esc);
      return function () { document.removeEventListener('mousedown', off); document.removeEventListener('keydown', esc); };
    }, [open]);
    return h('div', { className: 'md-acct', ref: root },
      h('button', { type: 'button', className: 'md-acct-btn', 'aria-haspopup': 'menu', 'aria-expanded': open ? 'true' : 'false', onClick: function () { setOpen(!open); } },
        h('span', { className: 'md-avatar', 'aria-hidden': 'true' }, (p.name || '?').slice(0, 1).toUpperCase()), h('span', { className: 'md-acct-name' }, p.name)),
      open ? h('div', { className: 'md-acct-menu', role: 'menu' },
        p.sub ? h('span', { className: 'md-meta md-acct-sub' }, p.sub) : null,
        (p.items || []).map(function (it, i) {
          return it.href ? h('a', { key: i, role: 'menuitem', href: it.href, className: 'md-acct-item' }, it.label)
            : h('button', { key: i, type: 'button', role: 'menuitem', className: 'md-acct-item', onClick: function () { setOpen(false); if (it.onClick) it.onClick(); } }, it.label);
        })) : null);
  }

  /* Skeleton / EmptyState */
  function Skeleton(p) {
    return h('span', { className: cx('md-skel', span(p.cols, p.rows)), style: p.height ? { height: p.height } : null, 'aria-hidden': 'true' });
  }
  function EmptyState(p) {
    return h('div', { className: cx('md-empty', span(p.cols, p.rows)) },
      h('span', { className: 'md-empty-title' }, p.title),
      p.body ? h('span', { className: 'md-meta' }, p.body) : null,
      p.action || null);
  }

  /* TopicBento — one topic: lead tile 2×2 + up to four 1×1 */
  function TopicBento(p) {
    var vs = p.videos || [];
    return h('section', { className: 'md-topic', 'aria-labelledby': p.id },
      h(SectionHeader, { title: p.title, tag: p.tagNode ? null : p.tag, meta: p.meta, action: p.action, id: p.id, level: p.level || 3 }),
      p.tagNode ? h('div', { className: 'md-topic-tag' }, p.tagNode) : null,
      h(BentoGrid, { row: 'topic' }, vs.slice(0, 5).map(function (v, i) {
        // lead 2×2; the other 2×2 quarter is filled exactly: 1 → 2×2, 2 → 1×2 each, 3 → 1×1 + 1×1 + 2×1, 4 → 1×1 each
        var n = Math.min(vs.length, 5) - 1;
        var c = 1, r = 1;
        if (i === 0) { c = 2; r = 2; }
        else if (n === 1) { c = 2; r = 2; }
        else if (n === 2) { r = 2; }
        else if (n === 3 && i === 3) { c = 2; }
        return h(VideoTile, { key: v.href || i, image: v.image, alt: v.alt, title: v.title, subtitle: v.subtitle, href: v.href, focus: v.focus,
          size: i === 0 ? 'md' : 'sm', cols: c, rows: r });
      })));
  }

  /* BottomNav — phones: 首頁、節目表、主題、我的 */
  function BottomNav(p) {
    return h('nav', { className: 'md-bnav', 'aria-label': p.label || '主選單' }, (p.items || []).map(function (it, i) {
      return h('a', { key: i, href: it.href, className: cx('md-bnav-a', it.active && 'is-on'), 'aria-current': it.active ? 'page' : undefined },
        h(Icon, { name: it.icon, size: 20 }), h('span', null, it.label));
    }));
  }

  /* ---------------------------------------------------------------- v3: community (phase 2) and schedule/topic pages */
  Object.assign(PATHS, {
    flag: [['path', { d: 'M5 21V4M5 4h11l-2 4 2 4H5' }]],
    send: [['path', { d: 'M4 12 20 4l-6 16-3-7z' }]],
    chat: [['path', { d: 'M4 5h16v11H9l-5 4z' }]],
    star: [['path', { d: 'm12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z' }]],
    back: [['path', { d: 'm15 6-6 6 6 6' }]],
    list: [['path', { d: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01' }]],
    cc: [['rect', { x: 3, y: 6, width: 18, height: 12, rx: 2 }], ['path', { d: 'M10 10.5a2 2 0 1 0 0 3M16 10.5a2 2 0 1 0 0 3' }]],
    rotate: [['path', { d: 'M4 12a8 8 0 0 1 14-5.3L20 9M20 4v5h-5M20 12a8 8 0 0 1-14 5.3L4 15M4 20v-5h5' }]]
  });

  /* ChatPanel — live chat: pinned official note, messages, composer, moderation feedback; collapsible on phones */
  function ChatPanel(p) {
    var list = React.useRef(null);
    var _t = React.useState(''), text = _t[0], setText = _t[1];
    var _o = React.useState(p.defaultOpen !== false), open = _o[0], setOpen = _o[1];
    var max = p.max || 100;
    React.useEffect(function () { var el = list.current; if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 120) el.scrollTop = el.scrollHeight; }, [p.messages && p.messages.length]);
    function send(e) { e.preventDefault(); var t = text.trim(); if (!t || p.disabled) return; if (p.onSend) Promise.resolve(p.onSend(t)).then(function (ok) { if (ok !== false) setText(''); }); }
    return h('aside', { className: cx('md-chat', !open && 'is-closed'), 'aria-label': p.title },
      h('div', { className: 'md-chat-head' },
        h('h2', { className: 'md-chat-title' }, p.title),
        p.meta ? h('span', { className: 'md-meta' }, p.meta) : null,
        h('button', { type: 'button', className: 'md-linkbtn md-chat-toggle', 'aria-expanded': open ? 'true' : 'false', onClick: function () { setOpen(!open); } }, open ? p.collapseLabel : p.expandLabel)),
      open ? h(React.Fragment, null,
        p.pinned ? h('div', { className: 'md-chat-pin' }, h(Badge, { tone: 'now', dot: false }, p.pinnedLabel), h('span', null, p.pinned)) : null,
        h('ol', { className: 'md-chat-list', ref: list, 'aria-live': 'polite' }, (p.messages || []).map(function (m) {
          return h('li', { key: m.id, className: 'md-chat-msg' },
            h('b', null, m.nickname), h('span', null, m.text),
            p.onReport ? h('button', { type: 'button', className: 'md-chat-report', 'aria-label': p.reportLabel, title: p.reportLabel, onClick: function () { p.onReport(m); } }, h(Icon, { name: 'flag', size: 13 })) : null);
        })),
        p.notice ? h('p', { className: 'md-chat-notice', role: 'status' }, p.notice) : null,
        p.composer === false ? null : h('form', { className: 'md-chat-form', onSubmit: send },
          p.signedIn === false ? h(SignInButton, { variant: 'outline', onClick: p.onSignIn }, p.signInLabel) :
            h(React.Fragment, null,
              h('label', { className: 'md-sr', htmlFor: 'md-chat-in' }, p.inputLabel),
              h('input', { id: 'md-chat-in', className: 'md-input', value: text, maxLength: max, placeholder: p.placeholder, disabled: p.disabled, onChange: function (e) { setText(e.target.value); } }),
              h('button', { type: 'submit', className: 'md-iconbtn md-chat-send', 'aria-label': p.sendLabel, disabled: p.disabled || !text.trim() }, h(Icon, { name: 'send', size: 18 }))),
          p.hint ? h('span', { className: 'md-meta md-chat-hint' }, p.hint) : null)) : null);
  }

  /* WishCard — a merged wish: kind, text, +1 progress to the production threshold, status */
  var WISH_TONE = { open: 'neutral', topic: 'up', producing: 'now', done: 'up' };
  function WishCard(p) {
    var pct = Math.round(100 * Math.min(1, p.progress || 0));
    return h('article', { className: 'md-wish' },
      h('div', { className: 'md-wish-top' }, h('span', { className: 'md-meta' }, p.kindLabel), p.statusLabel ? h(Badge, { tone: WISH_TONE[p.status] || 'neutral', dot: false }, p.statusLabel) : null),
      h('p', { className: 'md-wish-text' }, p.text),
      p.note ? h('span', { className: 'md-meta' }, p.note) : null,
      h('div', { className: 'md-progress', role: 'progressbar', 'aria-label': p.progressLabel, 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': pct }, h('span', { style: { width: pct + '%' } })),
      h('div', { className: 'md-wish-foot' },
        h('span', { className: 'md-meta' }, p.countLabel),
        h('span', { className: 'md-wish-acts' },
          p.onReport ? h('button', { type: 'button', className: 'md-iconbtn', 'aria-label': p.reportLabel, title: p.reportLabel, onClick: p.onReport }, h(Icon, { name: 'flag', size: 15 })) : null,
          h('button', { type: 'button', className: cx('md-chip md-chip-sm', p.supported && 'is-on'), 'aria-pressed': p.supported ? 'true' : 'false', onClick: p.onSupport }, p.supported ? p.supportedLabel : p.supportLabel))));
  }

  /* WishComposer — topic (free text ≤ 40) or cast (1–2 actors + one line) */
  function WishComposer(p) {
    var _k = React.useState('topic'), kind = _k[0], setKind = _k[1];
    var _t = React.useState(''), text = _t[0], setText = _t[1];
    var _a = React.useState([]), cast = _a[0], setCast = _a[1];
    var max = p.max || 40;
    function toggle(hd) { setCast(function (c) { return c.indexOf(hd) >= 0 ? c.filter(function (x) { return x !== hd; }) : c.concat([hd]).slice(-2); }); }
    function submit(e) {
      e.preventDefault();
      if (!text.trim() || (kind === 'cast' && !cast.length)) return;
      Promise.resolve(p.onSubmit && p.onSubmit({ kind: kind, text: text.trim(), actors: kind === 'cast' ? cast : [] })).then(function (ok) { if (ok !== false) { setText(''); setCast([]); } });
    }
    return h('form', { className: 'md-wishform', onSubmit: submit },
      h('div', { className: 'md-wishform-head' }, h('h2', { className: 'md-wishform-title', id: 'md-wish-t' }, p.title), p.left != null ? h('span', { className: 'md-meta' }, p.leftLabel) : null),
      h(SegmentedTabs, { label: p.kindLabel, value: kind, onChange: setKind, options: [{ value: 'topic', label: p.topicLabel }, { value: 'cast', label: p.castLabel }] }),
      kind === 'cast' ? h('div', { className: 'md-wishform-cast', role: 'group', 'aria-label': p.castPick },
        (p.actors || []).map(function (a) {
          var on = cast.indexOf(a.handle) >= 0;
          return h('button', { key: a.handle, type: 'button', className: cx('md-castpick', on && 'is-on'), 'aria-pressed': on ? 'true' : 'false', onClick: function () { toggle(a.handle); } },
            h('img', { src: a.image, alt: '' }), h('span', null, a.name), h('small', null, '@' + a.handle));
        })) : null,
      h('label', { className: 'md-field' }, h('span', { className: 'md-meta' }, kind === 'cast' ? p.castTextLabel : p.topicTextLabel),
        h('input', { className: 'md-input', value: text, maxLength: max, placeholder: kind === 'cast' ? p.castPlaceholder : p.topicPlaceholder, onChange: function (e) { setText(e.target.value); } }),
        h('span', { className: 'md-meta md-count' }, text.length + ' / ' + max)),
      p.rules ? h('span', { className: 'md-meta' }, p.rules) : null,
      h('div', { className: 'md-wishform-foot' }, p.footer ? h('span', { className: 'md-meta' }, p.footer) : h('span'),
        h(Button, { type: 'submit', disabled: p.disabled || !text.trim() || (kind === 'cast' && !cast.length) }, p.submitLabel)));
  }

  /* AskActor — question box (≤ 60, 3 a day) and the asker's own questions with the actor's text reply */
  function AskActor(p) {
    var _t = React.useState(''), text = _t[0], setText = _t[1];
    var max = p.max || 60;
    function submit(e) { e.preventDefault(); if (!text.trim()) return; Promise.resolve(p.onAsk && p.onAsk(text.trim())).then(function (ok) { if (ok !== false) setText(''); }); }
    return h('div', { className: 'md-ask' },
      h('form', { className: 'md-ask-form', onSubmit: submit },
        h('div', { className: 'md-wishform-head' }, h('h2', { className: 'md-wishform-title' }, p.title), p.leftLabel ? h('span', { className: 'md-meta' }, p.leftLabel) : null),
        h('label', { className: 'md-field' }, h('span', { className: 'md-meta' }, p.inputLabel),
          h('textarea', { className: 'md-input', rows: 2, value: text, maxLength: max, placeholder: p.placeholder, onChange: function (e) { setText(e.target.value); } }),
          h('span', { className: 'md-meta md-count' }, text.length + ' / ' + max)),
        h('div', { className: 'md-wishform-foot' }, h('span', { className: 'md-meta' }, p.footer),
          p.signedIn === false ? h(SignInButton, { onClick: p.onSignIn }) : h(Button, { type: 'submit', disabled: p.disabled || !text.trim() }, p.submitLabel))),
      (p.replies || []).map(function (r) {
        return h('div', { key: r.id, className: 'md-reply' },
          h('p', { className: 'md-reply-q' }, h('span', { className: 'md-meta' }, p.youAskedLabel), ' ', r.question),
          h('div', { className: 'md-reply-head' },
            p.avatar ? h('img', { src: p.avatar, alt: '' }) : null,
            h('b', null, p.actorName),
            h('span', { className: 'md-reply-label' }, p.aiLabel)),
          h('p', { className: 'md-reply-a' }, r.reply || p.pendingLabel),
          p.replyNote ? h('span', { className: 'md-meta' }, p.replyNote) : null);
      }));
  }

  /* AnswerTile — an actor's video answer (VideoTile with the question) */
  function AnswerTile(p) {
    return h(VideoTile, { image: p.image, title: '「' + p.question + '」', subtitle: p.meta, href: p.href, size: 'sm', focus: 'top',
      badge: h(Badge, { tone: 'neutral', dot: false }, p.aiLabel), cols: p.cols, rows: p.rows });
  }

  /* TopicHeader — topic page title: name, reason, regroup time and count */
  function TopicHeader(p) {
    return h('header', { className: 'md-topichead' },
      p.eyebrow ? h('span', { className: 'md-vmeta-eyebrow' }, p.eyebrow) : null,
      h('h1', { className: 'md-topichead-title' }, p.title),
      h('div', { className: 'md-vmeta-tags' }, p.tags || null, p.meta ? h('span', { className: 'md-meta' }, p.meta) : null));
  }

  /* ScheduleDay / ScheduleWeek — the official channel's prime time, one row per day */
  function ScheduleDay(p) {
    return h('section', { className: cx('md-sday', p.today && 'is-today'), 'aria-label': p.label },
      h('h3', { className: 'md-sday-d' }, p.label),
      h('div', { className: 'md-sday-slots' }, (p.slots || []).map(function (s) {
        return h(DaySlot, { key: s.id, day: s.range + (s.now ? ' · ' + (p.nowLabel || '') : ''), title: s.title, time: s.meta, today: !!s.now, href: s.href, tag: s.tag });
      })));
  }
  function ScheduleWeek(p) {
    return h('div', { className: 'md-sweek' }, (p.days || []).map(function (d) {
      return h(ScheduleDay, { key: d.label, label: d.label, today: d.today, slots: d.slots, nowLabel: p.nowLabel });
    }));
  }

  var api = { Logo: Logo, Icon: Icon, Button: Button, SignInButton: SignInButton, SearchField: SearchField, SegmentedTabs: SegmentedTabs,
    SiteHeader: SiteHeader, SiteFooter: SiteFooter, Badge: Badge, Tag: Tag, ProgressBar: ProgressBar, SectionHeader: SectionHeader,
    BentoGrid: BentoGrid, VideoTile: VideoTile, ThemeTile: ThemeTile, RankTile: RankTile, RankRow: RankRow, DaySlot: DaySlot, ActorCard: ActorCard,
    InfluenceTag: InfluenceTag, ViewerCount: ViewerCount, ReactionBar: ReactionBar, LiveReactions: LiveReactions, PollCard: PollCard,
    LivePlayer: LivePlayer, VideoPlayer: VideoPlayer, VideoMeta: VideoMeta, AIDisclosure: AIDisclosure, SignInDialog: SignInDialog,
    AccountMenu: AccountMenu, Skeleton: Skeleton, EmptyState: EmptyState, TopicBento: TopicBento, BottomNav: BottomNav,
    ChatPanel: ChatPanel, WishCard: WishCard, WishComposer: WishComposer, AskActor: AskActor, AnswerTile: AnswerTile,
    TopicHeader: TopicHeader, ScheduleDay: ScheduleDay, ScheduleWeek: ScheduleWeek };
  window.Midea = Object.assign(window.Midea || {}, api);
})();
