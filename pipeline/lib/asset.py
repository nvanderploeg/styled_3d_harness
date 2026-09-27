import hashlib
import json
import os

import bpy

import art

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = os.environ.get("ASSETS_DIR") or os.path.join(REPO, "assets")
KIT = os.path.join(ASSETS, "_kit")
ART = os.path.join(ASSETS, "_art")

STAGES = ("model", "rig", "texture_base", "texture_ref")

SPEC_DEFAULTS = {
    "brief": "",
    "refs": [],
    "art": None,
    "rig": "none",
    "texture_mode": None,
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
        self.spec = {**SPEC_DEFAULTS, **raw}
        if self.spec["texture_mode"] is None:
            self.spec["texture_mode"] = self.art.get("texture_mode")
        self.limits = {**LIMIT_DEFAULTS, **self.art.get("limits", {}), **raw.get("limits", {})}

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

    def fingerprint(self):
        """Hash of what a build or check reads: spec fields, limits in force and art rules.
        brief, refs and shots are notes, not inputs."""
        inputs = {k: v for k, v in self.spec.items() if k not in ("brief", "refs", "shots", "slug")}
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
        return table

    @property
    def rigged(self):
        return self.spec["rig"] != "none"

    def stages(self):
        return [s for s in STAGES if s != "rig" or self.rigged]

    def upstream(self, stage):
        order = self.stages()
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
            json.dump({"slug": slug, **SPEC_DEFAULTS, "limits": {}}, f, indent=2)
            f.write("\n")
    print(f"asset: {d}")


def status(a):
    kit = max((os.path.getmtime(os.path.join(KIT, f)) for f in os.listdir(KIT) if f.endswith(".py")),
              default=0.0) if os.path.isdir(KIT) else 0.0
    rows, upstream_mtime = [], 0.0
    for s in a.stages():
        blend = a.blend(s)
        if not os.path.exists(blend):
            rows.append((s, "not built"))
            continue
        mtime = os.path.getmtime(blend)
        rep = a.report(s)
        script = a.script(s)
        if mtime < upstream_mtime or (os.path.exists(script) and os.path.getmtime(script) > mtime):
            state = "stale — rebuild"
        elif rep is None or rep.get("built") != mtime:
            state = "unchecked"
        else:
            state = "pass" if rep["pass"] else f"FAIL ({len(rep['fail'])})"
            changed = ["_kit"] if kit > max(mtime, rep.get("verified", 0.0)) else []
            if rep.get("spec") != a.fingerprint():
                changed.append("spec")
            if changed:
                state += f" — {' and '.join(changed)} changed since; run: pipeline/asset verify {a.slug} {s}"
        rows.append((s, state))
        upstream_mtime = max(upstream_mtime, mtime)
    glb = a.path("export", f"{a.slug}.glb")
    if not os.path.exists(glb):
        rows.append(("export", "not exported"))
    else:
        rows.append(("export", "stale — re-export" if os.path.getmtime(glb) < upstream_mtime else "exported"))
    for s, state in rows:
        print(f"{s:14} {state}")
