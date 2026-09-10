import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

print("Checking installed packages...")
print("-" * 50)

modules = {
    "playwright": "Playwright",
    "PIL": "Pillow",
    "groq": "Groq",
    "tkinter": "Tkinter (GUI)"
}

all_ok = True
for module, name in modules.items():
    try:
        __import__(module)
        print(f"✓ {name:20} - INSTALLED")
    except ImportError:
        print(f"✗ {name:20} - NOT INSTALLED")
        all_ok = False

print("-" * 50)

if all_ok:
    print("\n✓ ALL PACKAGES INSTALLED!")
    print("\nTesting if app can start...")
    try:
        from src.app import run
        print("✓ App imports successfully!")
        print("\nYou can now run: RUN_APP.bat")
    except Exception as e:
        print(f"✗ App import failed: {e}")
        sys.exit(1)
else:
    print("\n✗ Some packages are missing")
    print("Run: python -m pip install playwright Pillow groq")
    print("Then: python -m playwright install chromium")
    sys.exit(1)
