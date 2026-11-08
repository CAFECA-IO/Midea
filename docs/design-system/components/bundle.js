/* @ds-bundle: {"format":4,"namespace":"Midea","components":[{"name":"Logo"},{"name":"Icon"},{"name":"Button"},{"name":"SignInButton"},{"name":"SearchField"},{"name":"SegmentedTabs"},{"name":"SiteHeader"},{"name":"SiteFooter"},{"name":"Badge"},{"name":"Tag"},{"name":"ProgressBar"},{"name":"SectionHeader"},{"name":"BentoGrid"},{"name":"VideoTile"},{"name":"ThemeTile"},{"name":"RankTile"},{"name":"RankRow"},{"name":"DaySlot"},{"name":"ActorCard"}]} */
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
      h('span', { className: 'md-meta' }, p.time));
  }

  function ActorCard(p) {
    return h('a', { href: p.href || '#', className: 'md-actor' },
      h('img', { src: p.image, alt: '' }),
      h('span', { className: 'md-actor-body' },
        h('span', { className: 'md-actor-name' }, p.name),
        h('span', { className: 'md-meta' }, '@' + p.handle + (p.role ? ' · ' + p.role : '')),
        p.works ? h('span', { className: 'md-actor-works' }, p.works) : null));
  }

  var api = { Logo: Logo, Icon: Icon, Button: Button, SignInButton: SignInButton, SearchField: SearchField, SegmentedTabs: SegmentedTabs,
    SiteHeader: SiteHeader, SiteFooter: SiteFooter, Badge: Badge, Tag: Tag, ProgressBar: ProgressBar, SectionHeader: SectionHeader,
    BentoGrid: BentoGrid, VideoTile: VideoTile, ThemeTile: ThemeTile, RankTile: RankTile, RankRow: RankRow, DaySlot: DaySlot, ActorCard: ActorCard };
  window.Midea = Object.assign(window.Midea || {}, api);
})();
