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

    def installed(self, package: str, user: int | None = None) -> bool:
        scope = f"--user {user} " if user is not None else ""
        listed = self.shell(f"pm list packages {scope}{package}")
        return any(line.strip() == f"package:{package}"
                   for line in listed.splitlines())

    def launch(self, package: str, user: int | None = None) -> None:
        if user is None:
            self.shell(
                f"monkey -p {package} -c android.intent.category.LAUNCHER 1",
                timeout=60)
            return
        # monkey rejects --user on this image ("args: [--user, 12, -p, ...]"),
        # so a clone is started by resolving its launcher component and asking
        # am to start that component as the given user.
        brief = self.shell(
            f"cmd package resolve-activity --brief --user {user} {package}")
        component = next((ln.strip() for ln in brief.splitlines()
                          if "/" in ln and ln.strip().startswith(package)), "")
        if not component:
            raise RuntimeError(
                f"no launcher activity for {package} as user {user}: "
                f"{brief.strip()[:160]}")
        self.shell(f"am start --user {user} -a android.intent.action.MAIN "
                   f"-c android.intent.category.LAUNCHER -n {component}",
                   timeout=60)

    def stop(self, package: str, user: int | None = None) -> None:
        scope = f"--user {user} " if user is not None else ""
        self.shell(f"am force-stop {scope}{package}")

    def clear_app_data(self, package: str, user: int | None = None) -> None:
        """Wipe an app back to first-run state.

        Facebook Lite keeps its session in app storage, so clearing it is the
        way back to the login form. It DESTROYS the session that is there -
        the caller decides, never this module.
        """
        scope = f"--user {user} " if user is not None else ""
        self.shell(f"pm clear {scope}{package}", timeout=120)

    # -- clones -----------------------------------------------------------
    #
    # LDPlayer's "App Clone" is a button in the host GUI: no package on the
    # device, and no ldconsole command, so it cannot be driven from here.
    # Android's own multi-user support can be, and gives the same thing -
    # each user has its own data directory, so one installed Facebook Lite
    # holds one SEPARATE session per user. The ceiling is the device's, not
    # ours: `pm get-max-users` reports 4 on this image, Owner included.

    def su(self, command: str, timeout: float = 60) -> str:
        """Run a command as root. Empty output when the device is not rooted."""
        return self.shell(f'su -c "{command}"', timeout=timeout)

    def rooted(self) -> bool:
        return "uid=0" in self.su("id")

    def raise_user_limit(self, wanted: int) -> int:
        """Lift Android's cap on how many users - i.e. clones - can exist.

        The cap is not a licence or a paid feature: UserManager reads it from
        the fw.max_users property, falling back to a build resource that
        happens to be 4 on this image. Root can set the property, and
        UserManager re-reads it per call, so it takes effect at once with no
        framework restart. Measured: `pm get-max-users` went 4 -> 32.

        Not persisted into /system/build.prop on purpose. Re-applying it on
        each run is one shell call and leaves the emulator image untouched, so
        nothing has to be undone later.

        Returns the cap actually in force afterwards.
        """
        if wanted > self.max_users():
            if not self.rooted():
                self.log("  cannot raise the clone limit: the device is not "
                         "rooted (LDPlayer: Settings > Other > Root)")
                return self.max_users()
            self.su(f"setprop fw.max_users {int(wanted)}")
        return self.max_users()

    def max_users(self) -> int:
        out = self.shell("pm get-max-users")
        m = re.search(r"(\d+)", out)
        return int(m.group(1)) if m else 1

    def users(self) -> list[tuple[int, str]]:
        """(id, name) for every Android user, Owner first."""
        found = []
        for line in self.shell("pm list users").splitlines():
            m = re.search(r"UserInfo\{(\d+):([^:]*):", line)
            if m:
                found.append((int(m.group(1)), m.group(2)))
        return found

    def create_user(self, name: str) -> int:
        """A new Android user, i.e. one more independent app session.

        Raises when the device is full rather than returning a user that does
        not exist - a caller that ploughs on would install into user -1 and
        report a login against a session nobody can open.
        """
        out = self.shell(f"pm create-user {name}", timeout=120)
        m = re.search(r"created user id (\d+)", out)
        if not m:
            raise RuntimeError(
                f"could not create user {name!r}: {out.strip()[:160]} "
                f"(max users on this device: {self.max_users()})")
        return int(m.group(1))

    def start_user(self, user: int) -> None:
        """Bring a user up so its packages resolve.

        A user created with pm create-user exists but is STOPPED, and a
        stopped user's components do not resolve: resolve-activity answers
        "No activity found" for an app that pm says is installed for it. Every
        clone therefore has to be started before it can be driven.
        """
        self.shell(f"am start-user {user}", timeout=120)

    def switch_user(self, user: int) -> None:
        """Bring a user to the FOREGROUND.

        This is not optional for a clone. `uiautomator dump`, `input tap` and
        `input text` all act on whatever user owns the display, so starting an
        app with `am start --user 12` while user 0 is in front drives nothing:
        the app runs, unseen, and the taps land in the wrong session - which
        on a login screen means typing one account's password into another
        account's form.
        """
        self.shell(f"am switch-user {user}", timeout=120)
        time.sleep(6)

    def current_user(self) -> int:
        out = self.shell("am get-current-user")
        m = re.search(r"(\d+)", out)
        return int(m.group(1)) if m else 0

    def remove_user(self, user: int) -> None:
        self.shell(f"pm remove-user {user}", timeout=120)

    def install_existing_for_user(self, package: str, user: int) -> None:
        """Give an already-installed app to another user.

        The APK is installed once and shared; only the data directory is per
        user. That is what makes this cheap enough to be worth doing at all -
        a full install per clone would not fit.
        """
        out = self.shell(f"pm install-existing --user {user} {package}",
                         timeout=180)
        if "installed for user" not in out.lower() and "success" not in out.lower():
            raise RuntimeError(
                f"could not give {package} to user {user}: {out.strip()[:160]}")
