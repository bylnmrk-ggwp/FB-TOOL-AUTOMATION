"""What the Tk tabs used to hold between events, as one value the server
can serialise.

The event bridge assigns fields on its own thread and routes read them on
the event loop. Each field is a plain value replaced whole - a new RunState,
a new dict - never mutated in place, so a reader sees the old value or the
new one and not a half-built one. to_dict() is what GET /api/state and
every {"type": "state"} event carry.
"""
from dataclasses import asdict, dataclass, field

from src.storage import config_manager as cfg

# config_manager setting the bridge saves after each batch and the state
# reads back on construction, so a restart still shows the last outcome.
LAST_RUN_SUMMARY_KEY = "last_run_summary"


@dataclass
class RunState:
    """The run in progress, as the status bar and progress line show it."""
    kind: str            # "batch" | "login" | "scan" | "auto_setup" | "join" | "share" | "fetch" | "watch"
    current: int = 0
    total: int = 0
    message: str = ""
    profile_name: str = ""
    started_at: float = 0.0   # time.time() when the bridge opened the run


@dataclass
class AppState:
    run: RunState | None = None
    last_run_summary: str = ""          # restored from config when left blank
    # The batch queue, mirrored from the QueueStore app.py owns. It rides
    # along on every state event because a phone that has just woken would
    # otherwise need a second request to find out what it is looking at,
    # and because a device must see the list move when another device adds
    # to it, not only when it next opens the Queue page.
    queue: list[dict] = field(default_factory=list)
    pending_input: dict | None = None   # the open needs_input prompt, or None
    login_run_active: bool = False
    scan_active: bool = False
    # Creating Brave profiles for unlinked roster rows. Not a DriverManager
    # command - it is scripts/provision_profiles.py run in a thread - so it
    # needs its own flag rather than riding on `run`.
    provision_active: bool = False
    sheet_last_ok: float = 0.0          # SheetWatcher.last_ok; 0.0 before the first poll
    system: dict = field(default_factory=dict)   # from manager.get_memory_stats()
    bridge_alive: bool = True
    version: str = "dev"

    def __post_init__(self):
        # The dashboard's Run card would otherwise be blank after every
        # restart, although the previous batch's outcome is still the most
        # useful thing it can show until a new run starts.
        if not self.last_run_summary:
            saved = cfg.get_setting(LAST_RUN_SUMMARY_KEY, "")
            self.last_run_summary = str(saved) if saved else ""

    def to_dict(self) -> dict:
        """A JSON-safe copy: `run` as a dict or None, nested values copied
        so a broadcast cannot be changed under a subscriber."""
        return asdict(self)
