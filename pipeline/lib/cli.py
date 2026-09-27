import os
import runpy
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402

import asset as asset_mod  # noqa: E402
from asset import Asset  # noqa: E402

sys.path.append(asset_mod.KIT)

USAGE = ("pipeline/asset <new|build|check|review|verify|status|export> <slug> [stage]\n"
         "       pipeline/asset compare <stage> <slug> <slug>... [--tolerance luma]\n"
         "       pipeline/asset art [<slug> | <world>[/<zone>[/<set>]] [--sheet <png>]]")


def open_source(a, stage):
    src = a.source(stage)
    if src:
        bpy.ops.wm.open_mainfile(filepath=src)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.engine = "CYCLES"


def run_stage(a, stage):
    script = a.script(stage)
    if not os.path.exists(script):
        raise SystemExit(f"no build script at {script} — copy pipeline/templates/{stage}.py there")
    open_source(a, stage)
    runpy.run_path(script, init_globals={"asset": a}, run_name="__main__")


def build(a, stage):
    run_stage(a, stage)
    bpy.ops.wm.save_as_mainfile(filepath=a.blend(stage), compress=True)
    print(f"built {a.blend(stage)}")


def show_art(args):
    """Every chain; or one asset's chain; or a chain named directly while its guides are being written."""
    import art
    sheet = args.pop(args.index("--sheet") + 1) if "--sheet" in args else None
    args = [x for x in args if x != "--sheet"]
    if not args:
        found = art.chains(asset_mod.ART)
        print("\n".join(found) if found else f"no art guides in {asset_mod.ART} (pipeline/ART.md)")
        return
    target = args[0]
    if os.path.exists(os.path.join(asset_mod.ASSETS, target, "asset.json")):
        a = Asset(target)
        files, rules, limits = a.art_files, a.art, a.limits
    else:
        files = art.chain(asset_mod.ART, target)
        rules, limits = art.merge(files, asset_mod.LIMIT_DEFAULTS), None
    art.show(files, rules, asset_mod.ART, limits)
    if sheet:
        art.sheet(rules, os.path.abspath(sheet))


def main(argv):
    if argv[:1] == ["art"]:
        return show_art(argv[1:])
    if len(argv) < 2:
        raise SystemExit(USAGE)
    cmd, slug, *rest = argv
    if cmd == "compare":
        import verify
        tol = float(rest.pop(rest.index("--tolerance") + 1)) if "--tolerance" in rest else 8.0
        rest = [s for s in rest if s != "--tolerance"]
        if not verify.compare([Asset(s) for s in rest], stage=slug, tolerance=tol):
            sys.exit(1)
        return
    if cmd == "new":
        return asset_mod.new(slug)
    a = Asset(slug)
    if cmd == "status":
        return asset_mod.status(a)
    if cmd == "export":
        import export
        return export.export(a)
    if not rest:
        raise SystemExit(USAGE)
    stage = rest[0]
    a.upstream(stage)
    if cmd == "build":
        return build(a, stage)
    if cmd == "verify":
        import verify
        if not os.path.exists(a.blend(stage)):
            raise SystemExit(f"'{stage}' is not built")
        if not verify.verify(a, stage, run_stage):
            sys.exit(1)
        return
    if not os.path.exists(a.blend(stage)):
        raise SystemExit(f"'{stage}' is not built")
    bpy.ops.wm.open_mainfile(filepath=a.blend(stage))
    if cmd == "check":
        import checks
        if not checks.run(a, stage):
            sys.exit(1)
    elif cmd == "review":
        import review
        review.run(a, stage)
    else:
        raise SystemExit(USAGE)


try:
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
except SystemExit as e:
    if isinstance(e.code, str):
        print(f"error: {e.code}", file=sys.stderr)
        sys.exit(2)
    raise
