#!/usr/bin/env python3
"""Assemble the public website into _site/ -- the ONLY directory GitHub Pages serves.

Pages used to serve the repository root, so everything committed was public: the signed
.ipa and Xcode archive (development profiles list device UDIDs), release scripts, the
App Store Connect key identifiers, raw data dumps. Now the site is an allow-list.

Adding a public file? Add it to FILES or DIRS below. The reference check at the end fails
the deploy if any public page, the manifest or the service worker points at something that
did not make it into _site/, so a missing entry breaks the build, not the live site.

    python3 publish.py            # build _site/ and check it
"""
import json
import os
import re
import shutil
import sys
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_site")

FILES = ["index.html", "404.html", "data.js", "sw.js", "manifest.json", "robots.txt",
         "sitemap.xml", "favicon.ico", "favicon.svg", "apple-touch-icon.png",
         "icon-192.png", "icon-512.png", "icon-maskable-512.png", "og.png", "CNAME"]
DIRS = ["near", "along", "trip", "privacy", "support", "admin", "og", "vendor", "assets"]
SITE_HOST = "chargeandchew.com"


def build():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    for f in FILES:
        shutil.copy2(os.path.join(HERE, f), os.path.join(OUT, f))
    for d in DIRS:
        shutil.copytree(os.path.join(HERE, d), os.path.join(OUT, d),
                        ignore=shutil.ignore_patterns(".DS_Store", "*.py", "__pycache__"))


def resolve(page_rel, ref):
    """Map a reference found in page_rel to a path inside _site, or None if not ours."""
    if not ref or ref.startswith(("#", "mailto:", "tel:", "data:", "javascript:", "blob:")):
        return None
    if "${" in ref or "{{" in ref or "'" in ref or "+" in ref:   # JS template, not a link
        return None
    u = urlparse(ref)
    if u.scheme in ("http", "https") or ref.startswith("//"):
        if u.netloc != SITE_HOST:
            return None
        path = u.path
    elif u.scheme:
        return None
    else:
        path = u.path
        if not path:
            return None
        if not path.startswith("/"):
            path = os.path.normpath(os.path.join("/" + os.path.dirname(page_rel), path))
    path = path.lstrip("/")
    if path == "" or path.endswith("/"):
        path += "index.html"
    elif "." not in os.path.basename(path):
        path += "/index.html"
    return path


def check():
    missing = {}
    REF = re.compile(r'(?:href|src)="([^"]+)"|content="(https?://[^"]+)"')
    for root, _, files in os.walk(OUT):
        for f in files:
            if not f.endswith(".html"):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, OUT)
            html = open(full, encoding="utf-8", errors="replace").read()
            for m in REF.finditer(html):
                p = resolve(rel, m.group(1) or m.group(2))
                if p and not os.path.isfile(os.path.join(OUT, p)):
                    missing.setdefault(p, rel)
    # The manifest's icons and the service worker's precache list are references too.
    man = json.load(open(os.path.join(OUT, "manifest.json")))
    for ic in man.get("icons", []):
        p = resolve("manifest.json", ic["src"])
        if p and not os.path.isfile(os.path.join(OUT, p)):
            missing.setdefault(p, "manifest.json")
    sw = open(os.path.join(OUT, "sw.js")).read()
    for ref in re.findall(r"'(/[A-Za-z0-9_./-]+\.[a-z]+)'", sw):
        p = resolve("sw.js", ref)
        if p and not os.path.isfile(os.path.join(OUT, p)):
            missing.setdefault(p, "sw.js")
    # Every URL we tell search engines about must exist.
    sm = open(os.path.join(OUT, "sitemap.xml")).read()
    locs = re.findall(r"<loc>([^<]+)</loc>", sm)
    for loc in locs:
        p = resolve("sitemap.xml", loc)
        if p and not os.path.isfile(os.path.join(OUT, p)):
            missing.setdefault(p, "sitemap.xml")
    return missing, len(locs)


def main():
    build()
    missing, nloc = check()
    leaked = [p for p in ("ios", "tools", "data", "refresh.sh", "README.md", "build.py", ".git")
              if os.path.exists(os.path.join(OUT, p))]
    n = sum(len(fs) for _, _, fs in os.walk(OUT))
    if leaked:
        print("FAIL: non-public paths in _site:", leaked)
        return 1
    if missing:
        print(f"FAIL: {len(missing)} referenced file(s) missing from _site (add them to FILES/DIRS):")
        for p, src in sorted(missing.items())[:30]:
            print(f"  /{p}   (referenced by {src})")
        return 1
    print(f"_site: {n} files, {nloc} sitemap URLs, every reference resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main())
