[app]
title = JobBot
package.name = jobbot
package.domain = org.kurisanishibambu
source.dir = .
source.include_exts = py,json,txt,html,png
version = 1.0

requirements = python3==3.11.8,hostpython3==3.11.8,flask,jinja2,werkzeug,markupsafe,itsdangerous,click,blinker,fpdf2,pypdf

orientation = portrait
fullscreen = 0

android.permissions = INTERNET
android.api = 33
android.minapi = 24
android.ndk_api = 24
android.ndk = 25b
android.archs = arm64-v8a

p4a.bootstrap = webview

[buildozer]
log_level = 2
warn_on_root = 1
