#!/usr/bin/env python3
"""
AutoShare CLI — Run Facebook automation tasks from the terminal.

Usage:
    python cli.py list-profiles
    python cli.py launch-profile <name>
    python cli.py share <post_url> <group_name> [options]
    python cli.py share-timeline <post_url> [options]
    python cli.py comment <post_url> --text "..." [--profile NAME]
    python cli.py login <email> <password>
    python cli.py batch <file.json>

Options for share/share-timeline:
    --profile NAME         Profile to use (default: first saved profile)
    --comment TEXT         Comment to post
    --reaction TYPE        Reaction: like, love, care, haha, wow, sad, angry

Examples:
    python cli.py list-profiles
    python cli.py launch-profile MyProfile
    python cli.py share "https://facebook.com/post/123" "My Group" --profile MyProfile --reaction like
    python cli.py login user@email.com mypassword
    python cli.py batch queue_items.json
"""

import argparse
import asyncio
import json
import random
import sys
import os

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Every line this prints carries a status emoji, and a Windows console is
# cp1252 by default: without this the first "OK" raises UnicodeEncodeError and
# the traceback's own error print raises it again, burying the real result.
# The other scripts in scripts/ all do this; cli.py was the one that did not.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from src.core.facebook_automation import FacebookAutomation
from src.storage import config_manager as cfg


# ── Helpers ──────────────────────────────────────────────────────────

def _log(msg: str):
    """Simple terminal logger."""
    print(f"  {msg}")


async def _ensure_profile(automation: FacebookAutomation, profile_name: str | None, auto_launch: bool = True):
    """Resolve a profile name to its Brave path, optionally launching the browser.
    
    If profile_name is None, picks the first available profile.
    Returns (profile_name, brave_path) or raises SystemExit.
    """
    profiles = cfg.list_profiles()
    if not profiles:
        print("❌ No saved profiles found. Add one using the GUI app (python main.py).")
        sys.exit(1)

    if profile_name is None:
        profile_name = profiles[0]
        print(f"  Using profile: '{profile_name}'")

    if profile_name not in profiles:
        print(f"❌ Profile '{profile_name}' not found. Available: {', '.join(profiles)}")
        sys.exit(1)

    brave_path = cfg.get_profile_path(profile_name)
    if not brave_path:
        print(f"❌ Profile '{profile_name}' has no Brave profile path. Re-add it in the GUI.")
        sys.exit(1)

    if auto_launch:
        print(f"  Launching profile '{profile_name}'...")
        await automation.start_browser(brave_path)
        await automation.go_to_facebook()

        logged_in = await automation._is_logged_in(timeout=15)
        if logged_in:
            print(f"  ✅ Logged in as '{profile_name}'")
        else:
            print(f"  ⚠️  Profile '{profile_name}' is not logged in to Facebook.")
            print("  Launch the GUI app and log in manually, or use the 'login' command.")

    return profile_name, brave_path


# ── Command handlers ─────────────────────────────────────────────────

async def cmd_list_profiles(args):
    """List all saved profiles."""
    profiles = cfg.list_profiles()
    if not profiles:
        print("  No saved profiles.")
        print("  Add one using the GUI app (python main.py) — pick a Brave profile, give it a name.")
        return

    print(f"  Saved profiles ({len(profiles)}):")
    for p in profiles:
        path = cfg.get_profile_path(p)
        print(f"    • {p}  ({path})")


async def cmd_launch_profile(args):
    """Launch a profile browser that navigates to Facebook."""
    auto = FacebookAutomation(log_callback=_log)
    try:
        profile_name, _ = await _ensure_profile(auto, args.name, auto_launch=True)

        print(f"\n  🚀 Browser opened for '{profile_name}' at https://www.facebook.com/")
        print("  The browser will remain open until you close it.")
        print("  Press Ctrl+C in this terminal to close the browser.\n")

        # Wait until user closes the browser or presses Ctrl+C
        while True:
            try:
                pages = auto.context.pages
                if len(pages) == 0:
                    print("  Browser window closed. Exiting.")
                    break
                await asyncio.sleep(0.5)
            except Exception:
                print("  Browser disconnected. Exiting.")
                break

    except KeyboardInterrupt:
        print("\n  Closing browser...")
    finally:
        await auto.quit()


async def cmd_share(args):
    """Share a post to a Facebook group."""
    auto = FacebookAutomation(log_callback=_log, debug=getattr(args, 'debug', False))
    try:
        profile_name, _ = await _ensure_profile(auto, args.profile, auto_launch=True)

        logged_in = await auto._is_logged_in(timeout=15)
        if not logged_in:
            print("❌ Not logged in. Please log in to Facebook first.")
            print("   Use: python cli.py login <email> <password>")
            await auto.quit()
            return

        ok, msg = await auto.share_post_to_group(
            args.post_url,
            args.group_name,
            comment_text=args.comment,
            reaction=args.reaction,
        )

        if ok:
            print(f"  ✅ {msg}")
        else:
            print(f"  ❌ {msg}")

        await auto.cleanup()

    except KeyboardInterrupt:
        print("\n  Interrupted. Closing browser...")
        await auto.quit()
    except Exception as e:
        print(f"  ❌ Error: {e}")
        await auto.quit()


async def cmd_share_timeline(args):
    """Share a post to the user's Facebook Timeline."""
    auto = FacebookAutomation(log_callback=_log, debug=getattr(args, 'debug', False))
    try:
        profile_name, _ = await _ensure_profile(auto, args.profile, auto_launch=True)

        logged_in = await auto._is_logged_in(timeout=15)
        if not logged_in:
            print("❌ Not logged in. Please log in to Facebook first.")
            print("   Use: python cli.py login <email> <password>")
            await auto.quit()
            return

        ok, msg = await auto.share_post_to_timeline(
            args.post_url,
            comment_text=args.comment,
            reaction=args.reaction,
        )

        if ok:
            print(f"  ✅ {msg}")
        else:
            print(f"  ❌ {msg}")

        await auto.cleanup()

    except KeyboardInterrupt:
        print("\n  Interrupted. Closing browser...")
        await auto.quit()
    except Exception as e:
        print(f"  ❌ Error: {e}")
        await auto.quit()


async def cmd_comment(args):
    """Post a comment on one post, without sharing it anywhere.

    The queue has commented on a post since it grew an action_type of
    "comment", but only through the app: the CLI could reach the same
    automation for a group share and a timeline share and not for a plain
    comment, so testing one meant starting the server. This is that gap,
    over the same _auto_comment() the queue runs.

    Several lines in --text means one of them is chosen at random, which is
    what the automation does with a multi-line comment everywhere else.
    """
    auto = FacebookAutomation(log_callback=_log, debug=getattr(args, "debug", False))
    try:
        profile_name, _ = await _ensure_profile(auto, args.profile, auto_launch=True)

        logged_in = await auto._is_logged_in(timeout=15)
        if not logged_in:
            print(f"  \u274c Profile '{profile_name}' is not logged in to Facebook.")
            print("   Log it in first: python scripts/login_accounts.py --only <username>")
            await auto.quit()
            return

        ok = await auto._auto_comment(args.post_url, args.text)
        if ok:
            print(f"  \u2705 {profile_name}: comment posted")
        else:
            reason = getattr(auto, "last_comment_error", "") or "Failed to comment"
            print(f"  \u274c {profile_name}: {reason}")

        await auto.cleanup()

    except KeyboardInterrupt:
        print("\n  Interrupted. Closing browser...")
        await auto.quit()
    except Exception as e:
        print(f"  \u274c Error: {e}")
        await auto.quit()


async def cmd_login(args):
    """Login with email and password, handling 2FA if needed."""
    auto = FacebookAutomation(log_callback=_log)
    try:
        import tempfile
        import time

        # Use a temp profile for credential login
        attempt_id = str(int(time.time()))
        tmp_profile = os.path.join(tempfile.gettempdir(), f"autoshare_cred_{attempt_id}")
        os.makedirs(tmp_profile, exist_ok=True)

        print(f"  Starting browser for login as '{args.email}'...")
        await auto.start_browser(tmp_profile)
        await auto.go_to_facebook()

        ok, msg = await auto.login_with_credentials(args.email, args.password)

        if ok:
            print(f"  ✅ {msg}")
        else:
            print(f"  ❌ {msg}")

        # Keep browser open if 2FA is needed
        if "2FA" in msg or "checkpoint" in msg.lower():
            print("\n  Complete 2FA in the browser window, then close it.")
            print("  Press Ctrl+C to abort.\n")
            try:
                while True:
                    pages = auto.context.pages
                    if len(pages) == 0:
                        break
                    await asyncio.sleep(0.5)
            except KeyboardInterrupt:
                pass
            except Exception:
                pass

        await auto.quit()

    except Exception as e:
        print(f"  ❌ Login error: {e}")
        try:
            await auto.quit()
        except Exception:
            pass


async def cmd_batch(args):
    """Run a batch queue from a JSON file.

    Expected JSON format (list of items):
    [
        {
            "profile_name": "MyProfile",
            "post_url": "https://facebook.com/post/123",
            "group_name": "My Group",        // for group shares
            "action_type": "group|timeline|comment",  // default: "group"
            "comment_text": "optional comment",
            "reaction": "like|love|etc"
        }
    ]
    """
    # Load JSON
    try:
        with open(args.file, "r") as f:
            items = json.load(f)
    except Exception as e:
        print(f"  ❌ Failed to load batch file: {e}")
        return

    if not isinstance(items, list) or not items:
        print("  ❌ Batch file must contain a non-empty array of items.")
        return

    total = len(items)
    print(f"  📋 Batch loaded: {total} item(s)\n")

    delays = cfg.get_comment_delays()
    auto = FacebookAutomation(log_callback=_log)
    try:
        for i, item in enumerate(items, 1):
            profile_name = item.get("profile_name", "")
            brave_path = cfg.get_profile_path(profile_name)
            if not brave_path:
                print(f"  [{i}/{total}] ❌ Profile '{profile_name}' not found. Skipping.")
                continue

            post_url = item.get("post_url", "")
            comment_text = item.get("comment_text") or item.get("comment") or ""
            reaction = item.get("reaction") or ""
            action_type = item.get("action_type", "group")
            group_name = item.get("group_name", "")

            if not post_url:
                print(f"  [{i}/{total}] ❌ No post_url. Skipping.")
                continue

            print(f"  [{i}/{total}] Processing: {profile_name}...")

            # Launch profile directly with Brave path
            await auto.start_browser(brave_path)
            await auto.go_to_facebook()

            # Check login
            logged_in = await auto._is_logged_in(timeout=15)
            if not logged_in:
                print(f"  [{i}/{total}] ⚠️  Profile '{profile_name}' not logged in. Skipping.")
                await auto.cleanup()
                continue

            # Perform action
            if action_type == "comment":
                # A comment needs no group and shares nothing: the queue
                # has had this action for a while and the batch runner had
                # not, so a multi-account comment test meant the server.
                if not comment_text:
                    print(f"  [{i}/{total}] \u274c No comment_text. Skipping.")
                    await auto.cleanup()
                    continue
                ok = await auto._auto_comment(post_url, comment_text)
                msg = "Commented" if ok else (getattr(
                    auto, "last_comment_error", "") or "Failed to comment")
            elif action_type == "timeline":
                ok, msg = await auto.share_post_to_timeline(
                    post_url,
                    comment_text=comment_text or None,
                    reaction=reaction or None,
                )
            else:
                if not group_name:
                    print(f"  [{i}/{total}] ❌ No group_name for group share. Skipping.")
                    await auto.cleanup()
                    continue
                ok, msg = await auto.share_post_to_group(
                    post_url, group_name,
                    comment_text=comment_text or None,
                    reaction=reaction or None,
                )

            icon = "✅" if ok else "❌"
            print(f"  [{i}/{total}] {icon} {profile_name}: {msg}")

            # Cleanup after each item
            await auto.cleanup()

            # Space the accounts out. Several accounts commenting on one
            # post back to back is the pattern Facebook rate-limits, and
            # the operator already configured this spacing for it. Only an
            # account that actually acted is paced: a skipped profile did
            # nothing Facebook saw, so waiting on its behalf buys nothing.
            if i < total:
                wait = random.uniform(delays["between_comments_min"],
                                      delays["between_comments_max"])
                print(f"  waiting {wait:.0f}s before the next account...")
                await asyncio.sleep(wait)

        print(f"\n  📋 Batch complete: {total} item(s) processed")

    except KeyboardInterrupt:
        print("\n  Interrupted. Closing browser...")
        await auto.quit()
    except Exception as e:
        print(f"  ❌ Batch error: {e}")
        await auto.quit()


# ── Argument parser ──────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autoshare",
        description="AutoShare — Facebook Post Sharer (CLI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py list-profiles
  python cli.py launch-profile MyProfile
  python cli.py share "https://fb.com/post/123" "My Group" --profile MyProfile --reaction like
  python cli.py share-timeline "https://fb.com/post/123" --comment "Great post!" --reaction love
  python cli.py login user@email.com mypassword
  python cli.py batch queue.json
        """,
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # list-profiles
    sub.add_parser("list-profiles", help="List all saved profiles")

    # launch-profile
    p_launch = sub.add_parser("launch-profile", help="Launch a profile browser to Facebook")
    p_launch.add_argument("name", help="Profile name to launch")

    # share
    p_share = sub.add_parser("share", help="Share a post to a Facebook group")
    p_share.add_argument("post_url", help="URL of the post to share")
    p_share.add_argument("group_name", help="Name of the target group")
    p_share.add_argument("--profile", help="Profile to use (default: first saved)")
    p_share.add_argument("--comment", help="Optional comment text")
    p_share.add_argument("--reaction", choices=["like", "love", "care", "haha", "wow", "sad", "angry"],
                         help="Optional reaction type")
    p_share.add_argument("--debug", action="store_true",
                         help="Dump page HTML for debugging")

    # share-timeline
    p_timeline = sub.add_parser("share-timeline", help="Share a post to your Facebook Timeline")
    p_timeline.add_argument("post_url", help="URL of the post to share")
    p_timeline.add_argument("--profile", help="Profile to use (default: first saved)")
    p_timeline.add_argument("--comment", help="Optional comment text")
    p_timeline.add_argument("--reaction", choices=["like", "love", "care", "haha", "wow", "sad", "angry"],
                            help="Optional reaction type")
    p_timeline.add_argument("--debug", action="store_true",
                            help="Dump page HTML for debugging")

    # comment
    p_comment = sub.add_parser("comment", help="Post a comment on a post")
    p_comment.add_argument("post_url", help="URL of the post to comment on")
    p_comment.add_argument("--text", required=True,
                           help="comment text; several lines means one is "
                                "picked at random")
    p_comment.add_argument("--profile", help="Profile to use (default: first saved)")
    p_comment.add_argument("--debug", action="store_true",
                           help="Dump page HTML for debugging")

    # login
    p_login = sub.add_parser("login", help="Login to Facebook with email/password")
    p_login.add_argument("email", help="Facebook email or phone")
    p_login.add_argument("password", help="Facebook password")

    # batch
    p_batch = sub.add_parser("batch", help="Run a batch queue from a JSON file")
    p_batch.add_argument("file", help="Path to JSON file with batch items")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    command_map = {
        "list-profiles": cmd_list_profiles,
        "launch-profile": cmd_launch_profile,
        "share": cmd_share,
        "share-timeline": cmd_share_timeline,
        "comment": cmd_comment,
        "login": cmd_login,
        "batch": cmd_batch,
    }

    handler = command_map.get(args.command)
    if handler:
        asyncio.run(handler(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
