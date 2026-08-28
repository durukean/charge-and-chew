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

def load_data(path):
    raw = open(path, encoding="utf-8").read()
    if not raw.startswith("window.PITSTOP_DATA"):
        raise ValueError("data.js has the wrong shape")
    marker = "JSON.parse("
    if marker in raw:
        start = raw.index(marker) + len(marker)
        end = raw.rindex(")")
        return json.loads(ast.literal_eval(raw[start:end].strip()))
    return json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
