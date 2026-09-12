"""Where an image sent from a phone lands, so a command can name a file.

The desktop file picker handed DriverManager absolute paths off the PC's
own disk; a phone has no such path, so its bytes travel once, are written
here, and the path save_upload returns goes into `post_to_timeline` /
queue items exactly as the picker's did - the worker never learns the
difference.

Nothing about the incoming name is trusted. A multipart filename is a
string a device chose and can say anything: a parent directory, a device
name, an executable suffix, a megabyte of padding. The stored name is
rebuilt from the allowed characters only, and the suffix decides whether
the file is written at all. Routes that accept a path back from a client
must still check it resolves inside UPLOAD_DIR - a name that is safe to
store says nothing about a path that was never stored here.
"""
import re
from datetime import date
from pathlib import Path

UPLOAD_DIR = Path.home() / ".autoshare" / "uploads"

# What Facebook's composer accepts, and all this folder is for. Anything
# else is refused at the door rather than stored and rejected later by a
# browser nobody is watching.
ALLOWED_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})

# A phone photo is a few MB; well past that the sender is not a camera.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

# Long enough to keep a recognisable name, short enough that the folder,
# the suffix and a collision counter stay inside Windows' 260-char path.
MAX_STEM_LEN = 60

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")

# Reserved on Windows whatever the suffix is: opening "CON.png" opens the
# console, writes nothing, and leaves the path this returned non-existent.
_RESERVED = frozenset({"CON", "PRN", "AUX", "NUL"}
                      | {f"COM{i}" for i in range(1, 10)}
                      | {f"LPT{i}" for i in range(1, 10)})


def safe_name(filename: str) -> str:
    """The name this file will be stored under, built from the client's.

    Only the last path component survives (a device may send
    "../../evil.png"), every character outside [A-Za-z0-9._-] becomes an
    underscore, and a suffix outside ALLOWED_SUFFIXES raises ValueError.
    """
    raw = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    suffix = Path(raw).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"unsupported file type: {suffix or 'none'}")
    # Leading dots are stripped with the rest: ".png" alone would otherwise
    # store as a hidden, extension-only file.
    stem = _UNSAFE.sub("_", Path(raw).stem)[:MAX_STEM_LEN].strip("._-")
    if not stem or stem.upper() in _RESERVED:
        stem = f"upload_{stem}" if stem else "upload"
    return f"{stem}{suffix}"


def save_upload(filename: str, data: bytes) -> str:
    """Write one uploaded image under UPLOAD_DIR/<YYYY-MM-DD>/ and return
    its absolute path.

    Raises ValueError on a type this folder does not hold or more bytes
    than MAX_UPLOAD_BYTES; nothing is written in either case. A name
    already taken gets a counter rather than overwriting the earlier file,
    which a queue item may still be pointing at.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    name = safe_name(filename)
    # Read through the module global on purpose: proofs point UPLOAD_DIR at
    # a temp folder, and a path bound at import time would ignore them.
    day_dir = Path(UPLOAD_DIR) / f"{date.today():%Y-%m-%d}"
    day_dir.mkdir(parents=True, exist_ok=True)
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate = day_dir / name
    n = 0
    while True:
        try:
            # Exclusive create, not exists(): two phones uploading the same
            # name in the same instant must not both win the check and have
            # one overwrite the other.
            with open(candidate, "xb") as f:
                f.write(data)
            break
        except FileExistsError:
            n += 1
            candidate = day_dir / f"{stem}-{n}{suffix}"
    return str(candidate.resolve())
