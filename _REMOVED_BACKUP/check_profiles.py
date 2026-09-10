import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(encoding='utf-8')
from src.storage import config_manager as cfg

profiles = cfg.list_profiles()
print(f"Total profiles: {len(profiles)}")
print(f"Type: {type(profiles[0]) if profiles else 'N/A'}")
for i, p in enumerate(profiles):
    print(f"  [{i+1}] {repr(p)}")
