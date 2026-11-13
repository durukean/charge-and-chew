Self-hosted web fonts (so no page waits on a third-party font host, and the app and offline
copies have them). Latin subset (U+0000-00FF and common punctuation), WOFF2, variable, as
served by Google Fonts on 2026-11-12:

  inter-latin.woff2                 Inter v20, wght 400-800             OFL-Inter.txt
  bricolage-grotesque-latin.woff2   Bricolage Grotesque v9, opsz 12-96, wght 600-800
                                                                        OFL-BricolageGrotesque.txt
  jetbrains-mono-latin.woff2        JetBrains Mono v24, wght 600-700    OFL-JetBrainsMono.txt

All three are licensed under the SIL Open Font License 1.1; each licence is kept beside the
fonts as the licence requires. The @font-face rules are in index.html and build.py (pages.css).
