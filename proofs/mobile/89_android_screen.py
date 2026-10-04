"""The Android screen is read correctly, and a password is never half-typed.

Logging accounts into Facebook Lite means driving a real Android screen over
adb: `uiautomator dump` for what is there, `input tap` and `input text` to
answer it. Two things in that have to be right, and both are testable with no
emulator running - which is why they are here rather than only in a live run.

Reading the screen: a dump arrives as XML and is occasionally truncated,
because uiautomator writes it while the screen is still moving. A truncated
dump must read as "nothing on screen yet", which the caller retries, rather
than as a traceback that ends the run for every remaining account.

Typing: `input text` sends its argument through a shell. A value holding a
quote, a backslash or a '%' can arrive doubled, mangled or cut short, and
there is no escape for a literal '%' that is defined across Android builds.
A password typed WRONG is worse than one not typed at all - Facebook counts
a failed login against an account that is already being gated, and the run
reports "wrong password" for a mistake made on this side. So type_text
refuses what it cannot send exactly.
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("android screen")  # noqa: F821

from src.mobile.adb import Device, Node, find, parse_screen  # noqa: E402


def _fail(msg):
    failures.append(f"android screen: {msg}")  # noqa: F821


DUMP = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout"
        content-desc="" password="false" bounds="[0,0][1600,900]">
    <node index="1" text="Facebook" resource-id="com.facebook.lite:id/title"
          class="android.widget.TextView" content-desc=""
          password="false" bounds="[40,60][400,140]" />
    <node index="2" text="" resource-id="com.facebook.lite:id/login_username"
          class="android.widget.EditText" content-desc="Email or phone"
          password="false" bounds="[40,200][1560,300]" />
    <node index="3" text="" resource-id="com.facebook.lite:id/login_password"
          class="android.widget.EditText" content-desc="Password"
          password="true" bounds="[40,320][1560,420]" />
    <node index="4" text="Log In" resource-id="com.facebook.lite:id/login"
          class="android.widget.Button" content-desc=""
          password="false" bounds="[40,460][1560,560]" />
  </node>
</hierarchy>"""

nodes = parse_screen(DUMP)
if len(nodes) != 5:
    _fail(f"expected 5 nodes in the dump, parsed {len(nodes)}")

# A tap goes to the middle of an element, not its corner.
button = find(nodes, resource_id="com.facebook.lite:id/login")
if not button:
    _fail("the Log In button was not found by resource id")
elif button[0].centre != (800, 510):
    _fail(f"the button's centre is {button[0].centre}, not (800, 510); a tap "
          f"would land off the control")

# The password field is told apart by its password flag, not by guessing from
# a label - the label is localised and the flag is not.
secret = find(nodes, password=True)
if len(secret) != 1 or secret[0].resource_id != "com.facebook.lite:id/login_password":
    _fail(f"the password field was not identified by its password flag "
          f"(found {[n.resource_id for n in secret]})")

# Facebook Lite localises and pads its labels, so text matching is loose;
# resource ids are not user-facing, so they match exactly.
if not find(nodes, text="log in"):
    _fail("text matching is case-sensitive, so a relabelled button is missed")
if not find(nodes, desc="email"):
    _fail("content-desc matching is case-sensitive")
if find(nodes, resource_id="com.facebook.lite:id/log"):
    _fail("resource ids match on a prefix, so the wrong control can be tapped")

# A dump caught mid-animation must read as "nothing yet", never raise.
for broken in ("", "<hierarchy><node bounds=", "not xml at all",
               "<hierarchy><node bounds=\"garbage\" /></hierarchy>"):
    try:
        if parse_screen(broken):
            _fail(f"a malformed dump produced nodes: {broken[:24]!r}")
    except Exception as e:  # noqa: BLE001
        _fail(f"a malformed dump raised {type(e).__name__} instead of "
              f"reading as an empty screen: {broken[:24]!r}")


# -- typing --------------------------------------------------------------

d = Device.__new__(Device)          # no emulator, no adb, no connection

# Ordinary credentials go through.
for ok in ("battlerrene3@gmail.com", "9283402278", "Passw0rd-123",
           "a b c", "user.name+tag@example.co.uk", ""):
    if not d.can_type(ok):
        _fail(f"refused a value it can send: {ok!r}")

# Anything ambiguous through a shell is refused, NOT guessed at.
for bad in ('quote"inside', "apostrophe'inside", "back\\slash", "50%off",
            "dollar$sign", "semi;colon", "pipe|char", "back`tick",
            "amp&ersand", "star*glob", "brace{x}", "new\nline"):
    if d.can_type(bad):
        _fail(f"accepted a value it cannot send exactly: {bad!r}")

# The refusal has to be an error the caller can report, and it must name the
# offending characters - "it failed" sends the operator to the wrong account.
try:
    d.type_text("pa%ss\"word")
    _fail("type_text silently accepted an unsendable password")
except ValueError as e:
    if "%" not in str(e) or '"' not in str(e):
        _fail(f"the refusal does not name the offending characters: {e}")
except Exception as e:  # noqa: BLE001
    _fail(f"type_text raised {type(e).__name__}, not a reportable ValueError")

print("FAILED" if [f for f in failures if "android screen" in f] else "ok")  # noqa: F821
