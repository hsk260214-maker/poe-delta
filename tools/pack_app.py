"""앱 코드 묶기: exe 안에 넣을 기본 코드 폴더(stage) + 업데이트용 app-<버전>.zip + manifest.json.

  python tools/pack_app.py <stage 폴더> <출력 폴더>

묶는 것: app/**/*.py, app/pob/headless.lua, data/*.json, 두 MIT LICENSE.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def files() -> list[Path]:
    out = [p for p in (ROOT / "app").rglob("*.py") if "__pycache__" not in p.parts]
    out.append(ROOT / "app" / "pob" / "headless.lua")
    out += sorted((ROOT / "data").glob("*.json"))
    out += [ROOT / "LICENSE", ROOT / "data" / "LICENSE-awakened-poe-trade.txt"]
    return sorted(set(out))


def main() -> int:
    stage, outdir = Path(sys.argv[1]), Path(sys.argv[2])
    vtext = (ROOT / "app" / "version.py").read_text(encoding="utf-8")
    ver = re.search(r'VERSION\s*=\s*"([^"]+)"', vtext).group(1)
    m = re.search(r"MIN_LOADER\s*=\s*(\d+)", vtext)
    min_loader = int(m.group(1)) if m else 1

    shutil.rmtree(stage, ignore_errors=True)
    for p in files():
        dest = stage / p.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)

    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("app-*.zip"):
        old.unlink()
    zpath = outdir / f"app-{ver}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files():
            z.write(p, p.relative_to(ROOT).as_posix())
    sha = hashlib.sha256(zpath.read_bytes()).hexdigest()
    (outdir / "manifest.json").write_text(json.dumps(
        {"version": ver, "zip": zpath.name, "sha256": sha, "min_loader": min_loader}, indent=1), encoding="utf-8")
    print(f"app {ver}: {zpath.name} {zpath.stat().st_size // 1024} KB sha256={sha[:12]}… ({len(files())} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
