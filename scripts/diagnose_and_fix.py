"""
FB Tool Automation - System Diagnostic and Fix Script
This script will check all requirements and install missing dependencies.
"""
import re
import sys
import subprocess
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The status glyphs are non-cp1252; a plain Windows console would otherwise
# crash on the first line of output.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def print_header(text):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)

def print_status(text, status="info"):
    icons = {"ok": "✓", "fail": "✗", "info": "ℹ", "warning": "⚠"}
    icon = icons.get(status, "•")
    print(f"{icon} {text}")

def check_python_version():
    print_header("Checking Python Version")
    version = sys.version_info
    print_status(f"Python {version.major}.{version.minor}.{version.micro}", "ok")
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print_status("Python 3.8 or higher is required!", "fail")
        return False
    return True

def check_module(module_name):
    """Check if a Python module is installed."""
    spec = importlib.util.find_spec(module_name)
    return spec is not None

def install_package(package):
    """Install a Python package using pip."""
    try:
        print_status(f"Installing {package}...", "info")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", package],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        return True
    except subprocess.CalledProcessError as e:
        print_status(f"Failed to install {package}", "fail")
        print(f"   Error: {e.stderr.decode() if e.stderr else 'Unknown error'}")
        return False

# Import name for each distribution in requirements.txt whose module name
# differs from the package name. requirements.txt is the single source of truth
# for what gets installed; this only maps it to what gets imported.
IMPORT_NAMES = {"Pillow": "PIL"}


def read_requirements():
    """(import_name, requirement_spec) for every line in requirements.txt."""
    reqs = []
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        dist = re.split(r"[<>=!~;\s\[]", line, 1)[0]
        reqs.append((IMPORT_NAMES.get(dist, dist), line))
    return reqs


def check_and_install_dependencies():
    print_header("Checking Required Packages")
    
    required = dict(read_requirements())
    required["tkinter"] = None  # Built-in, but we check it
    
    missing = []
    
    for module, package in required.items():
        if check_module(module):
            print_status(f"{module} - Already installed", "ok")
        else:
            if package:
                print_status(f"{module} - Not found", "warning")
                missing.append(package)
            else:
                print_status(f"{module} - Not found (tkinter should be built-in)", "fail")
                print_status("   Install tkinter: 'python -m pip install tk'", "info")
                return False
    
    if missing:
        print_header("Installing Missing Packages")
        for package in missing:
            if not install_package(package):
                return False
            print_status(f"{package} installed successfully", "ok")
    
    return True

def install_playwright_browsers():
    print_header("Installing Playwright Browsers")
    
    if not check_module("playwright"):
        print_status("Playwright not installed yet", "fail")
        return False
    
    try:
        print_status("Installing Chromium browser (this may take a few minutes)...", "info")
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print_status("Chromium browser installed successfully", "ok")
            return True
        else:
            print_status("Failed to install Chromium browser", "fail")
            print(f"   Error: {result.stderr}")
            return False
    except Exception as e:
        print_status(f"Failed to install playwright browsers: {e}", "fail")
        return False

def test_imports():
    print_header("Testing All Imports")
    
    test_modules = [
        ("playwright.async_api", "Playwright"),
        ("PIL", "Pillow (PIL)"),
        ("groq", "Groq"),
        ("tkinter", "Tkinter (GUI)"),
    ]
    
    all_ok = True
    for module, name in test_modules:
        try:
            __import__(module)
            print_status(f"{name} - Import successful", "ok")
        except ImportError as e:
            print_status(f"{name} - Import failed: {e}", "fail")
            all_ok = False
    
    return all_ok

def check_only() -> int:
    """Report what is installed and whether the app imports; change nothing."""
    print_header("FB TOOL AUTOMATION - Dependency Check")
    ok = check_python_version()
    for module, _spec in read_requirements() + [("tkinter", None)]:
        present = check_module(module)
        print_status(f"{module:12} - {'installed' if present else 'MISSING'}",
                     "ok" if present else "fail")
        ok = ok and present
    if ok:
        ok = test_imports()
    print_status("ready - run RUN_APP.bat" if ok else "not ready - run INSTALL.bat",
                 "ok" if ok else "fail")
    return 0 if ok else 1


def main():
    if "--check" in sys.argv[1:]:
        return check_only()

    print_header("FB TOOL AUTOMATION - System Diagnostic")
    print("This script will check and fix all dependencies\n")
    
    # Step 1: Check Python version
    if not check_python_version():
        print_status("\nPlease upgrade Python and try again", "fail")
        input("\nPress Enter to exit...")
        return 1
    
    # Step 2: Check and install dependencies
    if not check_and_install_dependencies():
        print_status("\nFailed to install required packages", "fail")
        input("\nPress Enter to exit...")
        return 1
    
    # Step 3: Install Playwright browsers
    if not install_playwright_browsers():
        print_status("\nFailed to install Playwright browsers", "fail")
        print_status("You may need to run: python -m playwright install chromium", "info")
        input("\nPress Enter to exit...")
        return 1
    
    # Step 4: Test all imports
    if not test_imports():
        print_status("\nSome imports failed", "fail")
        input("\nPress Enter to exit...")
        return 1
    
    # Success!
    print_header("✓ ALL CHECKS PASSED!")
    print("\nYour system is ready to run FB Tool Automation")
    print("You can now run: RUN_APP.bat\n")
    
    input("Press Enter to exit...")
    return 0

if __name__ == "__main__":
    sys.exit(main())
