#!/usr/bin/env python3
"""Compile docs/design-system/tokens.json into tokens.css (CSS custom properties + type classes).

Usage: python scripts/gen_tokens_css.py [docs/design-system]
The first theme is the default (:root); every later theme is a [data-theme="<id>"] block.
"""
import json
import re
import sys
from pathlib import Path

base = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "docs" / "design-system")
t = json.loads((base / "tokens.json").read_text(encoding="utf-8"))


def val(v):
    m = re.fullmatch(r"\{(.+)\}", str(v))
    return f"var(--{m.group(1)})" if m else v


themes = [th["id"] for th in t["color"]["themes"]]
first = themes[0]
out = [f"/* {t.get('name', 'Design system')} — generated from tokens.json by scripts/gen_tokens_css.py; do not edit by hand */"]
lines = []
for tok in t["color"]["tokens"]:
    v = tok["value"]
    lines.append(f"  --{tok['name']}: {val(v if isinstance(v, str) else v.get(first))};")
out.append(f':root, [data-theme="{first}"] {{\n  color-scheme: {"dark" if first == "dark" else "light"};\n' + "\n".join(lines) + "\n}")
for th in themes[1:]:
    lines = [f"  --{tok['name']}: {val(tok['value'][th])};" for tok in t["color"]["tokens"]
             if isinstance(tok["value"], dict) and th in tok["value"]]
    out.append(f'[data-theme="{th}"] {{\n  color-scheme: {"dark" if th == "dark" else "light"};\n' + "\n".join(lines) + "\n}")
lines = []
for fam in [k for k in t if k not in ("name", "version", "color", "type", "meta") and isinstance(t[k], dict) and "tokens" in t[k]]:
    lines += [f"  --{tok['name']}: {tok['value']};" for tok in t[fam]["tokens"]]
lines += [f"  --font-{k}: {v};" for k, v in t["type"]["families"].items()]
out.append(":root {\n" + "\n".join(lines) + "\n}")
for g in t["type"]["groups"]:
    for s in g["styles"]:
        fam = s.get("family") or g.get("family")
        props = [f"font-family: var(--font-{fam})", f"font-size: {s['fontSize']}", f"line-height: {s['lineHeight']}",
                 f"font-weight: {s['fontWeight']}"] + ([f"letter-spacing: {s['letterSpacing']}"] if s.get("letterSpacing") else [])
        out.append(f".{s['name']} {{ " + "; ".join(props) + "; }")
(base / "tokens.css").write_text("\n".join(out) + "\n", encoding="utf-8")
print("wrote", base / "tokens.css")
