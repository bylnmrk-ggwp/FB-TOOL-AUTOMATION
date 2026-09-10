"""
Quick friendship status check - minimal dependencies
Directly queries the database file
"""
import os
from pathlib import Path

# Find the database
db_path = Path.home() / ".autoshare" / "autoshare.db"

if not db_path.exists():
    print(f"❌ Database not found at: {db_path}")
    print("   Make sure you've run the app at least once!")
    input("\nPress Enter to exit...")
    exit(1)

print(f"\n{'='*80}")
print(f"FRIENDSHIP STATUS CHECK")
print(f"{'='*80}\n")
print(f"Database: {db_path}\n")

# Try to import sqlite3 - if not available, show manual instructions
try:
    import sqlite3
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Get all unique profile names from friend_relationships
    cursor.execute("""
        SELECT DISTINCT profile_a FROM friend_relationships
        UNION
        SELECT DISTINCT profile_b FROM friend_relationships
        ORDER BY 1
    """)
    
    profiles = [row[0] for row in cursor.fetchall()]
    
    if not profiles:
        print("ℹ️  No friendship data found in database yet.")
        print("   Profiles need to send and accept friend requests first.")
        conn.close()
        input("\nPress Enter to exit...")
        exit(0)
    
    print(f"Found {len(profiles)} profiles with friendship data:\n")
    
    # Calculate friendships
    total_possible = len(profiles) * (len(profiles) - 1) // 2
    
    cursor.execute("SELECT COUNT(*) FROM friend_relationships WHERE status='friends'")
    actual_friendships = cursor.fetchone()[0]
    
    # Show each profile's friend count
    for profile in profiles:
        cursor.execute("""
            SELECT COUNT(*) FROM friend_relationships 
            WHERE (profile_a=? OR profile_b=?) AND status='friends'
        """, (profile, profile))
        friend_count = cursor.fetchone()[0]
        max_friends = len(profiles) - 1
        
        if friend_count == max_friends:
            status = "✅"
        elif friend_count >= max_friends * 0.7:
            status = "🟡"
        else:
            status = "❌"
        
        print(f"{status} {profile}: {friend_count}/{max_friends} friends")
    
    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY")
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
            print(f"💡 NEXT STEP: Click 'Accept All Pending Friend Requests' in the app")
    
    # Show pending requests
    cursor.execute("SELECT COUNT(*) FROM friend_relationships WHERE status='pending'")
    pending = cursor.fetchone()[0]
    
    if pending > 0:
        print(f"\n📬 {pending} pending friend requests waiting to be accepted")
    
    print(f"\n{'='*80}\n")
    
    conn.close()

except ImportError:
    print("❌ sqlite3 module not available in your Python installation")
    print(f"\nTo check friendships manually:")
    print(f"1. Open the database file in a SQLite browser:")
    print(f"   {db_path}")
    print(f"2. Run this query:")
    print(f"""
    SELECT 
        profile_a,
        profile_b, 
        status,
        sent_by,
        accepted_at/
    FROM friend_relationships
    ORDER BY status, profile_a;
    """)

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

input("\nPress Enter to exit...")
