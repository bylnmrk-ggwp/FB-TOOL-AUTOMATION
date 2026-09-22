"""Proof: the web/ PWA installs and builds. Run by verify.py with globals
failures, step and ROOT.

Skipped with a printed notice when npm is absent, so a machine that only
runs the Python side still gets ALL PROOFS PASS. With npm present this is
the same command BUILD_WEB.bat runs (npm ci + npm run build), so a build
that passes here is the build server.py serves. Output is captured and
only the tail is printed on failure: the console is cp1252 and npm/vite
print non-ASCII progress glyphs."""
import shutil
import subprocess
import sys
sys.path.insert(0, str(ROOT))

step("web build")
_WEB = ROOT / "web"
_npm = shutil.which("npm")
if _npm is None:
    print("SKIP: node not installed")
else:
    _install = "ci" if (_WEB / "package-lock.json").exists() else "install"
    _log = ""
    try:
        for _args in ([_npm, _install], [_npm, "run", "build"]):
            _proc = subprocess.run(_args, cwd=_WEB, check=True, timeout=600,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            _log = _proc.stdout.decode("utf-8", errors="replace")
        for _name in ("index.html", "manifest.webmanifest", "sw.js"):
            if not (_WEB / "dist" / _name).exists():
                failures.append(f"web/dist/{_name} missing after npm run build")
    except subprocess.CalledProcessError as _e:
        _log = (_e.stdout or b"").decode("utf-8", errors="replace")
        failures.append(f"web build: {' '.join(_a for _a in _e.cmd[1:])} exited {_e.returncode}")
    except (subprocess.TimeoutExpired, OSError) as _e:
        failures.append(f"web build: {_e}")
    _web_fails = [f for f in failures if f.startswith("web")]
    if _web_fails:
        for _line in _log.splitlines()[-20:]:
            print("  " + _line.encode("ascii", errors="replace").decode("ascii"))
        print("FAILED")
    else:
        print(f"ok (npm {_install}, npm run build, dist/index.html + manifest + sw.js)")
