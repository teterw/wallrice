"""The wallpaper library: curated collections downloaded into ~/Pictures/walls/<collection>/, folders
of your own next to them, and the Yes/No review's choices.

Git collections are partial clones with a sparse checkout: only the picture folders are downloaded,
and pictures removed in the review are sparse-checkout exclusions, so updates never bring them back
(taking one out of review.json and re-applying the patterns restores it from git's local objects,
with no download). List collections are plain downloads, each file checked against a pinned SHA-256:
a file whose checksum doesn't match is skipped, not installed."""
import configparser
import functools
import hashlib
import os
import random
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from . import __version__, paths
from .state import load_review

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MOVING = ("*.gif", "*.mp4", "*.webm", "*.mkv", "*.mov")  # still images only: never download these
SYSTEM_WALLS = (Path("/usr/share/backgrounds"),)
THUMB = (320, 180)


# ---------------------------------------------------------------- configuration

def conf_file(name):
    """~/.config/wallrice/<name> if the user made one, else the one shipped with wallrice."""
    mine = paths.config() / name
    return mine if mine.is_file() else paths.resource("data", name)


def sources():
    """The collections in review order: {name: {"git" or "list", "branch", "paths", "about"}}."""
    cfg = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";",))
    cfg.read(conf_file("collections.conf"), encoding="utf-8")
    return {name: dict(cfg[name]) for name in cfg.sections()}


@functools.lru_cache(maxsize=None)
def _entries(path, mtime):
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            sha, url, name, title, credit = (line.split("\t") + [""] * 5)[:5]
            out.append((sha.strip(), url.strip(), name.strip(), title.strip(), credit.strip()))
    return tuple(out)


def list_entries(listfile):
    """A list collection's files: [(sha256, url, file, title, credit)]."""
    p = conf_file(listfile)
    try:
        return list(_entries(str(p), p.stat().st_mtime))
    except OSError:
        return []


def sets():
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(conf_file("sets.conf"), encoding="utf-8")
    out = {}
    for name in cfg.sections():
        sec = cfg[name]
        out[name] = {"include": (sec.get("include") or "").split(), "exclude": (sec.get("exclude") or "").split()}
    out.setdefault("all", {"include": [], "exclude": []})
    return out


# ---------------------------------------------------------------- listing

def images_in(folder):
    found = []
    for dirpath, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))  # skips .git
        found += [Path(dirpath) / f for f in files if Path(f).suffix.lower() in IMAGE_EXT and not f.startswith(".")]
    return sorted(found)


def all_pictures():
    """Every downloaded picture not removed in the review, in review order; folders of your own in
    the walls folder come after the collections."""
    walls = paths.walls()
    if not walls.is_dir():
        return []
    drop = load_review()["drop"]
    names = list(sources())
    own = sorted(p.name for p in walls.iterdir() if p.is_dir() and not p.name.startswith(".") and p.name not in names)
    loose = [p for p in sorted(walls.iterdir()) if p.is_file() and p.suffix.lower() in IMAGE_EXT]
    out = []
    for name in names + own:
        out += [p for p in images_in(walls / name) if rel(p) not in drop]
    return out + [p for p in loose if rel(p) not in drop]


def system_pictures():
    """Until a collection is downloaded: the distro's wallpapers and the user's own backgrounds."""
    out = []
    for d in (paths.data_home() / "backgrounds", *SYSTEM_WALLS):
        if d.is_dir():
            out += images_in(d)
    return out


def wallpapers(mode="all"):
    s = sets().get(mode) or sets()["all"]
    inc, exc = set(s["include"]), set(s["exclude"])
    walls = paths.walls()
    pics = []
    for p in all_pictures():
        parts = p.relative_to(walls).parts
        keys = {parts[0], "/".join(parts[:2])}
        if (inc and not keys & inc) or keys & exc:
            continue
        pics.append(p)
    return pics or system_pictures()


def rel(p):
    """A picture's path relative to the walls folder (how review.json names it)."""
    try:
        return str(Path(p).relative_to(paths.walls()))
    except ValueError:
        return str(p)


def in_walls(p):
    try:
        Path(p).relative_to(paths.walls())
        return True
    except ValueError:
        return False


def describe(img):
    """(collection, folder, title, credit) to show with a picture."""
    img = Path(img)
    title = img.stem.replace("_", " ").replace("-", " ").strip()
    if not in_walls(img):
        return img.parent.name, "", title, ""
    parts = img.relative_to(paths.walls()).parts
    src = sources().get(parts[0], {})
    if "list" in src:
        for _sha, _url, name, t, credit in list_entries(src["list"]):
            if name == img.name:
                return parts[0], "", t or title, credit
    folder = parts[-2] if len(parts) > 2 else ""
    return parts[0] if len(parts) > 1 else "walls", folder, title, ""


def pick_random(mode="all", avoid=None):
    pics = wallpapers(mode)
    if avoid and len(pics) > 1:
        pics = [p for p in pics if str(p) != str(avoid)]
    return random.choice(pics) if pics else None


# ---------------------------------------------------------------- downloading

def git(*args, cwd=None, stdin=None):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    p = subprocess.run(["git", *args], cwd=cwd, input=stdin, capture_output=True, text=True, env=env)
    if p.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {(p.stderr or p.stdout).strip()[-300:]}")
    return p.stdout


def sparse_patterns(src, drops):
    """The collection's folders, minus the pictures dropped in the review (gitignore syntax)."""
    def esc(r):
        r = "".join("\\" + ch if ch in "*?[\\" else ch for ch in r)
        return r[:-1] + "\\ " if r.endswith(" ") else r
    pats = src.get("paths", "/*").split() + [f"!{m}" for m in MOVING]
    return "\n".join(pats + [f"!/{esc(r)}" for r in sorted(drops)]) + "\n"


def sync_git(name, src, drops, say=print):
    dest = paths.walls() / name
    branch = src.get("branch", "main")
    if not (dest / ".git").is_dir():
        shutil.rmtree(dest, ignore_errors=True)
        say(f"{name}: downloading {src['git']} …")
        git("clone", "--quiet", "--filter=blob:none", "--no-checkout", "--depth", "1", "--branch", branch, src["git"], str(dest))
        git("sparse-checkout", "set", "--no-cone", "--stdin", cwd=dest, stdin=sparse_patterns(src, drops))
        git("checkout", "--quiet", branch, cwd=dest)
    else:
        say(f"{name}: updating …")
        git("sparse-checkout", "set", "--no-cone", "--stdin", cwd=dest, stdin=sparse_patterns(src, drops))
        git("fetch", "--quiet", "--depth", "1", "origin", branch, cwd=dest)
        git("reset", "--quiet", "--hard", "FETCH_HEAD", cwd=dest)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": f"wallrice/{__version__} (+https://github.com/teterw/wallrice)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def sync_list(name, src, drops, say=print, fetch=fetch):
    dest = paths.walls() / name
    dest.mkdir(parents=True, exist_ok=True)
    entries = list_entries(src["list"])
    wanted = {f for _sha, _url, f, _t, _c in entries if f not in drops}
    todo = [e for e in entries if e[2] in wanted and not ((dest / e[2]).is_file() and sha256(dest / e[2]) == e[0])]
    if todo:
        say(f"{name}: downloading {len(todo)} pictures …")
    for n, (sha, url, f, title, _credit) in enumerate(todo, 1):
        if not url.startswith("https://"):
            say(f"{name}: {title}: not https, skipped")
            continue
        try:
            data = fetch(url)
        except OSError as e:
            say(f"{name}: {title}: download failed ({e}), skipped")
            continue
        if hashlib.sha256(data).hexdigest() != sha:
            say(f"{name}: {title}: checksum mismatch, skipped")
            continue
        tmp = dest / f".{f}.part"
        tmp.write_bytes(data)
        tmp.replace(dest / f)
        if n % 10 == 0:
            say(f"{name}: {n}/{len(todo)}")
    for p in dest.iterdir():  # no longer listed, or removed in the review
        if p.is_file() and p.name not in wanted:
            p.unlink()


def drops_for(name, review=None):
    review = review or load_review()
    return {r[len(name) + 1:] for r in review["drop"] if r.startswith(name + "/")}


def update(say=print):
    """`wallrice walls update`: download or update every collection."""
    paths.walls().mkdir(parents=True, exist_ok=True)
    review = load_review()
    for name, src in sources().items():
        try:
            if "git" in src:
                if not shutil.which("git"):
                    say(f"{name}: skipped (git isn't installed)")
                    continue
                sync_git(name, src, drops_for(name, review), say)
            elif "list" in src:
                sync_list(name, src, drops_for(name, review), say)
        except (RuntimeError, OSError) as e:  # one collection failing doesn't stop the others
            say(f"{name}: {e}")
    pics = all_pictures()
    say("Making thumbnails …")
    build_thumbs(pics)
    clean_caches(pics)
    status(say)


def apply_review():
    """Take the pictures dropped in the review off the disk (from git collections through the sparse
    checkout, so updates don't bring them back)."""
    review = load_review()
    for name, src in sources().items():
        dest = paths.walls() / name
        drops = drops_for(name, review)
        if not dest.is_dir():
            continue
        if "git" in src and (dest / ".git").is_dir():
            git("sparse-checkout", "set", "--no-cone", "--stdin", cwd=dest, stdin=sparse_patterns(src, drops))
        else:
            for r in drops:
                (dest / r).unlink(missing_ok=True)
    walls = paths.walls()
    own = [r for r in review["drop"] if r.split("/", 1)[0] not in sources()]
    for r in own:  # pictures of your own go to the desktop's trash, never straight to deletion
        p = walls / r
        if p.is_file():
            rc = subprocess.run(["gio", "trash", str(p)], capture_output=True).returncode if shutil.which("gio") else 1
            if rc != 0:
                trash = walls / ".removed" / r
                trash.parent.mkdir(parents=True, exist_ok=True)
                p.replace(trash)


def status(say=print):
    review = load_review()
    pics = all_pictures()
    walls = paths.walls()
    names = list(sources())
    total = 0
    for name in names + ["(your own)"]:
        mine = [p for p in pics if (p.relative_to(walls).parts[0] == name if name != "(your own)"
                                    else p.relative_to(walls).parts[0] not in names)]
        if not mine and name == "(your own)":
            continue
        kept = sum(rel(p) in review["keep"] for p in mine)
        dropped = sum(r.startswith(name + "/") for r in review["drop"])
        about = sources().get(name, {}).get("about", "")
        say(f"  {name:12} {len(mine):4} pictures  {kept:4} kept  {dropped:4} removed  {about}")
        total += len(mine)
    left = sum(rel(p) not in review["keep"] for p in pics)
    say(f"{total} wallpapers in {walls}. " + (f"{left} not reviewed yet: wallrice walls review" if left else "All reviewed."))


def update_in_background():
    """Start `walls update` detached, logging to ~/.cache/wallrice/update.log (it can take a while)."""
    log = paths.cache() / "update.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    exe = [sys.executable, "-m", "wallrice", "walls", "update"]
    with open(log, "ab") as f:
        f.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n".encode())
        subprocess.Popen(exe, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True,
                         cwd=str(paths.SRC), env={**os.environ, "PYTHONUNBUFFERED": "1"})
    return log


# ---------------------------------------------------------------- thumbnails and caches

def thumb_path(img):
    return paths.cache() / "thumbs" / (hashlib.sha1(str(img).encode()).hexdigest() + ".jpg")


def build_thumbs(pics, say=None):
    from PIL import Image, ImageOps
    todo = [p for p in pics if not thumb_path(p).exists()]
    (paths.cache() / "thumbs").mkdir(parents=True, exist_ok=True)
    for n, p in enumerate(todo, 1):
        try:
            with Image.open(p) as im:
                im.draft("RGB", (THUMB[0] * 2, THUMB[1] * 2))
                ImageOps.fit(im.convert("RGB"), THUMB, Image.BILINEAR).save(thumb_path(p), quality=82)
        except Exception:  # noqa: BLE001 - a broken image just gets no thumbnail
            continue
        if say and n % 100 == 0:
            say(f"thumbnails: {n}/{len(todo)}")
    return len(todo)


def clean_caches(pics):
    """Drop thumbnails and palettes of pictures that are gone."""
    from .palette import cache_path
    keep = {thumb_path(p).name for p in pics}
    for t in (paths.cache() / "thumbs").glob("*.jpg"):
        if t.name not in keep:
            t.unlink(missing_ok=True)
    keep = set()
    for p in pics:
        try:
            keep.add(cache_path(p).name)
        except OSError:
            continue
    for f in (paths.cache() / "palettes").glob("*.json"):
        if f.name not in keep:
            f.unlink(missing_ok=True)

