"""
Check friendship status between all Facebook profiles.
Shows a matrix of which profiles are friends with each other.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(encoding='utf-8')

from src.storage import config_manager as cfg
from src.storage.database import are_friends, get_friend_count_for_profile


def main():
    profiles = cfg.list_profiles()
    
    if not profiles:
        print("❌ No profiles found in database!")
        return
    
    print(f"\n{'='*80}")
    print(f"FRIENDSHIP STATUS CHECK - {len(profiles)} PROFILES")
    print(f"{'='*80}\n")
    
    # Count total possible friendships (n * (n-1) / 2)
    total_possible = len(profiles) * (len(profiles) - 1) // 2
    actual_friendships = 0
    
    # Build friendship matrix
    print("Building friendship matrix...\n")
    friendship_data = {}
    
    for profile1 in profiles:
        friendship_data[profile1] = {}
        for profile2 in profiles:
            if profile1 == profile2:
                friendship_data[profile1][profile2] = None  # Self
            else:
                is_friend = are_friends(profile1, profile2)
                friendship_data[profile1][profile2] = is_friend
                # Count each friendship once (when profile1 < profile2 alphabetically)
                if is_friend and profile1 < profile2:
                    actual_friendships += 1
    
    # Print summary
    print(f"📊 SUMMARY")
    print(f"   Total Profiles: {len(profiles)}")
    print(f"   Possible Friendships: {total_possible}")
    print(f"   Actual Friendships: {actual_friendships}")
    
    if total_possible > 0:
        percentage = (actual_friendships * 100) // total_possible
        print(f"   Completion: {actual_friendships}/{total_possible} ({percentage}%)")
    else:
        print(f"   Completion: N/A")
    print()
    
    # Show individual friend counts
    print(f"\n{'='*80}")
    print("INDIVIDUAL FRIEND COUNTS")
    print(f"{'='*80}\n")
    
    for profile in profiles:
        friend_count = get_friend_count_for_profile(profile)
        max_friends = len(profiles) - 1
        percentage = (friend_count * 100 // max_friends) if max_friends > 0 else 0
        
        if friend_count == max_friends:
            status = "✅"
        elif friend_count >= max_friends * 0.7:
            status = "🟡"
        else:
            status = "❌"
        
        print(f"{status} {profile}: {friend_count}/{max_friends} friends ({percentage}%)")
    
    # Print matrix
    print(f"\n{'='*80}")
    print("FRIENDSHIP MATRIX")
    print(f"{'='*80}")
    print("✅ = Friends  |  ❌ = Not Friends  |  -- = Self\n")
    
    # Print profile list with numbers
    print("Profile List:")
    for idx, profile in enumerate(profiles, 1):
        print(f"  {idx:2d}. {profile}")
    print()
    
    # Print matrix grid
    print("    ", end="")
    for idx in range(1, len(profiles) + 1):
        print(f"{idx:3d}", end="")
    print()
    print("    " + "-" * (len(profiles) * 3))
    
    for idx1, profile1 in enumerate(profiles, 1):
        print(f"{idx1:2d} |", end="")
        for profile2 in profiles:
            status = friendship_data[profile1][profile2]
            if status is None:
                print(" --", end="")
            elif status:
                print(" ✅", end="")
            else:
                print(" ❌", end="")
        # Show profile name (truncated if too long)
        name_display = profile1 if len(profile1) <= 25 else profile1[:22] + "..."
        print(f"  | {name_display}")
    
    print()
    
    # Find profiles with missing friendships
    print(f"\n{'='*80}")
    print("MISSING FRIENDSHIPS")
    print(f"{'='*80}\n")
    
    has_missing = False
    for profile1 in profiles:
        missing = []
        for profile2 in profiles:
            if profile1 != profile2 and not friendship_data[profile1][profile2]:
                missing.append(profile2)
        
        if missing:
            has_missing = True
            print(f"❌ {profile1}")
            print(f"   Not friends with ({len(missing)}): {', '.join(missing)}")
            print()
    
    if not has_missing:
        print("🎉 ALL PROFILES ARE FRIENDS WITH EACH OTHER!")
        print("   Complete friendship network achieved! ✨")
    else:
        missing_count = total_possible - actual_friendships
        print(f"\n⚠️  {missing_count} friendships still missing!")
        print(f"💡 TIP: Run 'Accept All Pending Friend Requests' to complete friendships")
    
    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    input("\nPress Enter to exit...")

