"""Extract and convert everything on a Grabbed by the Ghoulies disc in one go.

usage: python -I extract_all.py <game.iso | unpacked disc folder> <out_dir> [options]

options:
  --tools DIR   folder to look in for xdvdfs / vgmstream-cli / ffmpeg (besides PATH)
  --no-av       skip audio and video conversion
  --no-glb      skip the rigged .glb export

Output:
  out/iso_root   the disc's files (only when given an .iso)
  out/assets     every bundle unpacked: models, textures (PNG), fonts, text, raw assets
  out/rigged     every model as a rigged, animated .glb
  out/scripts    every scene script as readable .gscript text
  out/audio      wavebanks as WAV          (needs vgmstream-cli)
  out/video      Bink and XMV videos as MP4 (needs ffmpeg)

Needs: Python 3.10+ with numpy and matplotlib, git, Rust (cargo), and xdvdfs for .iso input.
Steps that are already done get skipped, so it can be re-run after an error.
"""
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE / "tools"
DEPS = HERE / "extract" / "deps"
HASHES_URL = "https://raw.githubusercontent.com/x1nixmzeng/project-grabbed/master/hashes/ghoulies.txt"
REPOS = {"bnl": "https://github.com/luboise/bnl.git", "gltf_writer": "https://github.com/luboise/gltf_writer.git"}

args = [a for a in sys.argv[1:] if not a.startswith("--")]
flags = [a for a in sys.argv[1:] if a.startswith("--")]
if len(args) < 2:
    sys.exit(__doc__)
src, out = Path(args[0]).resolve(), Path(args[1]).resolve()
extra_tools = None
if "--tools" in sys.argv:
    extra_tools = Path(sys.argv[sys.argv.index("--tools") + 1]).resolve()
    args = [a for a in args if Path(a).resolve() != extra_tools]
    src, out = Path(args[0]).resolve(), Path(args[1]).resolve()


def step(msg):
    print(f"\n== {msg}", flush=True)


def run(cmd, **kw):
    print("  > " + " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd], **kw)
    if r.returncode != 0:
        sys.exit(f"failed (exit {r.returncode}): {cmd[0]}")
    return r


def find_tool(name):
    for n in (name, name + ".exe"):
        if extra_tools and (extra_tools / n).exists():
            return extra_tools / n
        if extra_tools:
            hit = next(extra_tools.rglob(n), None)
            if hit:
                return hit
    return shutil.which(name)


def has_files(d):
    return d.is_dir() and any(d.iterdir())


def py(script, *a):
    run([sys.executable, "-I", TOOLS / script, *a])


out.mkdir(parents=True, exist_ok=True)

# ---- 1. disc files
if src.is_dir():
    iso_root = src
else:
    iso_root = out / "iso_root"
    step("unpacking disc")
    if has_files(iso_root):
        print("  already unpacked")
    else:
        xdvdfs = find_tool("xdvdfs") or sys.exit("xdvdfs not found (https://github.com/antangelo/xdvdfs/releases)")
        run([xdvdfs, "unpack", src, iso_root])
if not (iso_root / "default.xbe").exists():
    sys.exit(f"{iso_root} doesn't look like the game's disc (no default.xbe)")

# ---- 2. asset name table
hashes = out / "ghoulies.txt"
if not hashes.exists():
    step("downloading asset name table (project-grabbed)")
    urllib.request.urlretrieve(HASHES_URL, hashes)

# ---- 3. bnl library + fixes, then the extractor
step("setting up bnl")
DEPS.mkdir(parents=True, exist_ok=True)
for name, url in REPOS.items():
    if not (DEPS / name).exists():
        run(["git", "clone", "-q", url, DEPS / name])
patch = HERE / "extract" / "bnl_fixes.patch"
already = subprocess.run(["git", "-C", DEPS / "bnl", "apply", "--reverse", "--check", patch],
                         capture_output=True).returncode == 0
if already:
    print("  fixes already applied")
else:
    run(["git", "-C", DEPS / "bnl", "apply", patch])

step("building the extractor")
run(["cargo", "build", "--release", "--quiet", "--manifest-path", HERE / "extract" / "Cargo.toml"])
exe = ".exe" if sys.platform == "win32" else ""
bins = HERE / "extract" / "target" / "release"

assets = out / "assets"
step("extracting bundles (models, textures, fonts, text)")
if has_files(assets / "bundles"):
    print("  already extracted")
else:
    run([bins / f"ghoul_extract{exe}", iso_root, assets, hashes])

step("decoding model textures")
model_dirs = sorted(p for p in assets.rglob("Model__*") if p.is_dir())
for i in range(0, len(model_dirs), 40):  # batches keep the command line short
    run([bins / f"model_textures{exe}", *model_dirs[i:i + 40]], stdout=subprocess.DEVNULL)
print(f"  {len(model_dirs)} models")

# ---- 4. rigged models
if "--no-glb" not in flags:
    step("exporting rigged models to .glb")
    rigged = out / "rigged"
    if has_files(rigged):
        print("  already exported")
    else:
        survey = out / "survey.json"
        py("survey.py", assets, survey)
        py("batch_export.py", survey, rigged)

# ---- 5. scene scripts
step("dumping scene scripts")
if has_files(out / "scripts"):
    print("  already dumped")
else:
    py("ghoul_script.py", "dumpall", assets, out / "scripts")

# ---- 6. audio / video
if "--no-av" not in flags:
    names = {}
    for line in hashes.read_text(errors="replace").splitlines():
        parts = line.strip().split(",")
        if len(parts) >= 3 and parts[2]:
            names.setdefault(parts[0].lower().removeprefix("0x"), parts[2])

    def resolve(stem):
        return names.get(stem.lower(), stem)

    step("converting audio")
    vgm = find_tool("vgmstream-cli")
    if not vgm:
        print("  vgmstream-cli not found, skipping (https://github.com/vgmstream/vgmstream/releases)")
    else:
        banks = sorted((iso_root / "xwavebank").glob("*")) + sorted((iso_root / "cdxmedia").glob("*.xwb"))
        for f in banks:
            n = resolve(f.stem)
            d = out / "audio" / n
            if has_files(d):
                continue
            d.mkdir(parents=True, exist_ok=True)
            # -S 0 = every sound in the bank, ?04s = its number
            subprocess.run([str(vgm), "-i", "-S", "0", "-o", str(d / f"{n}_?04s.wav"), str(f)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"  {n}: {len(list(d.glob('*.wav')))} sounds")

    step("converting video")
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        print("  ffmpeg not found, skipping (https://ffmpeg.org/download.html)")
    else:
        vids = [(f, out / "video" / "movie" / f"{resolve(f.name)}.mp4") for f in sorted((iso_root / "movie").glob("*"))]
        vids += [(f, out / "video" / "Videos" / f"{f.stem}.mp4") for f in sorted((iso_root / "Videos").glob("*.xmv"))]
        failed = []
        for f, dst in vids:
            if dst.exists():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            # some Bink videos have odd sizes, which x264 can't encode: pad to even
            r = subprocess.run([str(ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(f),
                                "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264", "-crf", "16",
                                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(dst)])
            if r.returncode != 0:
                failed.append(f.name)
                dst.unlink(missing_ok=True)
        print(f"  {len(vids) - len(failed)} of {len(vids)} videos converted" + (f"; failed: {failed}" if failed else ""))

step(f"done: {out}")
