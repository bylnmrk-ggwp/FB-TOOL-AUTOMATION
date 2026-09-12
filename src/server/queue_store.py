"""The batch queue, held by the server so every device sees one list.

QueueTab kept its items inside the widget: one window, one queue, and it
died with the process. On the web a phone adds three items and a laptop
presses Run, so the list lives here instead - behind one lock, and
validated at the door rather than by whichever form built the dict.

The "id" this store adds is for the UI alone: it is what a remove button
sends back, since an index shifts under another device's remove. to_run()
strips it again, because DriverManager._process_one must receive exactly
the dict shape the Tk tab handed it and that contract is frozen.
"""
import threading

# What _process_one branches on; "group" is its default, so it is the
# default here. A value outside this tuple would silently become a group
# share in the worker, which is why it is refused instead.
ACTION_TYPES: tuple[str, ...] = ("group", "timeline", "post_text", "react",
                                 "comment", "share", "story")

# The rest of what _process_one reads off an item, as strings. Listed so a
# key the worker never looks at cannot ride along into the batch.
_TEXT_FIELDS: tuple[str, ...] = ("post_url", "group_name", "comment_text",
                                 "reaction", "text")


def _image_paths(value) -> list[str]:
    """post_text items carry the file picker's paths; a phone's uploads
    land in the same key once they are saved on the PC."""
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        raise ValueError("image_paths must be a list of paths")
    try:
        raw = list(value)
    except TypeError:
        raise ValueError("image_paths must be a list of paths") from None
    return [str(p).strip() for p in raw if str(p).strip()]


def _require(item: dict) -> None:
    """The fields whose absence the worker cannot survive politely:
    _process_one indexes item["post_url"] directly for every action but a
    text post, and a group share with no group name searches Facebook for
    "?" and shares into whatever that finds."""
    action = item["action_type"]
    if action == "post_text":
        if not item.get("text"):
            raise ValueError("text is required for a text post")
        return
    url = item.get("post_url", "")
    if not url:
        raise ValueError("post_url is required")
    if not url.startswith("http"):
        raise ValueError("post_url must start with http")
    if action == "group" and not item.get("group_name"):
        raise ValueError("group_name is required for a group share")


def normalise(item: dict) -> dict:
    """One queue item as the worker wants it, or ValueError with a line a
    route can hand back as the 400. Empty optionals are left out: the
    worker reads every one of them through .get(), so an absent key and a
    blank one mean the same thing and the stored item stays the shape the
    form actually filled in."""
    if not isinstance(item, dict):
        raise ValueError("a queue item must be an object")
    profile_name = str(item.get("profile_name") or "").strip()
    if not profile_name:
        raise ValueError("profile_name is required")
    action_type = str(item.get("action_type") or "group").strip() or "group"
    if action_type not in ACTION_TYPES:
        raise ValueError("action_type must be one of " + ", ".join(ACTION_TYPES))
    out = {"profile_name": profile_name, "action_type": action_type}
    for key in _TEXT_FIELDS:
        value = item.get(key)
        if value is None:
            continue
        value = str(value).strip()
        if value:
            out[key] = value
    images = _image_paths(item.get("image_paths"))
    if images:
        out["image_paths"] = images
    _require(out)
    return out


def _copy(item: dict) -> dict:
    """A copy a caller may serialise or even edit; the list this store owns
    is never handed out."""
    out = dict(item)
    if "image_paths" in out:
        out["image_paths"] = list(out["image_paths"])
    return out


class QueueStore:
    """The shared queue. Every method is safe to call from a route thread,
    which is where all of them are called from."""

    def __init__(self):
        self._lock = threading.Lock()
        self._items: list[dict] = []
        self._next_id = 1

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def add(self, item: dict) -> dict:
        """Validate one item and append it. The stored copy, id and all,
        comes back so a route can answer with what it actually kept."""
        stored = normalise(item)
        with self._lock:
            stored["id"] = self._mint_id()
            self._items.append(stored)
            return _copy(stored)

    def items(self) -> list[dict]:
        with self._lock:
            return [_copy(it) for it in self._items]

    def remove(self, index: int) -> bool:
        """False rather than IndexError when the item is already gone: two
        devices removing the same row is ordinary, not an error."""
        with self._lock:
            if index < 0 or index >= len(self._items):
                return False
            del self._items[index]
            return True

    def clear(self) -> int:
        with self._lock:
            count = len(self._items)
            self._items.clear()
            return count

    def replace(self, items: list[dict]) -> None:
        """All or nothing: every item is validated before the old list
        goes, so a bad one in the middle cannot leave half a queue."""
        fresh = [normalise(it) for it in items]
        with self._lock:
            for it in fresh:
                it["id"] = self._mint_id()
            self._items = fresh

    def to_run(self) -> list[dict]:
        """What DriverManager.run_queue takes: the stored items without the
        id, which is ours and means nothing to the worker."""
        with self._lock:
            out = []
            for it in self._items:
                item = _copy(it)
                item.pop("id", None)
                out.append(item)
            return out

    def _mint_id(self) -> str:
        # Caller holds the lock. Ids are never reused, so a remove sent by
        # a phone that missed someone else's remove misses rather than
        # deleting whatever took that row's place.
        item_id = f"q{self._next_id}"
        self._next_id += 1
        return item_id
