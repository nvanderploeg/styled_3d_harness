import ast
import contextlib
import datetime
import hashlib
import json
import os
import sys

import bpy

import art

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = os.environ.get("ASSETS_DIR") or os.path.join(REPO, "assets")
KIT = os.path.join(ASSETS, "_kit")
LIB = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(ASSETS, "_art")

STAGES = ("model", "rig", "texture_base", "texture_ref", "bake", "animate")
MATERIALS = ("baked", "shared")
INPUTS = "pipeline_inputs"

SPEC_DEFAULTS = {
    "brief": "",
    "refs": [],
    "art": None,
    "budget_class": None,
    "rig": "none",
    "texture_mode": None,
    "materials": None,
    "tri_budget": 3000,
    "texture_size": 1024,
    "height_m": None,
}

LIMIT_DEFAULTS = {
    "max_tri_ratio": 0.15,
    "allow_open": False,
    "uv_overlap_ok": False,
    "min_uv_coverage": 0.35,
    "texel_density_tolerance": 2.0,
    "max_influences": 4,
    "max_bones": 80,
    "texel_density_px_per_m": None,
    "min_zone_contrast": 20,
    "albedo_luma": None,
    "max_saturation": None,
    "min_corner_deg": 0.5,
}


class Asset:
    def __init__(self, slug):
        self.slug = slug
        self.dir = os.path.join(ASSETS, slug)
        spec_path = self.path("asset.json")
        if not os.path.exists(spec_path):
            raise SystemExit(f"no asset at {self.dir} — run: pipeline/asset new {slug}")
        with open(spec_path) as f:
            raw = json.load(f)
        self.art_files = art.chain(ART, raw.get("art"))
        self.art = art.merge(self.art_files, LIMIT_DEFAULTS)
        budget = self.budget(raw.get("budget_class"))
        sized = {k: budget[k] for k in ("tri_budget", "head_tri_budget", "texture_size") if k in budget}
        self.spec = {**SPEC_DEFAULTS, **sized, **raw}
        if self.spec.get("head_tri_budget") is None and self.spec["rig"] == "humanoid":
            self.spec["head_tri_budget"] = self.spec["tri_budget"]
        if self.spec["texture_mode"] is None:
            self.spec["texture_mode"] = self.art.get("texture_mode")
        if self.spec["materials"] is None:
            self.spec["materials"] = self.art.get("materials", "baked")
        if self.spec["materials"] not in MATERIALS:
            raise SystemExit(f"materials is {self.spec['materials']!r}; it is one of {list(MATERIALS)} "
                             "(pipeline/ASSET.md)")
        # A class's limits replace the guides' rather than tighten them: a character's texel band sits above
        # a prop's.
        self.limits = {**LIMIT_DEFAULTS, **self.art.get("limits", {}), **budget.get("limits", {}),
                       **raw.get("limits", {})}

    def budget(self, name):
        """The guides' budget class `name`, or {} for none."""
        if name is None:
            return {}
        budgets = self.art.get("budgets", {})
        if name not in budgets:
            raise SystemExit(f"budget_class '{name}' is not a budget in the art guides; "
                             f"they have {sorted(budgets) or 'none'} (pipeline/asset art {self.slug})")
        return budgets[name]

    def path(self, *parts):
        return os.path.join(self.dir, *parts)

    def blend(self, stage):
        return self.path(f"{stage}.blend")

    def script(self, stage):
        return self.path("build", f"{stage}.py")

    def textures(self, stage):
        return self.path("textures", stage)

    def texture(self, stage, name):
        return os.path.join(self.textures(stage), f"{self.slug}_{name}.png")

    def fingerprint(self, stage=None):
        """Hash of what a build or check of stage reads: spec fields, limits in force and art rules.
        brief, refs and shots are notes, not inputs; budget_class counts through the values it supplies;
        animations are read by the animate stage alone."""
        notes = ("brief", "refs", "shots", "slug", "budget_class") + (() if stage == "animate" else ("animations",))
        inputs = {k: v for k, v in self.spec.items() if k not in notes}
        inputs["limits"] = self.limits
        if self.art:
            inputs["art"] = self.art
        return hashlib.sha1(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:12]

    def swatch(self, name):
        """The art guides' palette swatch `name` with its defaults filled in, or None."""
        s = self.art.get("palette", {}).get(name)
        return {**art.SWATCH, **s} if s else None

    def zone_table(self, local):
        """(sRGB colour, roughness, metallic) for every mesh zone: the guides' swatch where the palette
        has one, else local[zone]."""
        table = {}
        for mat in self.mesh.data.materials:
            zone = mat.name[5:]
            s = self.swatch(zone)
            if s and zone in local:
                raise SystemExit(f"zone '{zone}' has a swatch in the art guides; change it there, "
                                 "not in the build script")
            if not s and zone not in local:
                raise SystemExit(f"zone '{zone}' needs a colour: add it to the build script's table "
                                 "or to a guide's palette")
            table[zone] = (s["color"], s["roughness"], s["metallic"]) if s else local[zone]
        extra = sorted(set(local) - set(table))
        if extra:
            raise SystemExit(f"the build script's table names {extra}, which the mesh has no zone for; "
                             f"the zones are {sorted(table)}")
        return table

    @property
    def rigged(self):
        return self.spec["rig"] != "none"

    @property
    def animated(self):
        return self.rigged and bool((self.spec.get("animations") or {}).get("clips"))

    @property
    def shared(self):
        """True when the engine paints every zone with its own shared material, so the asset's only maps are the
        normal and occlusion of its bake stage."""
        return self.spec["materials"] == "shared"

    def stages(self):
        skip = {"rig": not self.rigged, "animate": not self.animated, "texture_base": self.shared,
                "texture_ref": self.shared, "bake": not self.shared}
        return [s for s in STAGES if not skip.get(s, False)]

    def upstream(self, stage):
        order = self.stages()
        if stage.startswith("texture") and self.shared:
            raise SystemExit(f"'{stage}' bakes textures, and this asset's materials are 'shared': the engine paints "
                             f"its zones. Its stages are {order}; its bake stage bakes its normal and occlusion maps")
        if stage == "bake" and not self.shared:
            raise SystemExit(f"'bake' is the detail bake of an asset whose materials are 'shared'; this asset's "
                             f"texture stages bake its maps. Its stages are {order}")
        if stage not in order:
            raise SystemExit(f"stage '{stage}' is not part of this asset: {order}")
        return order[: order.index(stage)]

    def source(self, stage):
        """Blend a stage builds on: the nearest upstream stage's output, or None for model."""
        up = self.upstream(stage)
        if not up:
            return None
        prev = up[-1]
        if not os.path.exists(self.blend(prev)):
            raise SystemExit(f"'{stage}' builds on '{prev}', which is not built yet")
        return self.blend(prev)

    def latest(self, prefix=""):
        built = [s for s in self.stages() if s.startswith(prefix) and os.path.exists(self.blend(s))]
        return built[-1] if built else None

    def report(self, stage):
        p = self.path("review", f"{stage}.json")
        if not os.path.exists(p):
            return None
        with open(p) as f:
            return json.load(f)

    def approvals(self):
        """approved.json: {stage: {"snapshot", "spec", "at"}} for each approved stage; {} when none is."""
        p = self.path("approved.json")
        if not os.path.exists(p):
            return {}
        with open(p) as f:
            return json.load(f)

    @property
    def mesh(self):
        return bpy.data.objects.get(self.slug)

    @property
    def high(self):
        return bpy.data.objects.get(f"{self.slug}_high")

    @property
    def armature(self):
        return bpy.data.objects.get(f"{self.slug}_rig")

    def size(self):
        """Largest bounding-box dimension of the mesh, in metres."""
        return max(self.mesh.dimensions) or 1.0


def new(slug):
    d = os.path.join(ASSETS, slug)
    for sub in ("build", "refs", "review", "textures", "export"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    spec = os.path.join(d, "asset.json")
    if not os.path.exists(spec):
        with open(spec, "w") as f:
            fields = ("brief", "refs", "art", "budget_class", "rig", "height_m")
            json.dump({"slug": slug, **{k: SPEC_DEFAULTS[k] for k in fields}, "limits": {}}, f, indent=2)
            f.write("\n")
    print(f"asset: {d}")


def build_modules(script):
    """Paths of the pipeline/lib and _kit modules a build script imports, directly or through each other,
    resolved in the build's order: pipeline/lib first. Only `import x` and `from x import y` statements count."""
    found, todo = set(), [script]
    while todo:
        path = todo.pop()
        if not os.path.exists(path):
            continue
        with open(path) as f:
            tree = ast.parse(f.read(), path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names = [node.module]
            else:
                continue
            for name in names:
                for home in (LIB, KIT):
                    mod = os.path.join(home, name.split(".")[0] + ".py")
                    if os.path.exists(mod):
                        if mod not in found:
                            found.add(mod)
                            todo.append(mod)
                        break
    return sorted(found)


WRITES = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
CODE = (".py", ".pyc", ".blend", ".blend1")
OUTPUTS = {"asset.json", "approved.json", "build", "review", "textures", "export"}
_opened = None
_hooked = False


def _audit(event, args):
    if event != "open" or _opened is None:
        return
    # A hook that raises fails the open it audits.
    try:
        path, _, flags = args
        if not isinstance(path, int):
            _opened.append((os.path.abspath(os.fsdecode(path)), flags))
    except Exception:
        pass


@contextlib.contextmanager
def recording():
    """Collect (absolute path, os flags) for every file Python code opens inside the block. Files Blender
    opens itself (images, libraries) are not seen."""
    global _opened, _hooked
    if not _hooked:
        sys.addaudithook(_audit)
        _hooked = True
    _opened = []
    try:
        yield _opened
    finally:
        _opened = None


def data_inputs(a, opened):
    """{path relative to ASSETS: input_hash} for the data files among opened: those under ASSETS that the build
    only read, less code, .blend files, the asset's own spec and outputs, and its own chain's guides, whose rules
    the fingerprint holds."""
    root, own = os.path.realpath(ASSETS), os.path.realpath(a.dir)
    chain = {os.path.realpath(f) for f in a.art_files}
    wrote = {os.path.realpath(p) for p, flags in opened if flags & WRITES}
    found = {}
    for p in {os.path.realpath(p) for p, _ in opened} - wrote - chain:
        rel = os.path.relpath(p, root)
        parts = rel.split(os.sep)
        if parts[0] == ".." or "__pycache__" in parts or p.endswith(CODE) or not os.path.isfile(p):
            continue
        if os.path.commonpath([p, own]) == own:
            first = os.path.relpath(p, own).split(os.sep)[0]
            if first in OUTPUTS or first.startswith("verify_"):
                continue
        rel = rel.replace(os.sep, "/")
        found[rel] = input_hash(rel)
    return dict(sorted(found.items()))


def input_hash(rel):
    """Hash of what a data input gives a build: a guide's json rules, so its prose counts for nothing, or any
    other file's bytes. None when the file is gone."""
    path = os.path.join(ASSETS, *rel.split("/"))
    if not os.path.isfile(path):
        return None
    if rel.startswith("_art/") and rel.endswith(".md"):
        try:
            data = json.dumps(art.parse(path), sort_keys=True).encode()
        except SystemExit as e:
            data = str(e.code).encode()
    else:
        with open(path, "rb") as f:
            data = f.read()
    return hashlib.sha1(data).hexdigest()[:12]


def stage_states(a):
    """(stage, state, changed) per stage: state is 'not built', 'stale — rebuild', 'unchecked', 'pass' or
    'FAIL (n)', and changed names what moved since a checked build: pipeline/lib, _kit, spec, data. A stage built
    after an unbuilt one is stale: its source is not the stage now upstream of it."""
    rows, upstream_mtime, gap = [], 0.0, False
    for s in a.stages():
        blend = a.blend(s)
        if not os.path.exists(blend):
            rows.append((s, "not built", []))
            gap = True
            continue
        mtime = os.path.getmtime(blend)
        rep = a.report(s)
        script = a.script(s)
        changed = []
        if gap or mtime < upstream_mtime or (os.path.exists(script) and os.path.getmtime(script) > mtime):
            state = "stale — rebuild"
        elif rep is None or rep.get("built") != mtime:
            state = "unchecked"
        else:
            state = "pass" if rep["pass"] else f"FAIL ({len(rep['fail'])})"
            since = max(mtime, rep.get("verified", 0.0))
            moved = [m for m in build_modules(script) if os.path.getmtime(m) > since]
            changed = [f"{label} ({', '.join(os.path.basename(m) for m in moved if os.path.dirname(m) == home)})"
                       for label, home in (("pipeline/lib", LIB), ("_kit", KIT))
                       if any(os.path.dirname(m) == home for m in moved)]
            if rep.get("spec") != a.fingerprint(s):
                changed.append("spec")
            data = [os.path.basename(rel) for rel, h in (rep.get("inputs") or {}).items() if input_hash(rel) != h]
            if data:
                changed.append(f"data ({', '.join(dict.fromkeys(data))})")
        rows.append((s, state, changed))
        upstream_mtime = max(upstream_mtime, mtime)
    return rows


def describe(a, stage, state, changed, approval=None):
    """One status line's state: the state, the approval's standing, and what changed since with how to clear it."""
    head, _, tail = state.partition(" — ")
    if approval:
        rep, blend = a.report(stage), a.blend(stage)
        moved = (rep and os.path.exists(blend) and rep.get("built") == os.path.getmtime(blend)
                 and rep.get("snapshot") not in (None, approval["snapshot"]))
        head += ", CHANGED since approval" if moved else ", approved"
    if changed:
        tail = f"{' and '.join(changed)} changed since; run: pipeline/asset verify {a.slug} {stage}"
    return head + (" — " + tail if tail else "")


def status(a):
    approved = a.approvals()
    rows = [(s, describe(a, s, state, changed, approved.get(s))) for s, state, changed in stage_states(a)]
    latest = max((os.path.getmtime(a.blend(s)) for s in a.stages() if os.path.exists(a.blend(s))), default=0.0)
    glb = a.path("export", f"{a.slug}.glb")
    if not os.path.exists(glb):
        rows.append(("export", "not exported"))
    else:
        rows.append(("export", "stale — re-export" if os.path.getmtime(glb) < latest else "exported"))
    for s, state in rows:
        print(f"{s:14} {state}")


def approve(a, stage=None, revoke=False):
    """Record stage (default: the last built) and every stage upstream of it in approved.json, each with its
    report's snapshot, its spec fingerprint and the time. With revoke, drop stage and every later stage (every
    stage without one). Returns why it refused; [] when it did not."""
    approved, order = a.approvals(), a.stages()
    if stage is not None:
        a.upstream(stage)
    if revoke:
        gone = [s for s in order[order.index(stage) if stage else 0:] if s in approved]
        for s in gone:
            del approved[s]
        _write_approvals(a, approved)
        print(f"revoked {a.slug}: {', '.join(gone) or 'nothing to revoke'}")
        return []
    stage = stage or a.latest()
    if stage is None:
        return [f"{a.slug} has no built stage"]
    want = order[: order.index(stage) + 1]
    problems = []
    for s, state, changed in stage_states(a):
        if s not in want:
            continue
        if state != "pass" or changed:
            problems.append(f"{s} is {describe(a, s, state, changed)}")
        elif not a.report(s).get("snapshot"):
            problems.append(f"{s} has no snapshot in its report; run: pipeline/asset check {a.slug} {s}")
    if problems:
        return problems
    at = datetime.datetime.now().isoformat(timespec="seconds")
    for s in want:
        rep = a.report(s)
        approved[s] = {"snapshot": rep["snapshot"], "spec": rep["spec"], "at": at}
    _write_approvals(a, approved)
    print(f"approved {a.slug}: {', '.join(want)}")
    return []


def _write_approvals(a, approved):
    p = a.path("approved.json")
    if not approved:
        if os.path.exists(p):
            os.remove(p)
        return
    with open(p, "w") as f:
        json.dump({s: approved[s] for s in STAGES if s in approved}, f, indent=2)
        f.write("\n")
