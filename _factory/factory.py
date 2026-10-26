#!/usr/bin/env python3
"""Page factory: the whole thing in one file. Python standard library only; needs Chrome or Edge.

Turns design-tool exports ("dc bundles", which only render with JavaScript) into static,
per-language, SEO-ready pages in the site. The repo root IS the website; this folder starts with
"_" so Jekyll (GitHub Pages) never publishes it. See _factory/README.md.

    python _factory/factory.py build [page]     regenerate the pages from their templates
    python _factory/factory.py verify [page]    pixel-compare them to the templates, check the
                                                <head>, links, and that nothing here is published
    python _factory/factory.py serve [port]     preview exactly what GitHub Pages would publish

To add a page: drop its design export next to this file and add an entry to PAGES below.
"""
import base64
import gzip
import hashlib
import html as htmllib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

FACTORY = Path(__file__).resolve().parent
ROOT = FACTORY.parent  # the repo root is the website

# ======================================================================================
# PAGE DEFINITIONS: what the design export does NOT contain (URLs, per-language <head> text,
# structured data, favicon, scripts). Re-exporting a template never touches this.
# ======================================================================================
BASE_URL = 'https://thebrousse.github.io/runtimenorth'  # no trailing slash; one line to change for a custom domain
SITE_NAME = 'Runtime North'
STORE_URL = 'https://apps.microsoft.com/detail/9PDWLDH31XLZ'

# title <= ~60 chars, description <= ~160 chars (the build warns otherwise).
SCATTERPOP_LANGS = {
    'en': {
        'label': 'English',
        'og_locale': 'en_US',
        'title': 'Scatter POP: Free Brick Breaker Game for Windows PC',
        'description': 'Free brick breaker for Windows 10 and 11. Aim one shot, chain bombs, melt steel in short turn-based runs. No ads, no account, plays offline.',
        'store_hl': None,  # English: let the Store use the visitor's own language
        'store_alt': 'Get Scatter POP on the Microsoft Store',
    },
    'fr': {
        'label': 'Français',
        'og_locale': 'fr_FR',
        'title': 'Scatter POP : casse-briques gratuit pour Windows (PC)',
        'description': 'Casse-briques gratuit pour Windows 10 et 11. Visez d’un geste, enchaînez les bombes, faites fondre l’acier. Parties courtes, sans pub, sans compte, hors ligne.',
        'store_hl': 'fr-FR',
        'store_alt': 'Télécharger Scatter POP sur le Microsoft Store',
    },
    'es': {
        'label': 'Español',
        'og_locale': 'es_ES',
        'title': 'Scatter POP: juego de romper ladrillos gratis para PC',
        'description': 'Juego de romper ladrillos gratis para Windows 10 y 11. Apunta con un gesto, encadena bombas y funde el acero. Sin anuncios, sin cuenta, sin conexión.',
        'store_hl': 'es-ES',
        'store_alt': 'Obtener Scatter POP en Microsoft Store',
    },
}

# The "Candy Icon" component (CSS in the template) redrawn as SVG with the same colours,
# proportions and -6deg tilt. Inlined as a data URI: no image file anywhere.
# Simplified for tab-icon sizes (no dot texture, no soft shadows).
SCATTERPOP_FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
<defs>
<clipPath id="r"><rect width="100" height="100" rx="20"/></clipPath>
<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2FA8FF"/><stop offset=".38" stop-color="#5FC6FF"/><stop offset=".68" stop-color="#9BE0FF"/><stop offset="1" stop-color="#FFD98F"/></linearGradient>
<radialGradient id="glow" gradientUnits="userSpaceOnUse" cx="77" cy="19" r="35"><stop offset="0" stop-color="#fff" stop-opacity=".36"/><stop offset=".72" stop-color="#fff" stop-opacity="0"/></radialGradient>
<linearGradient id="mint" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7FF0C4"/><stop offset=".55" stop-color="#35D398"/><stop offset="1" stop-color="#1FB47D"/></linearGradient>
<linearGradient id="lemon" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFE38A"/><stop offset=".55" stop-color="#FFC531"/><stop offset="1" stop-color="#F5A800"/></linearGradient>
<linearGradient id="cherry" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FF8FA6"/><stop offset=".55" stop-color="#FF4D6D"/><stop offset="1" stop-color="#E82C52"/></linearGradient>
<linearGradient id="hi" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".9"/><stop offset="1" stop-color="#fff" stop-opacity=".05"/></linearGradient>
<radialGradient id="ball" cx=".36" cy=".3" r=".948"><stop offset="0" stop-color="#FFE2BF"/><stop offset=".42" stop-color="#FFA75E"/><stop offset=".82" stop-color="#F26D14"/></radialGradient>
</defs>
<g clip-path="url(#r)">
<rect width="100" height="100" fill="url(#bg)"/>
<circle cx="77" cy="19" r="35" fill="url(#glow)"/>
<g transform="rotate(-6 50 50)">
<rect x="17" y="19.2" width="31" height="31" rx="7.5" fill="#128A5E"/><rect x="17" y="17" width="31" height="31" rx="7.5" fill="url(#mint)"/><rect x="20.7" y="20.1" width="23.6" height="9.3" rx="4.5" fill="url(#hi)"/>
<rect x="52" y="19.2" width="31" height="31" rx="7.5" fill="#C77F00"/><rect x="52" y="17" width="31" height="31" rx="7.5" fill="url(#lemon)"/><rect x="55.7" y="20.1" width="23.6" height="9.3" rx="4.5" fill="url(#hi)"/>
<rect x="17" y="54.2" width="31" height="31" rx="7.5" fill="#B01238"/><rect x="17" y="52" width="31" height="31" rx="7.5" fill="url(#cherry)"/><rect x="20.7" y="55.1" width="23.6" height="9.3" rx="4.5" fill="url(#hi)"/>
<circle cx="67.5" cy="70.5" r="18.15" fill="#963A0A" fill-opacity=".45"/>
<circle cx="67.5" cy="67.5" r="18.15" fill="url(#ball)"/>
<ellipse cx="62.3" cy="57.4" rx="5" ry="3" transform="rotate(-30 62.3 57.4)" fill="#fff" fill-opacity=".92"/>
</g>
</g>
</svg>"""

# On Windows 11, open the Microsoft Store app directly; everywhere else the web link is used.
# Lived in the page shell (not the template), so the build owns it.
STORE_LINK_SCRIPT = """(function () {
  var STORE_PREFIX = 'https://apps.microsoft.com/detail/';
  var isWin11 = false;
  var uad = navigator.userAgentData;
  if (uad && uad.platform === 'Windows' && uad.getHighEntropyValues) {
    uad.getHighEntropyValues(['platformVersion']).then(function (v) {
      isWin11 = parseInt(String(v.platformVersion).split('.')[0], 10) >= 13;
    }).catch(function () {});
  }
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href^="' + STORE_PREFIX + '"]');
    if (!a || !isWin11 || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey) return;
    e.preventDefault();
    var href = a.getAttribute('href');
    var cid = /[?&]cid=([^&#]*)/.exec(href);
    window.location.href = 'ms-windows-store://pdp/?productid=' + href.slice(STORE_PREFIX.length).split(/[?#]/)[0] + (cid ? '&cid=' + cid[1] : '');
  });
})();"""


def scatterpop_json_ld(lang, url):
    return {
        '@context': 'https://schema.org',
        '@type': ['VideoGame', 'SoftwareApplication'],
        'name': 'Scatter POP',
        'description': SCATTERPOP_LANGS[lang]['description'],
        'url': url,
        'inLanguage': lang,
        'applicationCategory': 'GameApplication',
        'operatingSystem': 'Windows 10, Windows 11',
        'isAccessibleForFree': True,
        'downloadUrl': STORE_URL,
        'offers': {
            '@type': 'Offer',
            'price': '0',
            'priceCurrency': 'USD',
            'availability': 'https://schema.org/InStock',
            'url': STORE_URL,
        },
        'publisher': {'@type': 'Organization', 'name': SITE_NAME, 'url': BASE_URL + '/'},
    }


PAGES = {
    'scatterpop': {
        'template': FACTORY / 'scatterpop.template.html',  # the design export: the source of truth
        'out_dir': 'scatterpop',  # site-relative; non-default languages go to scatterpop/<lang>/
        'default_lang': 'en',
        'langs': SCATTERPOP_LANGS,
        'base_url': BASE_URL,
        'site_name': SITE_NAME,
        'home_link_in_template': '../index.html',  # the template's link back to the studio homepage
        # Store links: `hl` (per language, see store_hl) opens the listing in the visitor's language; `cid` makes
        # Partner Center's Acquisitions report show which page and language produce installs.
        'store': {'url': STORE_URL, 'cid': 'site-scatterpop-{lang}'},
        'theme_color': '#2FA8FF',
        'preload_families': ['Baloo 2', 'Nunito'],  # above-the-fold fonts; their latin file is preloaded
        'favicon_svg': SCATTERPOP_FAVICON_SVG,
        'inline_script': STORE_LINK_SCRIPT,
        'json_ld': scatterpop_json_ld,
        # Optional: 'og_image': lambda lang: {'url': 'https://…/og.jpg', 'alt': '…'} to emit og:image /
        # twitter:image. Off on purpose: it must be a real file and this site keeps image files out.
        'og_image': None,
    },
}

# ======================================================================================
# ENGINE
# ======================================================================================
MAX_DIFF = 0.002  # verify: fraction of pixels allowed to differ
FREEZE = '*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}'
MIME = {'.html': 'text/html; charset=utf-8', '.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.js': 'text/javascript',
        '.css': 'text/css', '.json': 'application/json', '.xml': 'application/xml', '.txt': 'text/plain'}

# ---- JavaScript that runs inside the page (injected into a temp copy of the template) --------
# Polls until the template has rendered and settled, then writes its result into the DOM as a
# base64 <meta id="__extract">, which `chrome --dump-dom` hands back to Python.
EXTRACT_JS = r'''(function () {
  var ARG = __ARG__;
  async function extract(a) {
    var root = document.getElementById('dc-root');
    var probe = root.querySelector('.sc-interp');
    var flat = !!probe && getComputedStyle(probe).display === 'contents';
    var words = document.body.innerText.split(/\s+/).filter(Boolean).length;
    var toB64 = function (blob) {
      return new Promise(function (res) {
        var fr = new FileReader();
        fr.onload = function () { res(String(fr.result).split(',')[1]); };
        fr.readAsDataURL(blob);
      });
    };
    var images = [];
    var srcs = Array.from(new Set(Array.from(root.querySelectorAll('img')).map(function (i) { return i.getAttribute('src'); })));
    for (var k = 0; k < srcs.length; k++) {
      var blob = window.__resourceBlobs && window.__resourceBlobs[srcs[k]];
      if (!blob) throw new Error('img is not a bundled blob: ' + String(srcs[k]).slice(0, 80));
      images.push({ src: srcs[k], mime: blob.type, b64: await toB64(blob) });
    }
    // Heading semantics with identical rendering: the keyword pill becomes the <h1>, the tagline a plain
    // block, the feature-card <h3>s become <h2>s. Done on the live DOM (discarded afterwards); any property
    // the browser's heading defaults would change (in practice: the pill's margins) is pinned back to its
    // previous value. Responsive values such as clamp() are never touched.
    var h1 = root.querySelector('h1'), pill = h1 && h1.previousElementSibling, firstH2 = root.querySelector('h2');
    var swaps = [];
    if (h1 && pill && !/^H[1-6]$/.test(pill.tagName) && pill.textContent.trim() && firstH2) {
      swaps.push([pill, 'h1'], [h1, 'div']);
      Array.from(root.querySelectorAll('h3')).forEach(function (h) {
        if (h.compareDocumentPosition(firstH2) & Node.DOCUMENT_POSITION_FOLLOWING) swaps.push([h, 'h2']);
      });
    }
    var UA_PROPS = ['display', 'margin-top', 'margin-right', 'margin-bottom', 'margin-left', 'font-size', 'font-weight', 'unicode-bidi'];
    swaps.forEach(function (s) {
      var old = s[0], before = getComputedStyle(old), snap = {};
      UA_PROPS.forEach(function (p) { snap[p] = before.getPropertyValue(p); });
      var el = document.createElement(s[1]);
      Array.from(old.attributes).forEach(function (at) { el.setAttribute(at.name, at.value); });
      while (old.firstChild) el.appendChild(old.firstChild);
      old.replaceWith(el);
      var after = getComputedStyle(el);
      var pin = UA_PROPS.filter(function (p) { return after.getPropertyValue(p) !== snap[p]; });
      if (pin.length) el.setAttribute('style', (el.getAttribute('style') || '').replace(/;?\s*$/, ';') + pin.map(function (p) { return p + ':' + snap[p]; }).join(';'));
    });
    var clone = root.cloneNode(true);
    var scaffolding = /^data-(dc-tpl|comment-anchor|sc-name|screen-label)$/;
    [clone].concat(Array.from(clone.querySelectorAll('*'))).forEach(function (el) {
      Array.from(el.attributes).forEach(function (at) { if (scaffolding.test(at.name)) el.removeAttribute(at.name); });
    });
    // Store links: language + campaign id in the href, and the game's name in the badge alt / link label.
    if (a.store) Array.from(clone.querySelectorAll('a[href^="' + a.store.url + '"]')).forEach(function (l) {
      l.setAttribute('href', a.store.href);
      l.setAttribute('aria-label', a.store.label);
      Array.from(l.querySelectorAll('img')).forEach(function (i) { i.setAttribute('alt', a.store.label); });
    });
    // The JS language buttons become real links to the per-language URLs.
    Array.from(clone.querySelectorAll('button[data-lang]')).forEach(function (b) {
      var code = b.getAttribute('data-lang');
      var el = document.createElement('a');
      Array.from(b.attributes).forEach(function (at) { if (at.name !== 'data-lang') el.setAttribute(at.name, at.value); });
      el.setAttribute('href', a.switcher[code].href);
      el.setAttribute('hreflang', code);
      el.setAttribute('lang', code);
      if (a.switcher[code].current) el.setAttribute('aria-current', 'page');
      while (b.firstChild) el.appendChild(b.firstChild);
      b.replaceWith(el);
    });
    var home = Array.from(clone.querySelectorAll('a')).find(function (x) { return x.getAttribute('href') === a.homeFrom; });
    if (home) home.setAttribute('href', a.homeTo);
    if (flat) Array.from(clone.querySelectorAll('span.sc-interp')).forEach(function (s) { s.replaceWith(...s.childNodes); });
    // CSS: <style> text, plus rules the runtime inserted through the CSSOM (hover states), which
    // never show up in serialized HTML.
    var styles = [], cssom = [], fontCss = '';
    document.querySelectorAll('style').forEach(function (st) {
      var t = st.textContent;
      if (!t.trim()) { if (st.sheet) Array.from(st.sheet.cssRules).forEach(function (r) { cssom.push(r.cssText); }); }
      else if (t.indexOf('@font-face') >= 0) fontCss += t + '\n';
      else if (!t.trim().startsWith('x-dc{')) styles.push(t.trim());
    });
    return { html: clone.outerHTML, text: clone.textContent, h1: (root.querySelector('h1') || {}).textContent || '',
             words: words, styles: styles, cssom: cssom, fontCss: fontCss, images: images, retagged: swaps.length };
  }
  var last = -1, same = 0, ticks = 0, done = false;
  var iv = setInterval(async function () {
    if (done) return;
    ticks++;
    var root = document.getElementById('dc-root');
    if (!root || !root.querySelector('h1')) return;
    var n = document.body.innerHTML.length;
    same = n === last ? same + 1 : 0;
    last = n;
    if (same < 3 || (document.fonts.status !== 'loaded' && ticks < 80)) return;
    done = true;
    clearInterval(iv);
    var out;
    try { out = await extract(ARG); } catch (e) { out = { error: String((e && e.stack) || e) }; }
    var s = JSON.stringify(out).replace(/[\u007f-￿]/g, function (c) { return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4); });
    var m = document.createElement('meta');
    m.id = '__extract';
    m.setAttribute('content', btoa(s));
    document.body.appendChild(m);
  }, 100);
})();'''

# Once the template has rendered and settled, freeze its animations (for screenshot comparison).
FREEZE_JS = r'''(function () {
  var last = -1, same = 0, ticks = 0;
  var iv = setInterval(function () {
    ticks++;
    var r = document.getElementById('dc-root');
    if (!r || !r.querySelector('h1')) return;
    var n = document.body.innerHTML.length;
    same = n === last ? same + 1 : 0;
    last = n;
    if (same < 3 || (document.fonts.status !== 'loaded' && ticks < 80)) return;
    clearInterval(iv);
    var s = document.createElement('style');
    s.textContent = '__FREEZE__';
    document.head.appendChild(s);
  }, 100);
})();'''

# Loads two PNGs (as data URIs, so the canvas stays untainted) and reports how many pixels differ.
DIFF_JS = r'''(function () {
  var A = document.getElementById('a'), B = document.getElementById('b'), t = 0;
  // A polling timer (not img.decode()) keeps Chrome's virtual clock running until the images are ready.
  var iv = setInterval(function () {
    t++;
    if (!(A.complete && B.complete && A.naturalWidth && B.naturalWidth) && t < 200) return;
    clearInterval(iv);
    var out;
    try {
      if (A.naturalWidth !== B.naturalWidth || A.naturalHeight !== B.naturalHeight) {
        out = { sizes: [A.naturalWidth, A.naturalHeight, B.naturalWidth, B.naturalHeight] };
      } else {
        var px = function (i) {
          var c = document.createElement('canvas'); c.width = i.naturalWidth; c.height = i.naturalHeight;
          var x = c.getContext('2d'); x.drawImage(i, 0, 0); return x.getImageData(0, 0, c.width, c.height).data;
        };
        var da = px(A), db = px(B), n = 0;
        for (var i = 0; i < da.length; i += 4)
          if (Math.abs(da[i] - db[i]) > 8 || Math.abs(da[i + 1] - db[i + 1]) > 8 || Math.abs(da[i + 2] - db[i + 2]) > 8) n++;
        out = { ratio: n / (da.length / 4), px: n, w: A.naturalWidth, h: A.naturalHeight };
      }
    } catch (e) { out = { error: String((e && e.stack) || e) }; }
    var m = document.createElement('meta'); m.id = '__diff'; m.setAttribute('content', btoa(JSON.stringify(out)));
    document.body.appendChild(m);
  }, 50);
})();'''


# ---- small helpers ----------------------------------------------------------------------------
def warn(msg):
    print(f'  ! {msg}')


def esc_attr(s):
    return str(s).replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;')


def esc_text(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;')


def rel_dir(frm, to):
    """Relative URL (with trailing slash) from directory `frm` to directory `to`, both site-relative."""
    r = posixpath.relpath('/' + to, '/' + frm)
    return './' if r == '.' else r + '/'


def page_dir(cfg, lang):
    return cfg['out_dir'] if lang == cfg['default_lang'] else f"{cfg['out_dir']}/{lang}"


def url_of(cfg, lang):
    return f"{cfg['base_url']}/{page_dir(cfg, lang)}/"


def store_href(cfg, lang):
    hl = cfg['langs'][lang].get('store_hl')
    params = ([f'hl={hl}'] if hl else []) + ['cid=' + cfg['store']['cid'].format(lang=lang)]
    return cfg['store']['url'] + '?' + '&'.join(params)


def svg_data_uri(svg):
    """SVG -> data URI escaping only what must be escaped (smaller than base64, gzips better)."""
    q = '%22' if "'" in svg else "'"
    s = re.sub(r'\s+', ' ', svg).strip()
    for a, b in (('%', '%25'), ('&', '%26'), ('"', q), ('#', '%23'), ('<', '%3C'), ('>', '%3E')):
        s = s.replace(a, b)
    return 'data:image/svg+xml,' + s


def inject_before_body_end(text, snippet):
    i = text.rfind('</body>')
    if i < 0:
        sys.exit('template has no </body>')
    return text[:i] + snippet + '\n' + text[i:]


def read_meta(dump, ident):
    tag = re.search(r'<meta\b[^>]*\bid="%s"[^>]*>' % ident, dump)
    c = re.search(r'\bcontent="([^"]*)"', tag.group(0)) if tag else None
    return json.loads(base64.b64decode(c.group(1))) if c else None


# ---- Chrome -----------------------------------------------------------------------------------
def find_chrome():
    cands = [os.environ.get('CHROME')]
    for var in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
        base = os.environ.get(var)
        if base:
            cands += [Path(base) / 'Google/Chrome/Application/chrome.exe', Path(base) / 'Microsoft/Edge/Application/msedge.exe']
    for name in ('google-chrome', 'chrome', 'chromium', 'chromium-browser', 'microsoft-edge'):
        cands.append(shutil.which(name))
    cands.append('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    for c in cands:
        if c and Path(c).exists():
            return str(c)
    sys.exit('Chrome or Edge not found. Install one, or set the CHROME environment variable to its path.')


CHROME = None


def run_chrome(url, *flags, timeout=240):
    global CHROME
    CHROME = CHROME or find_chrome()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        cmd = [CHROME, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-extensions',
               '--hide-scrollbars', '--force-device-scale-factor=1', f'--user-data-dir={profile}', *flags, url]
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return p.stdout.decode('utf-8', 'replace')


def lang_flags(lang):
    return [f'--lang={lang}', f'--accept-lang={lang}']


# ---- fonts ------------------------------------------------------------------------------------
FACE_RE = re.compile(r'(?:/\*\s*([\w-]+)\s*\*/\s*)?@font-face\s*\{([^}]*)\}')


def parse_faces(css):
    faces = []
    for m in FACE_RE.finditer(css):
        body = m.group(2)
        data = re.search(r'url\(\s*["\']?data:font/woff2;base64,([^"\')]+)["\']?\s*\)', body)
        if not data:
            continue

        def get(prop):
            g = re.search(prop + r'\s*:\s*([^;]+);', body)
            return g.group(1).strip() if g else None

        faces.append({'subset': m.group(1), 'family': get('font-family').strip('\'"'), 'range': get('unicode-range'),
                      'body': body, 'buf': base64.b64decode(data.group(1))})
    return faces


def parse_ranges(s):
    out = []
    for part in s.split(','):
        part = re.sub(r'^U\+', '', part.strip(), flags=re.I)
        a, _, b = part.partition('-')
        out.append((int(a, 16), int(b or a, 16)))
    return out


def in_ranges(ranges, cp):
    return any(a <= cp <= b for a, b in ranges)


def families_used(*texts):
    out = set()
    for t in texts:
        for m in re.finditer(r'font-family\s*:\s*([^;}"]+)', t.replace('&quot;', "'")):
            for n in m.group(1).split(','):
                out.add(n.strip().strip('\'"'))
    return out


# ======================================================================================
# BUILD
# ======================================================================================
def build_page(name, cfg, tmp):
    langs = list(cfg['langs'])
    default = cfg['default_lang']
    print(f"\n[{name}] {', '.join(langs)} (default {default})")
    template = cfg['template'].read_text(encoding='utf-8')

    # 1. Render each language in a real browser and extract the compiled DOM.
    res = {}
    for lang in langs:
        arg = {
            'switcher': {c: {'href': rel_dir(page_dir(cfg, lang), page_dir(cfg, c)), 'current': c == lang} for c in langs},
            'homeFrom': cfg['home_link_in_template'],
            'homeTo': rel_dir(page_dir(cfg, lang), ''),
            'store': {'url': cfg['store']['url'], 'href': store_href(cfg, lang), 'label': cfg['langs'][lang]['store_alt']},
        }
        page = inject_before_body_end(template, '<script>' + EXTRACT_JS.replace('__ARG__', json.dumps(arg)) + '</script>')
        f = tmp / f'extract-{name}-{lang}.html'
        f.write_text(page, encoding='utf-8')
        dump = run_chrome(f.as_uri(), *lang_flags(lang), '--virtual-time-budget=20000', '--dump-dom')
        data = read_meta(dump, '__extract')
        if data is None:
            sys.exit(f'{lang}: the template did not render (no extraction came back from Chrome)')
        if 'error' in data:
            sys.exit(f"{lang}: extraction failed in the page:\n{data['error']}")
        res[lang] = data
        if not data.get('retagged'):
            warn(f'{lang}: the heading swap did not apply (did the template structure change?)')
        h1 = re.sub(r'\s+', ' ', data['h1']).strip()
        print(f'  rendered {lang}: "{h1}"')
        if lang != default and h1 == re.sub(r'\s+', ' ', res[default]['h1']).strip():
            sys.exit(f'{lang} rendered the same h1 as {default}: the locale did not take effect')

    # 2. Fonts: keep only the families the page uses, and the subsets its text actually needs.
    base = res[default]
    faces = parse_faces(base['fontCss'])
    used = families_used(base['html'], '\n'.join(base['styles']))
    latin = next((f for f in faces if f['subset'] == 'latin'), None)
    latin_ranges = parse_ranges(latin['range']) if latin else []
    keep_subsets = {'latin'}
    codepoints = {ord(ch) for r in res.values() for ch in r['text']}
    for cp in sorted(codepoints):
        if cp < 0x20 or in_ranges(latin_ranges, cp):
            continue
        f = next((x for x in faces if x['range'] and in_ranges(parse_ranges(x['range']), cp)), None)
        if f and f['subset']:
            keep_subsets.add(f['subset'])
        else:
            warn(f'U+{cp:04X} is in no font subset')
    kept = [f for f in faces if f['family'] in used and f['subset'] in keep_subsets]
    assets = ROOT / cfg['out_dir'] / 'assets'
    shutil.rmtree(assets, ignore_errors=True)
    (assets / 'fonts').mkdir(parents=True)
    files = {}
    for f in kept:
        slug = re.sub(r'[^a-z0-9]+', '-', f['family'].lower())
        f['file'] = f"{slug}-{f['subset']}-{hashlib.sha256(f['buf']).hexdigest()[:8]}.woff2"
        if f['file'] not in files:
            files[f['file']] = len(f['buf'])
            (assets / 'fonts' / f['file']).write_bytes(f['buf'])
    print(f"  fonts: {len(kept)} @font-face rules -> {len(files)} files ({sum(files.values()) / 1024:.0f} KB); "
          f"subsets [{','.join(sorted(keep_subsets))}], families [{','.join(f for f in sorted(used) if any(x['family'] == f for x in faces))}]")

    def font_css(prefix):
        rules = []
        for f in kept:
            css = re.sub(r'src\s*:\s*url\([^)]*\)\s*(?:format\([^)]*\))?\s*;',
                         lambda _m, f=f: f'src:url("{prefix}assets/fonts/{f["file"]}") format("woff2");', f['body'], count=1)
            rules.append('@font-face{' + re.sub(r'\s+', ' ', css).strip() + '}')
        return '\n'.join(rules)

    preloads = sorted({f['file'] for f in kept if f['subset'] == 'latin' and f['family'] in cfg['preload_families']},
                      key=lambda n: [x['file'] for x in kept].index(n))

    # 3. Write one page per language.
    favicon = svg_data_uri(cfg['favicon_svg'])
    for lang in langs:
        l = cfg['langs'][lang]
        r = res[lang]
        url = url_of(cfg, lang)
        prefix = rel_dir(page_dir(cfg, lang), cfg['out_dir'])
        prefix = '' if prefix == './' else prefix
        if len(l['title']) > 62:
            warn(f"{lang} title is {len(l['title'])} chars (>62)")
        if len(l['description']) > 160:
            warn(f"{lang} description is {len(l['description'])} chars (>160)")

        body = r['html']
        for img in r['images']:
            raw = base64.b64decode(img['b64'])
            data = svg_data_uri(raw.decode('utf-8')) if img['mime'] == 'image/svg+xml' else f"data:{img['mime']};base64,{img['b64']}"
            body = body.replace(f'src="{img["src"]}"', f'src="{data}"')

        og = cfg['og_image'](lang) if cfg.get('og_image') else None
        ld = cfg['json_ld'](lang, url) if cfg.get('json_ld') else None
        head = [
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{esc_text(l['title'])}</title>",
            f"<meta name=\"description\" content=\"{esc_attr(l['description'])}\">",
            f'<link rel="canonical" href="{url}">',
            *[f'<link rel="alternate" hreflang="{c}" href="{url_of(cfg, c)}">' for c in langs],
            f'<link rel="alternate" hreflang="x-default" href="{url_of(cfg, default)}">',
            '<meta name="robots" content="index, follow, max-image-preview:large">',
            f"<meta name=\"theme-color\" content=\"{cfg['theme_color']}\">" if cfg.get('theme_color') else '',
            f'<link rel="icon" type="image/svg+xml" href="{favicon}">',
            '<meta property="og:type" content="website">',
            f"<meta property=\"og:site_name\" content=\"{esc_attr(cfg['site_name'])}\">",
            f"<meta property=\"og:title\" content=\"{esc_attr(l['title'])}\">",
            f"<meta property=\"og:description\" content=\"{esc_attr(l['description'])}\">",
            f'<meta property="og:url" content="{url}">',
            f"<meta property=\"og:locale\" content=\"{l['og_locale']}\">",
            *[f"<meta property=\"og:locale:alternate\" content=\"{cfg['langs'][c]['og_locale']}\">" for c in langs if c != lang],
            f"<meta property=\"og:image\" content=\"{og['url']}\">" if og else '',
            f"<meta property=\"og:image:alt\" content=\"{esc_attr(og['alt'])}\">" if og else '',
            f"<meta name=\"twitter:card\" content=\"{'summary_large_image' if og else 'summary'}\">",
            f"<meta name=\"twitter:title\" content=\"{esc_attr(l['title'])}\">",
            f"<meta name=\"twitter:description\" content=\"{esc_attr(l['description'])}\">",
            f"<meta name=\"twitter:image\" content=\"{og['url']}\">" if og else '',
            *[f'<link rel="preload" href="{prefix}assets/fonts/{fn}" as="font" type="font/woff2" crossorigin>' for fn in preloads],
            f'<style>\n{font_css(prefix)}\n</style>',
            '<style>\n' + '\n'.join(r['styles'] + r['cssom']) + '\n</style>',
            ('<script type="application/ld+json">' + json.dumps(ld, separators=(',', ':'), ensure_ascii=False).replace('<', '\\u003c') + '</script>') if ld else '',
        ]
        out_html = (f'<!DOCTYPE html>\n<html lang="{lang}">\n<head>\n' + '\n'.join(h for h in head if h) +
                    f'\n</head>\n<body>\n{body}\n<script>\n{cfg["inline_script"]}\n</script>\n</body>\n</html>\n')

        for bad in (r'blob:', r'data-dc-', r'__resources', r'<script[^>]+src=', r'x-dc', r'\{\{'):
            if re.search(bad, out_html):
                sys.exit(f'{lang}: build output still contains /{bad}/')

        out = ROOT / page_dir(cfg, lang) / 'index.html'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(out_html, encoding='utf-8', newline='\n')
        enc = out_html.encode('utf-8')
        print(f"  wrote {out.relative_to(ROOT)}  {len(enc) / 1024:.0f} KB ({len(gzip.compress(enc, 9)) / 1024:.0f} KB gzipped)")


# ======================================================================================
# VERIFY
# ======================================================================================
def config_excludes():
    cfg = ROOT / '_config.yml'
    if not cfg.exists():
        return []
    out, on = [], False
    for line in cfg.read_text(encoding='utf-8').splitlines():
        if re.match(r'^exclude\s*:', line):
            on = True
        elif on and (m := re.match(r'^\s+-\s+(.+?)\s*$', line)):
            out.append(m.group(1))
        elif on and line.strip() and not line.lstrip().startswith('#'):
            on = False
    return out


EXCLUDES = config_excludes()


def is_published(p):
    """Model of what GitHub Pages' Jekyll build publishes: every file except paths with a segment
    starting with "_" or ".", node_modules, and the entries under `exclude:` in _config.yml.
    (Jekyll itself can't run here; the first deploy should confirm it, see _factory/README.md.)"""
    try:
        parts = p.resolve().relative_to(ROOT).parts
    except ValueError:
        return False
    if parts[0] == 'node_modules' or any(x.startswith(('_', '.')) for x in parts):
        return False
    return parts[0] not in EXCLUDES and '/'.join(parts) not in EXCLUDES


def repo_files():
    return [p for p in ROOT.rglob('*') if p.is_file() and '.git' not in p.relative_to(ROOT).parts and 'node_modules' not in p.relative_to(ROOT).parts]


class Scan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = None
        self.title = ''
        self.metas, self.links, self.scripts, self.imgs, self.anchors, self.ld, self.text = [], [], [], [], [], [], []
        self.headings = []
        self.h1 = self.buttons = self.skip = 0
        self._title = self._ld = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'html':
            self.lang = a.get('lang')
        elif tag == 'title':
            self._title = True
        elif tag == 'meta':
            self.metas.append(a)
        elif tag == 'link':
            self.links.append(a)
        elif tag in ('script', 'style'):
            self.skip += 1
            if tag == 'script':
                self.scripts.append(a)
                self._ld = a.get('type') == 'application/ld+json'
        elif tag == 'img':
            self.imgs.append(a)
        elif re.fullmatch(r'h[1-6]', tag):
            self.headings.append(int(tag[1]))
            self.h1 += tag == 'h1'
        elif tag == 'a':
            self.anchors.append(a)
        elif tag == 'button':
            self.buttons += 1

    def handle_endtag(self, tag):
        if tag == 'title':
            self._title = False
        elif tag in ('script', 'style'):
            self.skip -= 1
            self._ld = False

    def handle_data(self, d):
        if self._title:
            self.title += d
        elif self._ld:
            self.ld.append(d)
        elif not self.skip:
            self.text.append(d)


def word_count(s):
    return len(s.split())


def make_server(templates, port=0):
    """Serves exactly what would be published (plus the templates under /__template/, and a
    /__frame harness that shows a page inside an iframe of a given width for mobile checks)."""
    class H(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            path = unquote(u.path)
            body, ctype = None, 'text/html; charset=utf-8'
            if path.startswith('/__template/'):
                t = templates.get(path.split('/')[2].removesuffix('.html'))
                if t:
                    body = inject_before_body_end(t, '<script>' + FREEZE_JS.replace('__FREEZE__', FREEZE) + '</script>').encode()
            elif path == '/__frame':
                w, h, src = int(q['w'][0]), int(q['h'][0]), q['src'][0]
                body = (f'<!doctype html><body style="margin:0;background:#fff"><iframe src="{htmllib.escape(src)}" '
                        f'style="border:0;display:block;width:{w}px;height:{h}px"></iframe>').encode()
            else:
                f = ROOT / path.lstrip('/')
                f = f / 'index.html' if f.is_dir() else f
                if f.is_file() and is_published(f):
                    body, ctype = f.read_bytes(), MIME.get(f.suffix, 'application/octet-stream')
                    if 'nojs' in q and f.suffix == '.html':  # no <script> at all == JavaScript off; animations frozen
                        body = re.sub(rb'<script\b[^>]*>.*?</script>', b'', body, flags=re.S)
                        body = body.replace(b'</head>', f'<style>{FREEZE}</style></head>'.encode(), 1)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('content-type', ctype)
            self.send_header('content-length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer(('127.0.0.1', port), H)


def start_server(templates):
    srv = make_server(templates)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def pixel_diff(a_png, b_png, tmp):
    enc = lambda p: base64.b64encode(Path(p).read_bytes()).decode()
    harness = tmp / 'diff.html'
    harness.write_text(f'<!doctype html><meta charset="utf-8"><body><img id="a" src="data:image/png;base64,{enc(a_png)}">'
                       f'<img id="b" src="data:image/png;base64,{enc(b_png)}"><script>{DIFF_JS}</script>', encoding='utf-8')
    out = read_meta(run_chrome(harness.as_uri(), '--virtual-time-budget=15000', '--dump-dom'), '__diff')
    if out is None:
        sys.exit('pixel diff harness returned nothing')
    return out


def verify_page(name, cfg, srv, tmp, check):
    langs = list(cfg['langs'])
    default = cfg['default_lang']
    base = f'http://127.0.0.1:{srv.server_address[1]}'
    print(f'\n[{name}]')
    shots = {}
    for lang in langs:
        l = cfg['langs'][lang]
        pdir = page_dir(cfg, lang)
        raw = (ROOT / pdir / 'index.html').read_text(encoding='utf-8')
        s = Scan()
        s.feed(raw)
        print(f' {lang}  /{pdir}/')
        meta = lambda key, val: next((m.get('content') for m in s.metas if m.get(key) == val), None)
        canon = next((k.get('href') for k in s.links if k.get('rel') == 'canonical'), None)
        alts = [(k.get('hreflang'), k.get('href')) for k in s.links if k.get('rel') == 'alternate' and k.get('hreflang')]
        icon = next((k.get('href') for k in s.links if k.get('rel') == 'icon'), '') or ''
        check(s.lang == lang, '<html lang>', s.lang)
        check(s.title == l['title'], 'title', f'{len(s.title)} chars')
        check(meta('name', 'description') == l['description'], 'meta description', f"{len(meta('name', 'description') or '')} chars")
        check(canon == url_of(cfg, lang), 'canonical is self-referencing', canon)
        check(alts == [(c, url_of(cfg, c)) for c in langs] + [('x-default', url_of(cfg, default))], 'hreflang set (all languages + x-default)')
        check(meta('property', 'og:locale') == l['og_locale'] and meta('property', 'og:url') == url_of(cfg, lang), 'Open Graph locale + url')
        check(s.h1 == 1, 'exactly one h1')
        hs = s.headings
        check(bool(hs) and hs[0] == 1 and all(b <= a + 1 for a, b in zip(hs, hs[1:])), 'heading levels never skip', ''.join(map(str, hs)))
        store_url = cfg['store']['url']
        store_links = [a for a in s.anchors if (a.get('href') or '').startswith(store_url)]
        check(bool(store_links) and all(a['href'] == store_href(cfg, lang) for a in store_links), f'Store links carry hl/cid ({len(store_links)})', store_href(cfg, lang))
        check(all(a.get('aria-label') == l['store_alt'] for a in store_links) and all(i.get('alt') == l['store_alt'] for i in s.imgs),
              'badge alt + link label name the game', l['store_alt'])
        check(len(l['title']) <= 62 and len(l['description']) <= 160, 'title <= 62 and description <= 160 chars', f"{len(l['title'])}/{len(l['description'])}")
        check(all('src' not in x for x in s.scripts), 'no external scripts', 'inline: ' + ', '.join(sorted(x.get('type') or 'js' for x in s.scripts)))
        check(all((i.get('alt') or '').strip() for i in s.imgs), 'every <img> has alt')
        check(icon.startswith('data:image/svg+xml'), 'inline SVG favicon')
        sw = [a for a in s.anchors if a.get('hreflang') and a.get('lang')]
        cur = [a.get('hreflang') for a in sw if a.get('aria-current') == 'page']
        check(s.buttons == 0 and len(sw) == len(langs) and cur == [lang], 'language switcher = links, current marked')
        try:
            j = json.loads(''.join(s.ld))
            ld_ok = j.get('inLanguage') == lang and j.get('url') == url_of(cfg, lang)
        except Exception:
            ld_ok = False
        check(ld_ok, 'JSON-LD parses, matches language + url')

        def resolves(href):
            p = urlparse(urljoin(f'http://x/{pdir}/', href)).path
            f = ROOT / unquote(p).lstrip('/')
            f = f / 'index.html' if f.is_dir() else f
            return f.is_file() and is_published(f)

        internal = [a['href'] for a in s.anchors if a.get('href') and not re.match(r'^(https?:|ms-|mailto:|#)', a['href'])]
        assets = re.findall(r'url\("([^"]+\.woff2)"\)', raw) + [k['href'] for k in s.links if k.get('rel') == 'preload' and k.get('href')]
        bad = [h for h in internal + assets if not resolves(h)]
        check(not bad, f'internal links and font files resolve ({len(internal)} links, {len(set(assets))} fonts)', ' '.join(bad))
        check(not re.search(r'Unpacking|requires JavaScript', raw), 'raw HTML has real content (no loader)', f'{word_count(" ".join(s.text))} words in raw HTML')

        # Pixel parity: static page with JavaScript OFF vs the template with JavaScript ON.
        for vp, (w, h) in (('desktop', (1280, 3200)), ('mobile', (390, 5600))):
            shot = {}
            for kind in ('template', 'static'):
                target = f'{base}/__template/{name}.html' if kind == 'template' else f'{base}/{pdir}/?nojs=1'
                if vp == 'mobile':  # iframe width = viewport width, so the page's media queries see 390px
                    target = f'{base}/__frame?w={w}&h={h}&src=' + target.replace('?', '%3F').replace('=', '%3D').replace('&', '%26')
                    win = (w + 410, h)
                else:
                    win = (w, h)
                png = tmp / f'{name}-{lang}-{vp}-{kind}.png'
                png.unlink(missing_ok=True)
                run_chrome(target, *lang_flags(lang), f'--window-size={win[0]},{win[1]}', '--virtual-time-budget=15000', f'--screenshot={png}')
                if not png.exists():
                    sys.exit(f'Chrome produced no screenshot for {target}')
                shot[kind] = png
            shots[(lang, vp)] = shot
            d = pixel_diff(shot['template'], shot['static'], tmp)
            if 'sizes' in d:
                check(False, f'pixel parity {vp}', f'screenshot sizes differ {d["sizes"]}')
            else:
                check(d['ratio'] <= MAX_DIFF, f'pixel parity {vp} ({w}px wide, scripts stripped)', f'{d["ratio"] * 100:.3f}% differ')
        # Template word count (from the template's own rendered text) vs the static page's words.
        arg = {'switcher': {c: {'href': '', 'current': False} for c in langs}, 'homeFrom': '', 'homeTo': ''}
        page = inject_before_body_end(cfg['template'].read_text(encoding='utf-8'), '<script>' + EXTRACT_JS.replace('__ARG__', json.dumps(arg)) + '</script>')
        f = tmp / f'words-{name}-{lang}.html'
        f.write_text(page, encoding='utf-8')
        data = read_meta(run_chrome(f.as_uri(), *lang_flags(lang), '--virtual-time-budget=20000', '--dump-dom'), '__extract')
        wa, wb = data['words'], word_count(' '.join(s.text))
        check(abs(wa - wb) / wa < 0.05, 'visible word count matches template', f'{wa} template / {wb} static')

    # Negative control: the pixel diff must be able to see a real difference.
    if len(langs) > 1 and (langs[0], 'desktop') in shots:
        a, b = langs[0], langs[1]
        d = pixel_diff(shots[(a, 'desktop')]['template'], shots[(b, 'desktop')]['static'], tmp)
        check('ratio' in d and d['ratio'] > 0.01, f'self-test: {a} template vs {b} static is flagged', f"{d.get('ratio', 0) * 100:.1f}% differ" if 'ratio' in d else 'sizes differ')


def verify_publishing(check):
    print('\n[publishing]')
    check(not (ROOT / '.nojekyll').exists(), 'no .nojekyll (it would switch Jekyll off and publish everything)')
    check('_factory' in EXCLUDES, '_config.yml excludes _factory')
    published = [p for p in repo_files() if is_published(p)]
    leaks = [p for p in published
             if p.suffix in ('.py', '.pyc', '.mjs', '.cjs', '.ts', '.md', '.yml', '.yaml') or p.name in ('package.json', 'package-lock.json')
             or 'template' in p.name or (p.suffix == '.html' and '__bundler/' in p.read_text(encoding='utf-8', errors='ignore'))]
    check(not leaks, f'no factory or tooling file would be published ({len(published)} files go out)', ' '.join(str(p.relative_to(ROOT)) for p in leaks))
    print('  published: ' + ', '.join(str(p.relative_to(ROOT)).replace('\\', '/') for p in sorted(published)))


# ======================================================================================
def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd not in ('build', 'verify', 'serve'):
        sys.exit(__doc__)
    if cmd == 'serve':  # a local preview of exactly what GitHub Pages would publish (_factory/ is a 404)
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
        srv = make_server({}, port)
        print(f'Serving what GitHub Pages would publish: http://127.0.0.1:{port}/   (Ctrl+C to stop)', flush=True)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        return
    names = [sys.argv[2]] if len(sys.argv) > 2 else list(PAGES)
    for n in names:
        if n not in PAGES:
            sys.exit(f'unknown page "{n}" (known: {", ".join(PAGES)})')
    tmp = Path(tempfile.mkdtemp(prefix='factory-'))
    failures = []
    try:
        if cmd == 'build':
            for n in names:
                build_page(n, PAGES[n], tmp)
        else:
            def check(ok, label, detail=''):
                print(f"  {'ok  ' if ok else 'FAIL'} {label}{'  ' + str(detail) if detail else ''}")
                if not ok:
                    failures.append(label)
            verify_publishing(check)
            srv = start_server({n: PAGES[n]['template'].read_text(encoding='utf-8') for n in PAGES})
            try:
                for n in names:
                    verify_page(n, PAGES[n], srv, tmp, check)
            finally:
                srv.shutdown()
            print(f'\n{len(failures)} check(s) FAILED:\n - ' + '\n - '.join(failures) if failures else '\nAll checks passed.')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
