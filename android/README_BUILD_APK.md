# Building JobBot as a real Android APK

## How this works

Android apps can't just "run a Flask server + open a browser tab" the way a
laptop can — so this uses a well-known pattern:

- **python-for-android**'s `webview` bootstrap bundles a real Python
  interpreter + your code into the APK.
- `android/main.py` starts the JobBot Flask server in a background thread on
  `127.0.0.1:5000`.
- The bootstrap automatically opens a native WebView (basically a chromeless
  browser window baked into the app) pointing at that address — so the app
  *looks* like a normal app, but under the hood it's still your dashboard.

## Why this has to build on GitHub, not on my end

Compiling this requires downloading the Android SDK + NDK (multiple GB) and
running a long native build — I don't have internet access in my working
environment to do that here. GitHub Actions runners do have internet access,
so the included workflow (`.github/workflows/build-apk.yml`) does the actual
compiling for you, for free, and hands you back a downloadable `.apk`.

## Steps

1. Create a new **public or private GitHub repo** and push this whole folder
   to it (must include the `android/` folder and `.github/workflows/` folder,
   exactly as they are).
2. On GitHub, go to the **Actions** tab of your repo. You should see
   "Build JobBot APK" — click it, then **Run workflow** (or just push a
   commit that touches something inside `android/`, which triggers it
   automatically).
3. Wait — this takes **20–40 minutes** the first time (it's compiling a lot
   from scratch). Grab a coffee.
4. When it finishes, open the completed run, scroll to **Artifacts**, and
   download `JobBot-apk`. Unzip it to get `jobbot-1.0-arm64-v8a_armeabi-v7a-debug.apk`.
5. Send that `.apk` file to friends (WhatsApp, Google Drive, email — any way
   you'd send a normal file). On their phone they'll need to allow
   "Install unknown apps" for whichever app they downloaded it through
   (Android will prompt them automatically the first time).

## If the build fails (very possible — be ready to debug)

Android/Python packaging is notoriously fragile. If the GitHub Action goes
red, **open the failed run and copy the last 30–50 lines of the log** — paste
them back to me and I'll help you fix it. Common causes, roughly in order of
likelihood:

- **A dependency isn't pure Python.** `requirements` in `buildozer.spec`
  currently only lists `python3,flask,fpdf2,pypdf` — all pure Python, no
  compiled code, which is deliberate. If you add anything else to jobbot.py
  later, adding it here too can break the build if it needs compilation.
- **NDK/SDK version mismatch.** Occasionally Buildozer's default SDK/NDK
  versions fall out of sync with what Google currently serves. If you see
  errors about "license not accepted" or a missing NDK version, that's this —
  I can pin exact versions once we see the error.
- **The `webview` bootstrap needing extra Android permissions** (e.g. if
  you later want it to read files for CV uploads from outside the app's own
  storage) — Android 11+ locks down file access more than a normal browser
  upload button expects, so uploading an "own CV" file inside the APK version
  may need extra permission handling that a website doesn't need. The core
  dashboard/browsing/fetching functionality shouldn't be affected.
- **Build timeout.** GitHub's free runners cap at 6 hours per job, so this
  shouldn't be an issue, but very first builds are slow — that's expected.

## What this can't fix

This is still an Android-only path. There's no equivalent free route to a
standalone iPhone app — iOS requires either a paid ($99/yr) Apple Developer
account + a Mac to sign the app, or your iPhone friends running JobBot
through iSH (already set up earlier). Once the Android APK exists, your
Android friends get a real tap-to-open app; iPhone friends still need iSH.
