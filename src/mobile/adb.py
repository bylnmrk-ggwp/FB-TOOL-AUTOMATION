"""Drive one Android screen over adb.

The browser fleet cannot use what this produces: Facebook Lite keeps its
session in app-private storage, not as the c_user/xs cookies every browser
path here reads (state_cache.py, login_accounts.py). This is a separate
capability - accounts that work inside Facebook Lite - and nothing in the
Brave automation consumes it.

There is no Appium and no Java on this machine, and installing them to press
two text fields would be a poor trade. adb already ships with LDPlayer and
already exposes everything a login needs: `uiautomator dump` gives the whole
screen as XML, `input tap` presses a point, `input text` types. This wraps
exactly that and nothing more.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

# LDPlayer ships its own adb, version-matched to the Android it runs. The one
# on PATH (if any) may speak a different protocol version and will restart the
# server out from under it, which shows up as devices vanishing mid-run.
LDPLAYER_DIRS = (Path(r"C:\LDPlayer\LDPlayer9"), Path(r"C:\LDPlayer\LDPlayer14"))
DEFAULT_SERIAL = "127.0.0.1:5555"

# Git Bash rewrites any argument that looks like a POSIX path: "/sdcard/x.xml"
# arrives inside the emulator as "C:/Program Files/Git/sdcard/x.xml", and the
# dump lands somewhere nothing can read it. Every adb call here therefore runs
# with MSYS path translation switched off rather than relying on the caller to
# remember.
_NO_PATH_CONV = {"MSYS_NO_PATHCONV": "1", "MSYS2_ARG_CONV_EXCL": "*"}


def adb_path() -> str:
    """LDPlayer's own adb.exe, or whatever is on PATH as a last resort."""
    for d in LDPLAYER_DIRS:
        exe = d / "adb.exe"
        if exe.exists():
            return str(exe)
    return "adb"


@dataclass(frozen=True)
class Node:
    """One element of the screen, as uiautomator reports it."""
    text: str
    resource_id: str
    cls: str
    desc: str
    bounds: tuple[int, int, int, int]      # left, top, right, bottom
    password: bool

    @property
    def centre(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return (left + right) // 2, (top + bottom) // 2


_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def parse_screen(xml: str) -> list[Node]:
    """Every element in a uiautomator dump, flattened.

    Kept a free function, not a method: it is the only part of this module
    that can be tested without an emulator, and the proof does exactly that.
    A malformed dump returns nothing rather than raising - uiautomator
    occasionally writes a truncated file when the screen changes mid-dump, and
    a retry is the right answer to that, not a traceback.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    out: list[Node] = []
    for el in root.iter("node"):
        m = _BOUNDS.fullmatch(el.get("bounds", ""))
        if not m:
            continue
        out.append(Node(
            text=el.get("text", ""),
            resource_id=el.get("resource-id", ""),
            cls=el.get("class", ""),
            desc=el.get("content-desc", ""),
            bounds=tuple(int(g) for g in m.groups()),  # type: ignore[arg-type]
            password=el.get("password", "false") == "true",
        ))
    return out


def find(nodes: list[Node], *, text: str | None = None,
         resource_id: str | None = None, cls: str | None = None,
         desc: str | None = None, password: bool | None = None) -> list[Node]:
    """The nodes matching every condition given.

    Substring and case-insensitive on the text fields, because Facebook Lite
    localises its labels and pads them; exact on resource ids and class names,
    which are not user-facing and must not match by accident.
    """
    def hit(n: Node) -> bool:
        if text is not None and text.lower() not in n.text.lower():
            return False
        if desc is not None and desc.lower() not in n.desc.lower():
            return False
        if resource_id is not None and n.resource_id != resource_id:
            return False
        if cls is not None and n.cls != cls:
            return False
        if password is not None and n.password is not password:
            return False
        return True
    return [n for n in nodes if hit(n)]


class Device:
    """One connected Android instance."""

    def __init__(self, serial: str = DEFAULT_SERIAL, log=print):
        self.serial = serial
        self.log = log
        self._adb = adb_path()

    # -- plumbing ---------------------------------------------------------

    def _run(self, *args: str, timeout: float = 60) -> str:
        # Bytes, not text=True. A uiautomator dump is UTF-8 and carries
        # whatever is on screen; decoding it with the console's locale codec
        # (cp1252 here) raises UnicodeDecodeError, and subprocess then hands
        # back stdout=None, so the failure surfaces as a baffling
        # AttributeError three frames away instead of as a decoding problem.
        env = {**os.environ, **_NO_PATH_CONV}
        proc = subprocess.run([self._adb, "-s", self.serial, *args],
                              capture_output=True, timeout=timeout, env=env)
        out = (proc.stdout or b"").decode("utf-8", errors="replace")
        err = (proc.stderr or b"").decode("utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(
                f"adb {' '.join(args)} failed: {(err or out).strip()[:200]}")
        return out.replace("\r\n", "\n")

    def shell(self, command: str, timeout: float = 60) -> str:
        return self._run("shell", command, timeout=timeout)

    def connect(self, timeout: float = 120) -> None:
        """Attach to the instance and wait for Android to finish booting.

        Connecting is not enough: adb reports a device the moment adbd
        answers, which is well before the launcher exists, and a dump taken in
        that window is empty.
        """
        env = {**os.environ, **_NO_PATH_CONV}
        subprocess.run([self._adb, "connect", self.serial],
                       capture_output=True, text=True, timeout=30, env=env)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.shell("getprop sys.boot_completed", timeout=10).strip() == "1":
                    return
            except Exception:
                pass
            time.sleep(2)
        raise RuntimeError(f"{self.serial} did not finish booting in {timeout}s")

    # -- screen -----------------------------------------------------------

    def screen(self, attempts: int = 3) -> list[Node]:
        """The current screen. Retries: a dump taken while the screen is
        still animating comes back truncated or empty."""
        for attempt in range(1, attempts + 1):
            try:
                self.shell("uiautomator dump /sdcard/_screen.xml", timeout=30)
                nodes = parse_screen(self.shell("cat /sdcard/_screen.xml", timeout=30))
                if nodes:
                    return nodes
            except Exception as e:  # noqa: BLE001 - a retry is the right answer
                if attempt == attempts:
                    raise
                self.log(f"  screen dump failed ({type(e).__name__}), retrying")
            time.sleep(1.5)
        return []

    def wait_for(self, timeout: float = 30, **criteria) -> Node | None:
        """The first node matching, or None once the deadline passes."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            hits = find(self.screen(), **criteria)
            if hits:
                return hits[0]
            time.sleep(1)
        return None

    # -- input ------------------------------------------------------------

    def tap(self, x: int, y: int) -> None:
        self.shell(f"input tap {int(x)} {int(y)}")

    def tap_node(self, node: Node) -> None:
        x, y = node.centre
        self.tap(x, y)

    # What `input text` can carry through a shell argument without ambiguity.
    # Space is sent as %s, which the tool decodes back to a space. A literal
    # '%' has no such escape - "%%" is not defined by `input`, and whether it
    # arrives as one '%' or two is a property of the Android build, not
    # something worth guessing with somebody's password.
    _TYPEABLE = re.compile(r"^[A-Za-z0-9 _\-.@+/:,()\[\]?!=]*$")

    def can_type(self, value: str) -> bool:
        """Whether type_text can send this exactly."""
        return bool(self._TYPEABLE.fullmatch(value))

    def type_text(self, value: str) -> None:
        """Type into whatever holds focus.

        Refuses rather than guesses. `input text` goes through a shell
        argument, so a value holding a quote, a backslash or a '%' can arrive
        mangled, doubled or truncated - and a password typed WRONG is worse
        than one not typed at all: the account is charged a failed login
        attempt for a mistake this side made, and the operator is told the
        password is bad. The caller gets an error it can report instead.
        """
        if not self.can_type(value):
            bad = sorted({c for c in value if not self._TYPEABLE.fullmatch(c)})
            raise ValueError(
                "adb `input text` cannot send these characters reliably: "
                f"{''.join(bad)!r} - type this account in by hand")
        self.shell(f'input text "{value.replace(" ", "%s")}"')

    def key(self, keycode: str) -> None:
        self.shell(f"input keyevent {keycode}")

    def clear_field(self) -> None:
        """Empty the focused field: select all, then delete."""
        self.key("KEYCODE_MOVE_END")
        for _ in range(64):
            self.key("KEYCODE_DEL")

    # -- apps -------------------------------------------------------------

    def installed(self, package: str) -> bool:
        listed = self.shell(f"pm list packages {package}")
        return any(line.strip() == f"package:{package}"
                   for line in listed.splitlines())

    def launch(self, package: str) -> None:
        self.shell(f"monkey -p {package} -c android.intent.category.LAUNCHER 1",
                   timeout=60)

    def stop(self, package: str) -> None:
        self.shell(f"am force-stop {package}")

    def clear_app_data(self, package: str) -> None:
        """Wipe an app back to first-run state.

        This is how one device logs a SECOND account in: Facebook Lite keeps
        its session in app storage, so clearing it is the only way back to the
        login form without the account switcher. It destroys the session that
        is there - the caller decides, never this module.
        """
        self.shell(f"pm clear {package}", timeout=120)
