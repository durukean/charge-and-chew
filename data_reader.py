"""Single place that knows how data.js is encoded.

data.js wraps the payload in JSON.parse('…') rather than a bare object literal: V8 parses
JSON.parse roughly 1.5-2x faster than equivalent object-literal source, measured cold with
a real script tag (80/67 ms -> 53/35 ms), for +1 KB gzipped. The JSON is wrapped in a
SINGLE-quoted JS string so its own double quotes need no escaping; only backslash, apostrophe
and the two JS line separators are escaped, all of which are also valid Python escapes, so
ast.literal_eval decodes the literal exactly.

The older bare-object-literal form is still read, so an old data.js does not break tooling.
"""
import ast, json

def load_data(path, prefix="window.PITSTOP_DATA"):
    """data.js by default; level2.js is the same encoding under window.PITSTOP_L2."""
    raw = open(path, encoding="utf-8").read()
    if not raw.startswith(prefix):
        raise ValueError("data.js has the wrong shape")
    marker = "JSON.parse("
    if marker in raw:
        start = raw.index(marker) + len(marker)
        end = raw.rindex(")")
        return _names(json.loads(ast.literal_eval(raw[start:end].strip())))
    return _names(json.loads(raw[raw.index("{"): raw.rindex("}") + 1]))


def _names(D):
    """A site's "xh" (places across a highway from the charger) is stored as positions in that
    site's own matches; every reader gets the chain names, as the app does at boot."""
    M = D.get("matches") or {}
    for s in D.get("sites", []):
        if s.get("xh") and all(isinstance(i, int) for i in s["xh"]):
            order = list(M.get(str(s["id"]), {}))
            s["xh"] = [order[i] for i in s["xh"] if i < len(order)]
    return D
