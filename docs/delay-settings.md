# Anti-Spam Delay Settings

## Overview

This Facebook automation tool now includes **configurable delays** to help avoid Facebook's spam detection when sharing posts to multiple groups. By adding randomized delays between actions, the tool mimics human behavior more closely.

## Why Delays Are Important

Facebook monitors for automated behavior patterns, including:
- Sharing to many groups in rapid succession
- Identical timing between actions
- No variation in interaction patterns

Without proper delays, Facebook may:
- Flag your account for spam
- Temporarily block sharing functionality
- Reduce post visibility
- Require additional verification

## Delay Types

### 1. Between Shares (15-45 seconds default)
**What it does:** Adds a random delay between each group share

**Example:** When sharing to 10 groups, there will be a 15-45 second delay between each share

**Recommendation:** 
- For 5-10 groups: Keep default (15-45s)
- For 10-20 groups: Increase to 20-60s
- For 20+ groups: Increase to 30-90s

### 2. After Share Button (2-5 seconds default)
**What it does:** Waits after clicking the "Share" button before selecting "Share to Group"

**Example:** Click Share → Wait 2-5 seconds → Click "Share to a Group"

**Recommendation:** Keep default unless you experience issues

### 3. After Posting (8-15 seconds default)
**What it does:** Waits after clicking the "Post" button for the share to complete

**Example:** Click Post → Wait 8-15 seconds → Proceed to next action

**Recommendation:** 
- For reliable internet: Keep default (8-15s)
- For slow internet: Increase to 10-20s

## Configuration Methods

### Method 1: Using the Configuration Tool (Recommended)

1. Double-click **`CONFIGURE_DELAYS.bat`**
2. Select option 2 (Configure delay settings)
3. Enter new values or press Enter to keep current
4. Confirm to save

### Method 2: Using Python Script

```bash
python scripts/configure_delays.py
```

### Method 3: Manual Configuration

Edit your config file at: `C:\Users\YourName\.autoshare\config.json`

Add or modify the `share_delays` section:

```json
{
  "profiles": { ... },
  "share_delays": {
    "between_shares_min": 15,
    "between_shares_max": 45,
    "after_share_button_min": 2,
    "after_share_button_max": 5,
    "after_post_min": 8,
    "after_post_max": 15
  }
}
```

## Recommended Settings by Use Case

### Conservative (Safest - Lower Risk)
- **Use when:** Sharing to many groups (20+) or previously flagged for spam
- Between Shares: 30-90 seconds
- After Share Button: 3-7 seconds
- After Posting: 10-20 seconds

### Balanced (Default - Moderate Risk)
- **Use when:** Normal sharing to 10-20 groups
- Between Shares: 15-45 seconds (default)
- After Share Button: 2-5 seconds (default)
- After Posting: 8-15 seconds (default)

### Aggressive (Faster - Higher Risk)
- **Use when:** Testing or sharing to few groups (5-10)
- Between Shares: 10-20 seconds
- After Share Button: 1-3 seconds
- After Posting: 5-10 seconds

⚠️ **Warning:** Using very short delays increases spam detection risk!

## How Delays Work

All delays use **random values** within the specified range:

- If set to 15-45 seconds, each delay will be a random value (e.g., 23s, 38s, 19s, 41s...)
- This randomness makes the automation appear more human-like
- Facebook is less likely to detect patterns when timing varies

## Example Timing

**Sharing to 5 groups with default settings:**

```
[00:00] Share to Group 1 → Post (wait 8-15s)
[00:12] Wait before next share (15-45s)
[00:45] Share to Group 2 → Post (wait 8-15s)
[00:58] Wait before next share (15-45s)
[01:25] Share to Group 3 → Post (wait 8-15s)
[01:40] Wait before next share (15-45s)
[02:18] Share to Group 4 → Post (wait 8-15s)
[02:30] Wait before next share (15-45s)
[03:05] Share to Group 5 → Post (wait 8-15s)
[03:18] Complete
```

**Total time: ~3-4 minutes for 5 groups** (vs. <30 seconds without delays)

## Best Practices

1. **Start Conservative:** Use longer delays initially, then adjust if needed
2. **Monitor Results:** Check Facebook's response and adjust accordingly
3. **Vary Your Patterns:** Don't share at the exact same time every day
4. **Limit Daily Shares:** Even with delays, don't share hundreds of times per day
5. **Use Multiple Profiles:** Distribute shares across multiple accounts
6. **Take Breaks:** Don't run automation 24/7

## Troubleshooting

### Still Getting Spam Warnings?
- Increase all delays by 50-100%
- Reduce the number of groups per batch
- Spread shares across more time
- Use multiple profiles

### Sharing Too Slow?
- Decrease delays gradually
- Monitor for spam warnings
- Find your account's "sweet spot"

### "Group option not found" Errors?
- Increase "After Share Button" delay
- Increase "After Posting" delay
- Check internet connection speed

## Technical Details

### Where Delays Are Applied

1. **`src/core/facebook_automation.py`:**
   - After clicking Share button
   - After clicking Post button

2. **`src/core/driver_manager.py`:**
   - Between each group share in bulk operations
   - Applied across all profiles

### Configuration Storage

- Config file: `~/.autoshare/config.json`
- Loaded once and cached for performance
- Changes take effect immediately (no restart needed)

## Support

If you experience issues:
1. Try resetting to defaults (Option 3 in scripts/configure_delays.py)
2. Check the logs for timing information
3. Verify Facebook is not temporarily blocking your account
4. Consider taking a break from automation for 24-48 hours

---

**Remember:** The goal is to appear human-like, not just fast. Quality over quantity!
