"""
PyQt6 migration smoke test.

Tests the most common failure points when migrating from PyQt5:
  - WebEngine import order (must precede QApplication in PyQt6)
  - QWebEngineView + setHtml()
  - QTreeWidget with items and column headers
  - Enum namespacing (Qt.ItemFlag, Qt.Orientation, etc.)

Run with:
    python pyqt6_smoke_test.py

Exit code 0 = all passed, 1 = one or more failures.
"""

import sys

# --- PyQt6 WebEngine must be imported before QApplication ---
# This is a hard requirement in PyQt6 that doesn't exist in PyQt5.
# If this import happens after QApplication is created you get a
# silent failure or crash.
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_AVAILABLE = True
except ImportError:
    WEBENGINE_AVAILABLE = False
    print("WARNING: PyQt6-WebEngine not installed. Skipping WebEngine tests.")
    print("         Install with: pip install PyQt6-WebEngine")

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem, QSplitter
)
from PyQt6.QtCore import Qt, QTimer

RESULTS = []


def log(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    msg = f"[{status}] {name}"
    if detail:
        msg += f": {detail}"
    print(msg)
    RESULTS.append((name, passed))


def test_webengine(parent):
    """QWebEngineView instantiation and setHtml()."""
    if not WEBENGINE_AVAILABLE:
        print("[SKIP] WebEngine: not installed")
        return None

    try:
        view = QWebEngineView(parent)
        log("WebEngine: QWebEngineView instantiation", True)
    except Exception as e:
        log("WebEngine: QWebEngineView instantiation", False, str(e))
        return None

    try:
        html = """<!DOCTYPE html>
<html>
  <head><meta charset="UTF-8"></head>
  <body>
    <h1>Smoke test</h1>
    <p>If you can read this, setHtml() worked.</p>
    <button onclick="document.title='clicked'">Click me</button>
  </body>
</html>"""
        view.setHtml(html)
        log("WebEngine: setHtml() accepted", True)
    except Exception as e:
        log("WebEngine: setHtml() accepted", False, str(e))

    return view


def test_treewidget(parent):
    """QTreeWidget with column headers, items, children, and flag enums."""
    try:
        tree = QTreeWidget(parent)
        tree.setColumnCount(2)
        tree.setHeaderLabels(["Feed", "Unread"])
        log("TreeWidget: instantiation + header labels", True)
    except Exception as e:
        log("TreeWidget: instantiation + header labels", False, str(e))
        return None

    try:
        for feed_name, unread in (("Feed A", "3"), ("Feed B", "0")):
            feed_item = QTreeWidgetItem(tree, [feed_name, unread])

            # Qt.ItemFlag enums are namespaced in PyQt6.
            # PyQt5 allowed Qt.ItemIsEnabled; PyQt6 requires Qt.ItemFlag.ItemIsEnabled.
            feed_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )

            for entry in ("Entry 1", "Entry 2"):
                child = QTreeWidgetItem(feed_item, [entry, ""])
                child.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )

        log("TreeWidget: item + child construction with Qt.ItemFlag enums", True)
    except Exception as e:
        log("TreeWidget: item + child construction with Qt.ItemFlag enums", False, str(e))
        return None

    try:
        tree.expandAll()
        tree.setColumnWidth(0, 200)
        tree.setColumnWidth(1, 60)
        log("TreeWidget: expandAll() + column sizing", True)
    except Exception as e:
        log("TreeWidget: expandAll() + column sizing", False, str(e))

    return tree


def main():
    app = QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("PyQt6 smoke test")
    window.resize(900, 600)

    # Qt.Orientation enum is also namespaced in PyQt6
    splitter = QSplitter(Qt.Orientation.Horizontal)

    tree = test_treewidget(splitter)
    if tree:
        splitter.addWidget(tree)

    web = test_webengine(splitter)
    if web:
        splitter.addWidget(web)
        splitter.setSizes([250, 650])

    window.setCentralWidget(splitter)
    window.show()

    # Auto-quit after 2 seconds so it's scriptable.
    # Comment this out to leave the window open for manual inspection.
    #QTimer.singleShot(2000, app.quit)

    app.exec()

    print()
    passed = sum(1 for _, ok in RESULTS if ok)
    total = len(RESULTS)
    print(f"Results: {passed}/{total} passed")

    if passed < total:
        print("\nFailed checks:")
        for name, ok in RESULTS:
            if not ok:
                print(f"  - {name}")
        sys.exit(1)
    else:
        print("All checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()