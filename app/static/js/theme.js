/* Shared appearance only. No account, module or API permissions are changed. */
(() => {
  const root = document.documentElement;
  const key = 'jarvis.appearance';
  const valid = value => ['light', 'dark', 'system'].includes(value);
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  let preference = 'system';
  try { const saved = localStorage.getItem(key); if (valid(saved)) preference = saved; } catch {}
  function apply() {
    const theme = preference === 'system' ? (system.matches ? 'dark' : 'light') : preference;
    root.dataset.jarvisTheme = theme;
    root.dataset.jarvisAppearance = preference;
    document.querySelectorAll('[data-theme-select]').forEach(select => { select.value = preference; });
    document.querySelectorAll('meta[name="theme-color"]').forEach(meta => {
      meta.content = theme === 'dark' ? '#101b2b' : '#f4f7f6';
      meta.removeAttribute('media');
    });
  }
  apply(); // Run in <head>, before page styles are painted.
  system.addEventListener('change', () => { if (preference === 'system') apply(); });
  window.addEventListener('storage', event => {
    if (event.key !== key && event.key !== null) return;
    preference = valid(event.newValue) ? event.newValue : 'system';
    apply();
  });
  const paths = {
    home:'M3 10 12 3l9 7v11h-6v-7H9v7H3Z',
    calendar:'M4 5h16v16H4ZM4 10h16M8 3v4m8-4v4',
    check:'M9 4H4v17h17V11M9 11l4 4L22 4',
    sun:'M12 2v2m0 16v2M2 12h2m16 0h2M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
    meal:'M4 3v7q0 3 3 3t3-3V3M7 3v19M19 22V3q-5 4-5 10h5',
    settings:'M4 7h16M4 17h16M8 4v6m8 4v6',
    paw:'M8 13q4-5 8 0l3 5q0 4-7 1-7 3-7-1ZM5 6a2 2 0 1 0 0 .1M10 3a2 2 0 1 0 0 .1M16 4a2 2 0 1 0 0 .1M21 8a2 2 0 1 0 0 .1',
    energy:'m13 2-9 12h7l-1 8 10-13h-8Z',
    camera:'M3 6h13v14H3Zm13 5 5-3v10l-5-3',
    pill:'M8 4a5 5 0 0 1 7 0l5 5a5 5 0 0 1-7 7l-5-5a5 5 0 0 1 0-7Zm1 8 7-7',
    cart:'M2 3h3l3 13h11l3-9H6M10 20h.1M18 20h.1',
    star:'m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9Z',
    bell:'M6 9a6 6 0 0 1 12 0v5l2 3H4l2-3ZM10 21h4M12 1v2',
    smile:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM8 14q4 5 8 0M8 9h.01M16 9h.01',
    users:'M16 21v-3q0-4-6-4t-6 4v3M14 4a4 4 0 1 1-8 0 4 4 0 0 1 8 0M18 8q4 0 4 4m-3 3q3 1 3 5',
    link:'m9 15 6-6M8 17l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m0 0 1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0',
  };
  function icon(name) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true'); svg.classList.add('ui-icon');
    const path = document.createElementNS(svg.namespaceURI, 'path'); path.setAttribute('d', paths[name] || paths.settings); svg.append(path);
    return svg;
  }
  window.JarvisUI = {icon};
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-theme-control]').forEach(host => {
      const label = document.createElement('label'); label.className = 'theme-control';
      const caption = document.createElement('span'); caption.append(icon('sun'), document.createTextNode('Tema'));
      const select = document.createElement('select'); select.dataset.themeSelect = ''; select.setAttribute('aria-label', 'Vælg farvetema');
      for (const [value, text] of [['system','Følg enhed'],['light','Lyst'],['dark','Mørkt']]) {
        const option = document.createElement('option'); option.value = value; option.textContent = text; select.append(option);
      }
      select.value = preference;
      select.addEventListener('change', () => { preference = select.value; try { localStorage.setItem(key, preference); } catch {} apply(); });
      label.append(caption, select); host.append(label);
    });
    document.querySelectorAll('.app-brand-mark,.admin-brand-mark').forEach(mark => mark.replaceChildren(icon('home')));
    const adminIcons = {overview:'home',home:'home',modules:'check',connections:'link',users:'users',system:'energy',advanced:'settings'};
    document.querySelectorAll('[data-admin-target]').forEach(button => button.prepend(icon(adminIcons[button.dataset.adminTarget])));
  });
})();
