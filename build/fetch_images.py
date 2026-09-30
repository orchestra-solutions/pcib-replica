#!/usr/bin/env python3
"""Download images listed in images.tsv (src<TAB>timestamp) from the Wayback Machine, politely.

Usage: fetch_images.py <images.tsv>. Serial, ~13 req/min (the archive blocks >15/min), long backoff when the archive refuses connections.
"""
import os, sys, time, urllib.request
sys.argv, tsv = sys.argv[:1] + ['.'], sys.argv[1]
from build import img_name, OUT

dest_dir = os.path.join(OUT, 'assets', 'img'); os.makedirs(dest_dir, exist_ok=True)
rows = [l.rstrip('\n').split('\t') for l in open(tsv)]
ok = fail = 0
for n, (src, ts) in enumerate(rows, 1):
    orig, name = img_name(src)
    dest = os.path.join(dest_dir, name)
    if os.path.exists(dest): ok += 1; continue
    for cand in dict.fromkeys([orig, src]):
        got = False
        for attempt in range(4):
            try:
                d = urllib.request.urlopen(f'https://web.archive.org/web/{ts}im_/{cand}', timeout=45).read()
                if len(d) > 100 and not d.lstrip()[:15].lower().startswith((b'<!doctype', b'<html')):
                    open(dest + '.part', 'wb').write(d); os.replace(dest + '.part', dest); got = True
                break
            except urllib.error.HTTPError:
                break                                   # 404 etc: try next candidate
            except Exception as e:
                print(f'  backoff {300 * (attempt + 1)}s: {e}', flush=True); time.sleep(300 * (attempt + 1))
        time.sleep(4.5)
        if got: break
    ok, fail = (ok + 1, fail) if got else (ok, fail + 1)
    if n % 25 == 0 or n == len(rows): print(f'{n}/{len(rows)} ok={ok} fail={fail}', flush=True)
