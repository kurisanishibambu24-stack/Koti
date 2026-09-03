[app]
title = JobBot
package.name = jobbot
package.domain = org.jobbot
source.dir = .
source.include_exts = py,json,txt
version = 1.0

# Pure-Python requirements only — no compiled/native packages, which is what
# most commonly breaks Android builds. flask's own dependencies
# (werkzeug, jinja2, click, itsdangerous, markupsafe) are pulled in with it.
requirements = python3,flask,fpdf2,pypdf

orientation = portrait
fullscreen = 0

android.permissions = INTERNET
android.api = 33
android.minapi = 24
android.ndk_api = 24
android.archs = arm64-v8a,armeabi-v7a

# This is the important bit: the webview bootstrap runs main.py as a
# background service and shows a native WebView pointing at
# http://127.0.0.1:5000 once the Flask server (in main.py) is up.
p4a.bootstrap = webview

[buildozer]
log_level = 2
warn_on_root = 1
