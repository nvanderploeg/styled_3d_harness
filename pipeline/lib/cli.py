import contextlib
import json
import os
import runpy
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402

import asset as asset_mod  # noqa: E402
from asset import Asset  # noqa: E402

sys.path.append(asset_mod.KIT)

USAGE = ("pipeline/asset <new|build|check|review|verify|status|export> <slug> [stage]\n"
         "       pipeline/asset approve <slug>... [--stage <stage>] [--revoke]\n"
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
    """Run the stage's build script on its source blend; the data files it read (asset.data_inputs)."""
    script = a.script(stage)
    if not os.path.exists(script):
        raise SystemExit(f"no build script at {script} — copy pipeline/templates/{stage}.py there")
    open_source(a, stage)
    with asset_mod.recording() as opened:
        runpy.run_path(script, init_globals={"asset": a}, run_name="__main__")
    return asset_mod.data_inputs(a, opened)


def build(a, stage):
    """Build stage and save it with its data inputs. An approved stage saves only a rebuild that matches its
    approval and, where maps are saved, bakes maps that match them; any other exits 1 and leaves the saved
    stage and its maps as they were."""
    import verify
    approval = a.approvals().get(stage)
    saved = None
    if approval and os.path.exists(a.blend(stage)):
        bpy.ops.wm.open_mainfile(filepath=a.blend(stage))
        saved = verify.snapshot(a)
    guard = approval and verify.has_maps(stage)
    with verify.scratch_maps(a, stage) if guard else contextlib.nullcontext() as maps:
        inputs = run_stage(a, stage)
        if approval:
            problems = verify.against_approval(approval, verify.snapshot(a), saved)
            if guard and os.path.isdir(maps[0]):
                problems += verify.diff_maps(*maps, a.slug)
            if problems:
                for p in problems:
                    print(f"CHANGED {p}")
                print(f"build {stage}: CHANGED against its approval of {approval['at']}; not saved. Undo the "
                      f"change, or revoke the approval to accept it: pipeline/asset approve {a.slug} --stage "
                      f"{stage} --revoke")
                sys.exit(1)
        if guard:
            shutil.rmtree(maps[0], ignore_errors=True)
            shutil.copytree(maps[1], maps[0])
    bpy.context.scene[asset_mod.INPUTS] = json.dumps(inputs)
    bpy.ops.wm.save_as_mainfile(filepath=a.blend(stage), compress=True)
    print(f"built {a.blend(stage)}")


def approve(args):
    """pipeline/asset approve <slug>... [--stage <stage>] [--revoke]; False when any asset was refused."""
    stage = args.pop(args.index("--stage") + 1) if "--stage" in args else None
    revoke = "--revoke" in args
    slugs = [x for x in args if x not in ("--stage", "--revoke")]
    if not slugs:
        raise SystemExit(USAGE)
    ok = True
    for slug in slugs:
        problems = asset_mod.approve(Asset(slug), stage, revoke)
        for p in problems:
            print(f"REFUSED {slug}: {p}")
        ok = ok and not problems
    return ok


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
    if argv[:1] == ["approve"]:
        if not approve(argv[1:]):
            sys.exit(1)
        return
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


if __name__ == "__main__":
    try:
        main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    except SystemExit as e:
        if isinstance(e.code, str):
            print(f"error: {e.code}", file=sys.stderr)
            sys.exit(2)
        raise
