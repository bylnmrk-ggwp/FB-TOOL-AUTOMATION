"""
Simple friendship status checker - reads the autoshare database directly
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the database helpers directly
from src.storage import config_manager as cfg
from src.storage.database import are_friends

def main():
    print("\n" + "="*80)
    print("FRIENDSHIP STATUS CHECKER")
    print("="*80 + "\n")
    print("Initializing...")
    
    profiles = cfg.list_profiles()
    
    if not profiles:
        print("❌ No profiles found!")
        return
    
    print(f"Found {len(profiles)} profiles\n")
    
    # Calculate stats
    total_possible = len(profiles) * (len(profiles) - 1) // 2
    actual_friendships = 0
    friendship_matrix = {}
    
    print("Checking friendships...\n")
    
    # Check each pair
    for profile1 in profiles:
        friendship_matrix[profile1] = {}
        friends_count = 0
        
        for profile2 in profiles:
            if profile1 == profile2:
                friendship_matrix[profile1][profile2] = None
            else:
                is_friend = are_friends(profile1, profile2)
                friendship_matrix[profile1][profile2] = is_friend
                if is_friend:
                    friends_count += 1
                    # Count each friendship once
                    if profile1 < profile2:
                        actual_friendships += 1
        
        # Show progress
        max_friends = len(profiles) - 1
        status = "✅" if friends_count == max_friends else ("🟡" if friends_count >= max_friends * 0.7 else "❌")
        print(f"{status} {profile1}: {friends_count}/{max_friends} friends")
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Total Profiles: {len(profiles)}")
    print(f"Possible Friendships: {total_possible}")
    print(f"Actual Friendships: {actual_friendships}")
    
    if total_possible > 0:
        percentage = (actual_friendships * 100) // total_possible
        print(f"Completion: {percentage}%")
        
        if percentage == 100:
            print(f"\n🎉 ALL PROFILES ARE FRIENDS WITH EACH OTHER!")
            print("   Complete friendship network achieved! ✨")
        else:
            missing = total_possible - actual_friendships
            print(f"\n⚠️  {missing} friendships still missing!")
            print(f"💡 TIP: Run 'Accept All Pending Friend Requests' in the app")
    
    print(f"\n{'='*80}\n")
    
    # Detailed missing friendships
    if actual_friendships < total_possible:
        print("MISSING FRIENDSHIPS:\n")
        for profile1 in profiles:
            missing = [p2 for p2 in profiles if p2 != profile1 and not friendship_matrix[profile1][p2]]
            if missing:
                print(f"❌ {profile1}")
                print(f"   Not friends with ({len(missing)}): {', '.join(missing[:5])}")
                if len(missing) > 5:
                    print(f"   ... and {len(missing) - 5} more")
                print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    input("\nPress Enter to exit...")
