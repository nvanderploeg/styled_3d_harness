"""Art guides: the world → zone → set rules an asset shares with every other asset in its chain.
The format and merge rules are pipeline/ART.md; keep this module and that file in step."""
import importlib
import inspect
import json
import os
import re

import numpy as np

WORLD = "world_art.md"
LEVELS = ("zone_art.md", "set_art.md")
BLOCK = re.compile(r"^```json[ \t]*\n(.*?)^```", re.M | re.S)
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
LUMA = np.array([0.299, 0.587, 0.114])

SWATCH = {"color": None, "roughness": 0.8, "metallic": 0, "accent": False}
BUDGET = {"tri_budget", "texture_size", "limits"}
HELPERS = {"painted_light": ("nodes", "Tree.painted_light"), "brush": ("nodes", "Tree.brush"),
           "make_high": ("modeling", "make_high")}
PER_ASSET = {"top"}
FREE = {"scale", "shape", "kit"}
TOP = {"texture_mode", "limits", "palette", "budgets"} | set(HELPERS) | FREE


def luma(rgb):
    """Rec. 601 luma of sRGB values in 0–1, on the 0–255 scale checks report."""
    return np.asarray(rgb, dtype=float) @ LUMA * 255


def saturation(rgb):
    """HSV saturation of sRGB values in 0–1."""
    rgb = np.asarray(rgb, dtype=float)
    hi, lo = rgb.max(axis=-1), rgb.min(axis=-1)
    return np.where(hi > 0, (hi - lo) / np.maximum(hi, 1e-9), 0.0)


def rgb(hex_):
    return np.array([int(hex_[i:i + 2], 16) for i in (1, 3, 5)]) / 255


def chain(root, name):
    """Guide files for chain `name` ("", "<zone>" or "<zone>/<set>") in reading order.
    world_art.md heads every chain when it exists."""
    parts = [p for p in (name or "").split("/") if p]
    if len(parts) > len(LEVELS):
        raise SystemExit(f"art '{name}' has {len(parts)} levels; a chain is <zone> or <zone>/<set>")
    world = os.path.join(root, WORLD)
    files = [world] if os.path.exists(world) else []
    for i, level in enumerate(LEVELS[:len(parts)]):
        path = os.path.join(root, *parts[:i + 1], level)
        if not os.path.exists(path):
            raise SystemExit(f"art '{name}' needs {path} (pipeline/ART.md)")
        files.append(path)
    return files


def parse(path):
    """Every json block in one guide, joined into one object."""
    with open(path) as f:
        text = f.read()
    rules = {}
    for m in BLOCK.finditer(text):
        line = text.count("\n", 0, m.start(1)) + 1
        try:
            block = json.loads(m.group(1))
        except json.JSONDecodeError as e:
            raise SystemExit(f"{path}:{line + e.lineno - 1}: {e.msg}")
        if not isinstance(block, dict):
            raise SystemExit(f"{path}:{line}: a rules block is a json object")
        _join(rules, block, path)
    return rules


def _join(dst, src, path, trail=()):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _join(dst[k], v, path, trail + (k,))
        elif k in dst:
            raise SystemExit(f"{path}: {'.'.join(trail + (k,))} is set in two blocks; give each rule one home")
        else:
            dst[k] = v


def _override(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _override(dst[k], v)
        else:
            dst[k] = json.loads(json.dumps(v))


def merge(files, limit_names):
    """The chain's rules: each guide over the one above it, limits only tightening."""
    rules, origin = {}, {}
    for path in files:
        level = parse(path)
        _check_keys(level, path, limit_names)
        above = rules.get("limits", {})
        for k, v in level.get("limits", {}).items():
            _tighten(k, above.get(k), v, origin.get(k), path)
            origin[k] = path
        _override(rules, level)
    _check_palette(rules, files)
    return rules


def _tighten(key, old, new, old_path, path):
    """A lower guide's limit stays inside the one above: min_* rises, max_* falls, [lo, hi] narrows."""
    ranged = isinstance(old, list) and len(old) == 2
    if old is None or not (key.startswith(("min_", "max_")) or ranged):
        return
    if new is None:
        loose = True
    elif ranged:
        loose = not (isinstance(new, list) and len(new) == 2 and new[0] >= old[0] and new[1] <= old[1])
    else:
        loose = new < old if key.startswith("min_") else new > old
    if loose:
        raise SystemExit(f"{path}: limits.{key} {new} loosens {old} from {old_path}; "
                         "a lower guide only tightens a limit (pipeline/ART.md)")


def _check_keys(rules, path, limit_names):
    unknown = set(rules) - TOP
    if unknown:
        raise SystemExit(f"{path}: unknown rules {sorted(unknown)}; the keys are {sorted(TOP)} (pipeline/ART.md)")
    if rules.get("texture_mode", "stylized") not in ("stylized", "pbr"):
        raise SystemExit(f"{path}: texture_mode is 'stylized' or 'pbr'")
    bad = sorted(set(rules.get("limits", {})) - set(limit_names))
    if bad:
        raise SystemExit(f"{path}: {bad} are not limits; the limits are {sorted(limit_names)}")
    for name, s in rules.get("palette", {}).items():
        extra = set(s) - set(SWATCH) if isinstance(s, dict) else {"(not an object)"}
        if extra:
            raise SystemExit(f"{path}: palette.{name} has {sorted(extra)}; a swatch holds {sorted(SWATCH)}")
        if "color" in s and not HEX.match(str(s["color"])):
            raise SystemExit(f"{path}: palette.{name}.color {s['color']!r} is not '#rrggbb' sRGB")
        if s.get("metallic", 0) not in (0, 1):
            raise SystemExit(f"{path}: palette.{name}.metallic is 0 or 1 (pipeline/MATERIALS.md)")
    for cls, b in rules.get("budgets", {}).items():
        extra = set(b) - BUDGET if isinstance(b, dict) else {"(not an object)"}
        if extra:
            raise SystemExit(f"{path}: budgets.{cls} has {sorted(extra)}; a budget holds {sorted(BUDGET)}")
        bad = sorted(set(b.get("limits", {})) - set(limit_names))
        if bad:
            raise SystemExit(f"{path}: budgets.{cls}.limits {bad} are not limits")
    for helper in set(rules) & set(HELPERS):
        extra = set(rules[helper]) - _kwargs(helper)
        if extra:
            raise SystemExit(f"{path}: {helper} takes {sorted(_kwargs(helper))}, not {sorted(extra)}")


def _kwargs(helper):
    mod, attr = HELPERS[helper]
    fn = importlib.import_module(mod)
    for part in attr.split("."):
        fn = getattr(fn, part)
    return {p.name for p in inspect.signature(fn).parameters.values() if p.default is not p.empty} - PER_ASSET


def _check_palette(rules, files):
    limits = rules.get("limits", {})
    band, cap = limits.get("albedo_luma"), limits.get("max_saturation")
    where = files[-1] if files else "palette"
    for name, s in rules.get("palette", {}).items():
        if "color" not in s:
            raise SystemExit(f"{where}: palette.{name} has no color")
        if s.get("accent"):
            continue
        c = rgb(s["color"])
        y, sat = float(luma(c)), float(saturation(c))
        if band and not band[0] <= y <= band[1]:
            raise SystemExit(f"{where}: palette.{name} {s['color']} has luma {y:.0f}, outside limits.albedo_luma "
                             f"{band}; move it inside or mark it an accent")
        if cap is not None and sat > cap:
            raise SystemExit(f"{where}: palette.{name} {s['color']} has saturation {sat:.2f}, above "
                             f"limits.max_saturation {cap}; mute it or mark it an accent")


def show(files, rules, root, limits=None):
    """Print the chain's guides in reading order, its palette, and its other rules."""
    print("read, in order:" if files else "no art guides: this asset follows the pipeline defaults")
    for f in files:
        print(f"  {f}")
    palette = rules.get("palette", {})
    if palette:
        home = {name: os.path.relpath(f, root) for f in files for name in parse(f).get("palette", {})}
        print("palette:")
        print(f"  {'swatch':12} {'color':8} {'luma':>5} {'sat':>5} {'rough':>5} {'metal':>5}  from")
        for name, s in palette.items():
            s = {**SWATCH, **s}
            c = rgb(s["color"])
            print(f"  {name:12} {s['color']:8} {float(luma(c)):5.0f} {float(saturation(c)):5.2f} "
                  f"{s['roughness']:5} {s['metallic']:5}  {home[name]}{'  (accent)' if s['accent'] else ''}")
    rest = {k: v for k, v in rules.items() if k != "palette"}
    if rest:
        print("rules:")
        for k, v in rest.items():
            print(f"  {k}: {json.dumps(v)}")
    if limits is not None:
        print("limits in force (pipeline defaults, then the guides, then asset.json):")
        print(f"  {json.dumps(limits)}")
