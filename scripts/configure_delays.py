"""
Configure delay settings for Facebook sharing to avoid spam detection.

This script allows you to customize the delays between shares and actions
to make the automation appear more human-like and avoid Facebook's spam filters.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.storage import config_manager as cfg


def display_current_delays():
    """Display current delay settings."""
    share_delays = cfg.get_share_delays()
    comment_delays = cfg.get_comment_delays()
    
    print("\n" + "="*60)
    print("CURRENT DELAY SETTINGS")
    print("="*60)
    
    print("\n" + "-"*60)
    print("SHARING DELAYS")
    print("-"*60)
    print(f"\n1. Between Shares:")
    print(f"   Min: {share_delays['between_shares_min']} seconds")
    print(f"   Max: {share_delays['between_shares_max']} seconds")
    print(f"   (Random delay between each group share)")
    
    print(f"\n2. After Share Button:")
    print(f"   Min: {share_delays['after_share_button_min']} seconds")
    print(f"   Max: {share_delays['after_share_button_max']} seconds")
    print(f"   (Delay after clicking Share, before selecting 'Group')")
    
    print(f"\n3. After Posting:")
    print(f"   Min: {share_delays['after_post_min']} seconds")
    print(f"   Max: {share_delays['after_post_max']} seconds")
    print(f"   (Wait time after clicking Post button)")
    
    print("\n" + "-"*60)
    print("COMMENTING DELAYS")
    print("-"*60)
    print(f"\n4. Between Comments:")
    print(f"   Min: {comment_delays['between_comments_min']} seconds")
    print(f"   Max: {comment_delays['between_comments_max']} seconds")
    print(f"   (Random delay between each comment attempt)")
    
    print(f"\n5. After Navigation:")
    print(f"   Min: {comment_delays['after_navigation_min']} seconds")
    print(f"   Max: {comment_delays['after_navigation_max']} seconds")
    print(f"   (Delay after loading post page)")
    
    print(f"\n6. After Clicking Comment Box:")
    print(f"   Min: {comment_delays['after_clicking_box_min']} seconds")
    print(f"   Max: {comment_delays['after_clicking_box_max']} seconds")
    print(f"   (Wait after clicking comment button)")
    
    print(f"\n7. After Posting Comment:")
    print(f"   Min: {comment_delays['after_posting_min']} seconds")
    print(f"   Max: {comment_delays['after_posting_max']} seconds")
    print(f"   (Wait time after submitting comment)")
    
    print("\n" + "="*60 + "\n")


def configure_delays():
    """Interactive configuration of delay settings."""
    print("\n" + "="*60)
    print("CONFIGURE DELAY SETTINGS")
    print("="*60)
    print("\nThese delays help avoid Facebook spam detection by making")
    print("the automation appear more human-like.")
    print("\nPress Enter to keep current value, or enter a new number.")
    print("-"*60)
    
    share_current = cfg.get_share_delays()
    comment_current = cfg.get_comment_delays()
    new_share_delays = {}
    new_comment_delays = {}
    
    # SHARING DELAYS
    print("\n" + "="*60)
    print("SHARING DELAYS")
    print("="*60)
    
    # Between shares
    print("\n1. DELAY BETWEEN GROUP SHARES")
    print("   (How long to wait between sharing to each group)")
    val = input(f"   Minimum seconds [{share_current['between_shares_min']}]: ").strip()
    new_share_delays['between_shares_min'] = float(val) if val else share_current['between_shares_min']
    
    val = input(f"   Maximum seconds [{share_current['between_shares_max']}]: ").strip()
    new_share_delays['between_shares_max'] = float(val) if val else share_current['between_shares_max']
    
    # After share button
    print("\n2. DELAY AFTER CLICKING SHARE BUTTON")
    print("   (Wait before selecting 'Share to Group' option)")
    val = input(f"   Minimum seconds [{share_current['after_share_button_min']}]: ").strip()
    new_share_delays['after_share_button_min'] = float(val) if val else share_current['after_share_button_min']
    
    val = input(f"   Maximum seconds [{share_current['after_share_button_max']}]: ").strip()
    new_share_delays['after_share_button_max'] = float(val) if val else share_current['after_share_button_max']
    
    # After posting
    print("\n3. DELAY AFTER POSTING")
    print("   (Wait for post to complete before next action)")
    val = input(f"   Minimum seconds [{share_current['after_post_min']}]: ").strip()
    new_share_delays['after_post_min'] = float(val) if val else share_current['after_post_min']
    
    val = input(f"   Maximum seconds [{share_current['after_post_max']}]: ").strip()
    new_share_delays['after_post_max'] = float(val) if val else share_current['after_post_max']
    
    # COMMENTING DELAYS
    print("\n" + "="*60)
    print("COMMENTING DELAYS")
    print("="*60)
    
    # Between comments
    print("\n4. DELAY BETWEEN COMMENT ATTEMPTS")
    print("   (How long to wait between each comment)")
    val = input(f"   Minimum seconds [{comment_current['between_comments_min']}]: ").strip()
    new_comment_delays['between_comments_min'] = float(val) if val else comment_current['between_comments_min']
    
    val = input(f"   Maximum seconds [{comment_current['between_comments_max']}]: ").strip()
    new_comment_delays['between_comments_max'] = float(val) if val else comment_current['between_comments_max']
    
    # After navigation
    print("\n5. DELAY AFTER NAVIGATING TO POST")
    print("   (Wait for page to fully load)")
    val = input(f"   Minimum seconds [{comment_current['after_navigation_min']}]: ").strip()
    new_comment_delays['after_navigation_min'] = float(val) if val else comment_current['after_navigation_min']
    
    val = input(f"   Maximum seconds [{comment_current['after_navigation_max']}]: ").strip()
    new_comment_delays['after_navigation_max'] = float(val) if val else comment_current['after_navigation_max']
    
    # After clicking box
    print("\n6. DELAY AFTER CLICKING COMMENT BOX")
    print("   (Wait after clicking 'Leave a comment' button)")
    val = input(f"   Minimum seconds [{comment_current['after_clicking_box_min']}]: ").strip()
    new_comment_delays['after_clicking_box_min'] = float(val) if val else comment_current['after_clicking_box_min']
    
    val = input(f"   Maximum seconds [{comment_current['after_clicking_box_max']}]: ").strip()
    new_comment_delays['after_clicking_box_max'] = float(val) if val else comment_current['after_clicking_box_max']
    
    # After posting comment
    print("\n7. DELAY AFTER POSTING COMMENT")
    print("   (Wait for comment to submit)")
    val = input(f"   Minimum seconds [{comment_current['after_posting_min']}]: ").strip()
    new_comment_delays['after_posting_min'] = float(val) if val else comment_current['after_posting_min']
    
    val = input(f"   Maximum seconds [{comment_current['after_posting_max']}]: ").strip()
    new_comment_delays['after_posting_max'] = float(val) if val else comment_current['after_posting_max']
    
    # Validate and save
    print("\n" + "="*60)
    print("NEW DELAY SETTINGS:")
    print("="*60)
    print("\nSHARING:")
    print(f"  Between Shares: {new_share_delays['between_shares_min']}-{new_share_delays['between_shares_max']}s")
    print(f"  After Share Button: {new_share_delays['after_share_button_min']}-{new_share_delays['after_share_button_max']}s")
    print(f"  After Posting: {new_share_delays['after_post_min']}-{new_share_delays['after_post_max']}s")
    print("\nCOMMENTING:")
    print(f"  Between Comments: {new_comment_delays['between_comments_min']}-{new_comment_delays['between_comments_max']}s")
    print(f"  After Navigation: {new_comment_delays['after_navigation_min']}-{new_comment_delays['after_navigation_max']}s")
    print(f"  After Clicking Box: {new_comment_delays['after_clicking_box_min']}-{new_comment_delays['after_clicking_box_max']}s")
    print(f"  After Posting: {new_comment_delays['after_posting_min']}-{new_comment_delays['after_posting_max']}s")
    print("="*60)
    
    confirm = input("\nSave these settings? (y/n): ").strip().lower()
    if confirm == 'y':
        cfg.save_share_delays(new_share_delays)
        cfg.save_comment_delays(new_comment_delays)
        print("\n[OK] Settings saved successfully!")
        return True
    else:
        print("\n[X] Settings not saved.")
        return False


def reset_to_defaults():
    """Reset delay settings to defaults."""
    share_defaults = {
        "between_shares_min": 15,
        "between_shares_max": 45,
        "after_share_button_min": 2,
        "after_share_button_max": 5,
        "after_post_min": 8,
        "after_post_max": 15,
    }
    comment_defaults = {
        "between_comments_min": 10,
        "between_comments_max": 30,
        "after_navigation_min": 2,
        "after_navigation_max": 4,
        "after_clicking_box_min": 1,
        "after_clicking_box_max": 2,
        "after_posting_min": 3,
        "after_posting_max": 5,
    }
    cfg.save_share_delays(share_defaults)
    cfg.save_comment_delays(comment_defaults)
    print("\n[OK] Delay settings reset to defaults!")


def main():
    """Main menu for delay configuration."""
    while True:
        print("\n" + "="*60)
        print("FACEBOOK AUTOMATION - DELAY CONFIGURATION")
        print("="*60)
        print("\n1. View current delay settings")
        print("2. Configure delay settings")
        print("3. Reset to default settings")
        print("4. Exit")
        print("\n" + "="*60)
        
        choice = input("\nSelect option (1-4): ").strip()
        
        if choice == '1':
            display_current_delays()
        elif choice == '2':
            configure_delays()
        elif choice == '3':
            confirm = input("\nReset to defaults? (y/n): ").strip().lower()
            if confirm == 'y':
                reset_to_defaults()
        elif choice == '4':
            print("\nGoodbye!")
            break
        else:
            print("\n[X] Invalid option. Please choose 1-4.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nExiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)
