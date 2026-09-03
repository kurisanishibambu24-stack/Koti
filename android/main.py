"""
main.py — Android entrypoint (used only inside the APK build).

python-for-android's "webview" bootstrap wraps this script in a native
Android WebView shell: it runs this file as a background service and then
opens a WebView pointing at http://127.0.0.1:5000. So all this file needs
to do is start the JobBot Flask server on that host/port and then stay
alive — the actual UI is the WebView the bootstrap already created.
"""
import os
import sys
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jobbot  # noqa: E402


def start_server():
    jobbot.init_db()
    jobbot.ensure_directories()
    app = jobbot.build_flask_app()
    if app is None:
        print("[!] Flask app failed to build — check requirements in buildozer.spec")
        return
    # host 127.0.0.1 + port 5000 must match what the webview bootstrap loads
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    # Keep the process alive; the WebView shell is what the user sees.
    while True:
        time.sleep(1)
