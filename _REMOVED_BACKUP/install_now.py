import subprocess
import sys

print("=" * 70)
print("INSTALLING REQUIRED PACKAGES")
print("=" * 70)

packages = [
    ("playwright", "playwright>=1.45.0"),
    ("Pillow", "Pillow>=10.0.0"),
    ("groq", "groq>=0.4.0"),
]

print("\n[1/4] Upgrading pip...")
try:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    print("OK - pip upgraded\n")
except Exception as e:
    print(f"WARN - pip upgrade failed: {e}\n")

print("[2/4] Installing Python packages...")
for name, package in packages:
    print(f"  Installing {name}...", end=" ", flush=True)
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", package],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("OK")
    except Exception as e:
        print(f"FAILED - {e}")
        sys.exit(1)

print("\n[3/4] Installing Playwright browsers (this may take 2-3 minutes)...")
try:
    subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
    print("OK - Chromium browser installed\n")
except Exception as e:
    print(f"FAILED - {e}\n")
    sys.exit(1)

print("[4/4] Testing imports...")
test_imports = ["playwright.async_api", "PIL", "groq", "tkinter"]
for module in test_imports:
    try:
        __import__(module)
        print(f"  {module} - OK")
    except ImportError as e:
        print(f"  {module} - FAILED: {e}")
        sys.exit(1)

print("\n" + "=" * 70)
print("SUCCESS! All dependencies installed.")
print("=" * 70)
print("\nYou can now run: RUN_APP.bat")
