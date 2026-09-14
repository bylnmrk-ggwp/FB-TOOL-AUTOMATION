"""Every self._method() a UI tab calls actually exists.

Removing the profile dot grid took _displayed_profiles with it and left four
"Add to Queue" handlers calling it. Nothing failed until a button was pressed,
and then every press raised AttributeError into the Tkinter callback - the
queue looked alive and could not accept a single item.

A missing method is invisible to the import and to every proof that does not
press that exact button, so the check is structural: gather what each class
defines, gather what it calls on self, and require the second to be inside
the first.
"""
import ast
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("ui calls resolve")  # noqa: F821

MODULES = ("src/ui/queue_tab.py", "src/ui/profiles_tab.py", "src/ui/main_window.py")

# Attributes any module assigns on any object: main_window injects
# profiles_tab._log_callback from outside the class, and that is not a
# missing method.
injected = set()
for rel in MODULES:
    for node in ast.walk(ast.parse((ROOT / rel).read_text(encoding="utf-8"))):  # noqa: F821
        if isinstance(node, ast.Assign):
            injected |= {t.attr for t in node.targets if isinstance(t, ast.Attribute)}

for rel in MODULES:
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))  # noqa: F821
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        defined = {n.name for n in ast.walk(node)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        # Attributes assigned on self are callables too (callbacks, Tk vars,
        # the hover-clearing closures), and inherited ttk methods are not in
        # this file at all - so only names that look like this class's own
        # private methods are checked.
        assigned = {t.attr for n in ast.walk(node) if isinstance(n, ast.Assign)
                    for t in n.targets
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
                    and t.value.id == "self"}
        called = {n.func.attr for n in ast.walk(node)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"
                  and n.func.attr.startswith("_")}
        missing = sorted(called - defined - assigned - injected)
        if missing:
            failures.append(f"ui calls resolve: {rel} {node.name} calls "  # noqa: F821
                            f"{', '.join(missing)}, which it does not define - "
                            f"every press of that control raises AttributeError")

print("FAILED" if [f for f in failures if "ui calls resolve" in f] else "ok")  # noqa: F821
