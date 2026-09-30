"""An account Facebook has gated drops out of the run instead of failing twice.

A wave of 84 profiles queued 168 items - React and Comment for each - and
finished "143/168 successful". Eleven of those profiles had no usable session:
eight landed on `/checkpoint/<id>/?next=...`, which is Facebook demanding a
human, and three had a session it no longer accepted. Each of the eleven was
launched twice, navigated twice and failed twice, so 22 items were counted
against a run that could never have done them.

Both halves of that are wrong. The second attempt cannot reach a different
verdict - a checkpoint has no password form, and a re-login cannot run
mid-batch because the shared browser holds Brave's singleton lock - so it is
pure cost. And the items belong outside the denominator: the account never
acted, which is not the same as the run failing.

The verdict has to be read from the message, not only from a flag: each action
phrases it differently. The comment path says "logged out or session expired",
share and timeline say "not logged in", a non-Like reaction says "login
overlay". A gate that understood one phrasing kept paying for the other two.
"""
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("gated accounts skipped")  # noqa: F821

from src.core.driver_manager import DriverManager  # noqa: E402

# ── The verdict itself ────────────────────────────────

gate = DriverManager._gate_reason

# A checkpoint, however the action phrased it.
for msg in ("Not logged in (checkpoint or verification required)",
            "checkpoint or verification required",
            "email confirmation required"):
    if gate({"ok": False, "message": msg}) != DriverManager._GATE_CHECKPOINT:
        failures.append(f"gated accounts skipped: {msg!r} is not read as a "  # noqa: F821
                        f"checkpoint, so the account is launched again")

# An expired session, in every phrasing the actions use.
for msg in ("logged out or session expired",
            "Not logged in (logged out or session expired)",
            "not logged in",
            "login overlay blocked the reaction"):
    if gate({"ok": False, "message": msg}) != DriverManager._GATE_EXPIRED:
        failures.append(f"gated accounts skipped: {msg!r} is not read as an "  # noqa: F821
                        f"expired session, so the account is launched again")

# The structured flag alone is enough - a message this proof cannot predict
# must still gate when the automation says so.
if gate({"ok": False, "needs_login": True, "message": "something new"}) \
        != DriverManager._GATE_EXPIRED:
    failures.append("gated accounts skipped: the needs_login flag does not gate "  # noqa: F821
                    "on its own")

# What must NOT gate: a live session whose action simply did not land. Three
# profiles in that run hit "Like button not found" and commented successfully
# seconds later - gating them would have thrown away work that worked.
for msg in ("Like button not found", "rate limit reached",
            "Facebook is restricting this account", "Commented"):
    verdict = gate({"ok": False, "message": msg})
    if verdict is not None:
        failures.append(f"gated accounts skipped: {msg!r} gated the account as "  # noqa: F821
                        f"{verdict!r}, but the session is live - its other "
                        f"items would be thrown away")

if gate({"ok": True, "message": "Reacted with 'Care'"}) is not None:
    failures.append("gated accounts skipped: a successful item gated the account")  # noqa: F821
if gate("not a dict") is not None:
    failures.append("gated accounts skipped: a non-result gated the account")  # noqa: F821

# ── How the run uses it ───────────────────────────────

src = inspect.getsource(DriverManager._do_batch)

if "gated: dict[str, str] = {}" not in src:
    failures.append("gated accounts skipped: the run keeps no record of which "  # noqa: F821
                    "profiles are gated, so it cannot skip their other items")
if "self._gate_reason(result)" not in src:
    failures.append("gated accounts skipped: the run never asks for the verdict")  # noqa: F821
if 'gate = gated.get(item.get("profile_name", ""))' not in src:
    failures.append("gated accounts skipped: items are not checked against the "  # noqa: F821
                    "gated set before being run")
if '"skipped": True' not in src:
    failures.append("gated accounts skipped: a skipped item is not marked, so a "  # noqa: F821
                    "UI counts it as a failure")

# The skip has to come BEFORE the anti-spam delay, or the run still spends the
# pause meant for real work on an account that will not act.
body = src[src.index("for i, (idx, item) in enumerate(batch_items):"):]
gate_at = body.index('gate = gated.get(')
delay_at = body.index("Waiting {delay:.1f}s")
if gate_at > delay_at:
    failures.append("gated accounts skipped: the gate is checked after the "  # noqa: F821
                    "delay, so a skipped item still costs the anti-spam pause")

# Skipped items leave the denominator, and the count is carried to consumers.
if "skipped_count += 1" not in src:
    failures.append("gated accounts skipped: skipped items are not counted apart")  # noqa: F821
if "countable = max(0, total - skipped_count)" not in src:
    failures.append("gated accounts skipped: the denominator still includes the "  # noqa: F821
                    "items no account could have done")
if '"skipped": skipped_count' not in src:
    failures.append("gated accounts skipped: batch_result carries no skipped "  # noqa: F821
                    "count, so the dashboard reports them as failures")

# Neither success nor failure: a skipped item must not reach the branch that
# counts one.
if "if result.get(\"skipped\"):" not in src:
    failures.append("gated accounts skipped: a skipped result falls through to "  # noqa: F821
                    "the success/failure accounting")

# ── The dashboard's own arithmetic ────────────────────

from src.server import data  # noqa: E402

line = data.summary_line(143, 0, skipped=22)
if "22 skipped" not in line:
    failures.append(f"gated accounts skipped: the run summary hides the skipped "  # noqa: F821
                    f"items: {line!r}")
if "0 failed" not in line:
    failures.append(f"gated accounts skipped: skipped items are reported as "  # noqa: F821
                    f"failures: {line!r}")
if "skipped" in data.summary_line(3, 1):
    failures.append("gated accounts skipped: a run with nothing skipped still "  # noqa: F821
                    "mentions it")

events_src = inspect.getsource(__import__("src.server.events",
                                          fromlist=["events"]).EventBridge)
if "total - ok_count - skipped" not in events_src:
    failures.append("gated accounts skipped: the dashboard still derives failures "  # noqa: F821
                    "as total minus ok, counting every gated item as a failure")

print("FAILED" if [f for f in failures if "gated accounts skipped" in f] else "ok")  # noqa: F821
