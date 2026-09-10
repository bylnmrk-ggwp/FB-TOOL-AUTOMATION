import subprocess
import sys

print("=" * 60)
print("Installing Required Dependencies")
print("=" * 60)

packages = [
    "playwright>=1.45.0",
    "Pillow>=10.0.0", 
    "groq>=0.4.0"
]

for package in packages:
    print(f"\nInstalling {package}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print(f"✓ {package} installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install {package}: {e}")
        sys.exit(1)

print("\n" + "=" * 60)
print("Installing Playwright Browsers")
print("=" * 60)

try:
    subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
    print("✓ Playwright chromium browser installed successfully")
except subprocess.CalledProcessError as e:
    print(f"✗ Failed to install playwright browsers: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✓ ALL DEPENDENCIES INSTALLED SUCCESSFULLY!")
print("=" * 60)
print("\nYou can now run: RUN_APP.bat")
input("\nPress Enter to exit...")
