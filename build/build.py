#!/usr/bin/env python3
"""Rebuild a plain static copy of pcibooking.net from Wayback Machine snapshots.

Input: raw/*.html (id_ snapshots) + pages.tsv. Output: ../site/
Keeps only semantic content from <main>, wrapped in shared chrome.
"""
import hashlib, html, os, re, sys, urllib.parse
from html.parser import HTMLParser

SRC = sys.argv[1]                    # dir holding raw/ and pages.tsv
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'site')
HOST = re.compile(r'^https?://(www\.)?pcibooking\.net(:80)?', re.I)
NITRO = re.compile(r'/nitropack_static/[^/]+/assets/(?:images|static)/(?:optimized|source)/rev-[^/]+/pcibooking\.net')
DROP = {'nav', 'aside', 'script', 'style', 'noscript', 'svg', 'form', 'iframe', 'button', 'select', 'textarea', 'template', 'video', 'object'}
KEEP = {'h1','h2','h3','h4','h5','h6','p','ul','ol','li','a','img','strong','b','em','i','br','blockquote',
        'table','thead','tbody','tr','td','th','figure','figcaption','hr','section'}
VOID = {'img', 'br', 'hr'}
# Pages that were live forms/app entry points; send visitors somewhere real instead.
REDIRECT = {'/sandbox/': '/contact-us/', '/login/': 'https://users.pcibooking.net/booker/Login',
            '/capture-form/': '/card-capture-and-display/', '/card-over-the-phone-demo/': '/card-over-the-phone/'}

pages = {}
for l in open(os.path.join(SRC, 'pages.tsv')):
    p, ts, u = l.rstrip('\n').split('\t')
    pages[p] = (ts, u)
built = {p for p in pages if os.path.exists(os.path.join(SRC, 'raw', (p.strip('/').replace('/', '__') or 'index') + '.html'))}

def local_link(href):
    href = html.unescape(href.strip())
    if href.startswith(('mailto:', 'tel:', '#')): return href
    h = HOST.sub('', href)
    if h == href and re.match(r'^[a-z]+:', href): return href      # external
    if not h.startswith('/'): h = '/' + h
    path, _, frag = h.partition('#')
    path = path.split('?')[0]
    if not path.endswith('/') and '.' not in path.rsplit('/', 1)[-1]: path += '/'
    path = path.lower()
    if path in REDIRECT: return REDIRECT[path]
    if path.startswith('/wp-content/'): return 'https://web.archive.org/web/2026/https://pcibooking.net' + path
    return path + ('#' + frag if frag else '')

def img_name(src):
    """Map an archived image URL to (original URL, local file name)."""
    src = html.unescape(src.strip())
    if src.startswith('data:') or not src: return None, None
    orig = NITRO.sub('', HOST.sub('', src)) if HOST.match(src) or src.startswith('/') else src
    if orig.startswith('/'): orig = 'https://pcibooking.net' + orig
    ext = os.path.splitext(urllib.parse.urlparse(orig).path)[1].lower()
    if ext not in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'): ext = '.png'
    return orig, hashlib.sha1(orig.encode()).hexdigest()[:12] + ext

def local_img(src, ts):
    # Offline: images are downloaded beforehand by fetch_images.py; missing ones are dropped.
    orig, name = img_name(src)
    if name and os.path.exists(os.path.join(OUT, 'assets', 'img', name)):
        return '/assets/img/' + name
    return None

class Clean(HTMLParser):
    def __init__(self, ts):
        super().__init__(convert_charrefs=False)
        self.ts, self.out, self.drop, self.stack = ts, [], 0, []
    def handle_starttag(self, tag, attrs):
        if self.drop:
            if tag in DROP: self.drop += 1
            return
        if tag in DROP: self.drop = 1; return
        if tag not in KEEP: return
        a = dict(attrs); keep = ''
        if tag == 'a':
            href = a.get('href')
            if not href: return
            href = local_link(href)
            if href.startswith('/') and not href.startswith('/assets/') and href.split('#')[0] not in built:
                return                      # page we don't have: keep the text, drop the link
            keep = f' href="{html.escape(href)}"'
        elif tag == 'img':
            src = a.get('nitro-lazy-src') or a.get('data-src') or a.get('src') or ''
            loc = local_img(src, self.ts)
            if not loc: return
            keep = f' src="{loc}" alt="{html.escape(a.get("alt") or "")}" loading="lazy"'
        elif tag in ('td', 'th') and a.get('colspan'):
            keep = f' colspan="{html.escape(a["colspan"])}"'
        self.out.append(f'<{tag}{keep}>')
        if tag not in VOID: self.stack.append(tag)
    def handle_endtag(self, tag):
        if self.drop:
            if tag in DROP: self.drop -= 1
            return
        if tag in KEEP and tag not in VOID and tag in self.stack:
            while self.stack:
                t = self.stack.pop(); self.out.append(f'</{t}>')
                if t == tag: break
    def handle_data(self, d):
        if not self.drop: self.out.append(d)
    def handle_entityref(self, n):
        if not self.drop: self.out.append(f'&{n};')
    def handle_charref(self, n):
        if not self.drop: self.out.append(f'&#{n};')
    def result(self):
        s = ''.join(self.out) + ''.join(f'</{t}>' for t in reversed(self.stack))
        s = re.sub(r'<(a|p|strong|b|em|i|li|h\d|section|figure|blockquote)>\s*</\1>', '', s)
        s = re.sub(r'<(a|p|strong|b|em|i|li|h\d|section|figure|blockquote)>\s*</\1>', '', s)
        s = re.sub(r'<section>\s*(?=<section>)', '', s)
        s = re.sub(r'^\s*(<section>)?\s*<a href="/">\s*<img[^>]*>\s*</a>', r'\1', s)   # logo from embedded header
        s = re.sub(r'<a href="([^"]+)">\s*([A-Z][A-Z0-9 &!\'?-]{3,}?)\s*</a>', r'<a class="btn" href="\1">\2</a>', s)  # CTA buttons
        return re.sub(r'\n\s*\n+', '\n', s)

def extract(raw, ts):
    t = re.search(r'<title[^>]*>(.*?)</title>', raw, re.S)
    d = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', raw)
    # Blog posts sit in <main>; full-width Elementor pages have no <main>, so start at the page's own post div.
    i = raw.find('<main')
    if i < 0:
        m = re.search(r'<div data-elementor-type="wp-(?:post|page)"[^>]*data-elementor-post-type="(?:page|post)"', raw)
        i = m.start() if m else 0
    # Stop at whichever site-wide footer block comes first.
    ends = [k for k in (raw.find('<footer id="footer"', i), raw.find('data-elementor-type="footer"', i),
                        raw.find('data-elementor-post-type="oceanwp_library"', i), raw.find('data-elementor-id="1147"', i)) if k > 0]
    j = raw.rfind('<', 0, min(ends)) if ends else len(raw)
    body = re.sub(r'<header data-elementor-type="header".*?</header>', '', raw[i:j], flags=re.S)
    c = Clean(ts); c.feed(body); c.close()
    content = c.result()
    if re.search(r'<form[^>]*wpcf7', body):  # contact forms can't run on a static host
        content += CONTACT_BOX
    return (t.group(1).strip() if t else 'PCI Booking'), (d.group(1) if d else ''), content

CONTACT_BOX = ('<section class="contact-box"><h2>Get in touch</h2><p>Our online forms are temporarily unavailable. '
               'Please email us directly:</p><ul><li>Sales: <a href="mailto:sales@pcibooking.net">sales@pcibooking.net</a></li>'
               '<li>Support: <a href="mailto:support@pcibooking.net">support@pcibooking.net</a></li>'
               '<li>Billing: <a href="mailto:billing@pcibooking.net">billing@pcibooking.net</a></li></ul></section>')

NAV = [('Solutions', [('PCI Shield', '/pci-shield/'), ('Payments Library', '/payments-library/'),
         ('Universal Payment Gateway', '/universal-payment-gateway/'),
         ('Tokenization &amp; Detokenization', '/tokenization-detokenization/'),
         ('Card Capture and Display Forms', '/card-capture-and-display/'), ('Proxy', '/proxy/'),
         ('Card By Link', '/card-by-link/'), ('Storage and Management', '/storage-and-management/'),
         ('Credit Card Risk Assessment', '/credit-card-risk-assessment/'),
         ('3D Secure', '/3d-secure-credit-card-authentication/'), ('Data Tokenization', '/data-tokenization/')]),
       ('Orchestra', [('Orchestra', 'https://orchestrasolutions.com/'),
         ('Payments Methods', 'https://orchestrasolutions.com/solutions/payment-methods/'),
         ('Orchestra Connect', 'https://orchestrasolutions.com/solutions/orchestra-connect/')]),
       ('Developers', [('PCI Shield', 'https://developers.pcibooking.net/'),
         ('Orchestra', 'https://developers.orchestrasolutions.com/')]),
       ('Blog', '/blog/'), ('Contact Us', '/contact-us/')]

def nav_html():
    out = []
    for label, target in NAV:
        if isinstance(target, str):
            out.append(f'<li><a href="{target}">{label}</a></li>')
        else:
            items = ''.join(f'<li><a href="{h}">{l}</a></li>' for l, h in target)
            out.append(f'<li class="has-sub"><details><summary>{label}</summary><ul>{items}</ul></details></li>')
    return ''.join(out)

TEMPLATE = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template.html')).read()

def main():
    os.makedirs(os.path.join(OUT, 'assets', 'img'), exist_ok=True)
    nav = nav_html()
    for i, p in enumerate(sorted(built), 1):
        print(i, *build_page(p, nav), flush=True)
    build_page('/blog/', nav, extra=all_articles())
    write_redirects()
    open(os.path.join(OUT, '404.html'), 'w').write(
        TEMPLATE.replace('{{title}}', 'Page not found | PCI Booking').replace('{{description}}', '')
        .replace('{{canonical}}', 'https://pcibooking.net/').replace('{{nav}}', nav).replace('{{content}}',
        '<h1>Page not found</h1><p>This page is not available right now. Try the <a href="/">home page</a>, '
        'the <a href="/blog/">blog</a>, or <a href="/contact-us/">contact us</a>.</p>'))

def raw_page(p):
    return open(os.path.join(SRC, 'raw', (p.strip('/').replace('/', '__') or 'index') + '.html'), encoding='utf-8', errors='replace').read()

def all_articles():
    """The archived /blog/ only lists the newest posts; append a list of every post we rebuilt."""
    from datetime import datetime
    posts = []
    for p in built:
        raw = raw_page(p)
        if 'data-elementor-post-type="post"' not in raw: continue
        d = re.search(r'"datePublished":"([0-9-]{10})', raw)
        t = re.search(r'<h1[^>]*>(.*?)</h1>', raw, re.S)
        if t: posts.append((d.group(1) if d else '', re.sub('<[^>]+>', '', t.group(1)).strip(), p))
    posts.sort(reverse=True)
    items = ''.join(f'<li><a href="{p}">{t}</a>' + (f' <span class="date">{datetime.strptime(d, "%Y-%m-%d"):%B %-d, %Y}</span>' if d else '') + '</li>'
                    for d, t, p in posts)
    return f'<section class="all-articles"><h2>All articles</h2><ul>{items}</ul></section>'

def build_page(p, nav, extra=''):
        ts, _ = pages[p]
        title, desc, content = extract(raw_page(p), ts)
        content += extra
        page = (TEMPLATE.replace('{{title}}', title).replace('{{description}}', desc)
                .replace('{{canonical}}', 'https://pcibooking.net' + p).replace('{{nav}}', nav)
                .replace('{{content}}', content).replace('{{snapshot}}', ts[:4] + '-' + ts[4:6] + '-' + ts[6:8]))
        d = os.path.join(OUT, p.strip('/'))
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'index.html'), 'w').write(page)
        return p, len(content)

def write_redirects():
    for src, dst in REDIRECT.items():
        d = os.path.join(OUT, src.strip('/')); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'index.html'), 'w').write(
            f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url={dst}">'
            f'<link rel="canonical" href="{dst}"><a href="{dst}">Continue</a>')

if __name__ == '__main__':
    main()
