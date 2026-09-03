# JobBot 💙

A local tool that finds jobs, tailors an ATS-friendly CV (or uses your own), and helps you send applications — with a simple dark-blue dashboard in your browser.

## Important: this runs on YOUR computer, not a shared website

JobBot isn't a hosted app — each person runs their own private copy on their own computer. That's actually a good thing here:

- Your CV, personal details, and email login never leave your machine.
- Everyone applies as *themselves*, from their *own* email account.
- There's nothing to pay for or host — just run it locally whenever you want to job hunt.

So "sharing the app" means sharing this folder — each friend runs it independently, with their own data.

## Setup (one-time, ~2 minutes)

### Windows / Mac / Linux

1. Install **Python 3** if you don't have it: https://www.python.org/downloads/
   - **Windows:** during install, tick "Add python.exe to PATH".
2. Unzip this folder anywhere on your computer.
3. Double-click the launcher for your system:
   - **Mac / Linux:** `run_mac_linux.sh` (if it won't open, run `chmod +x run_mac_linux.sh` once in Terminal)
   - **Windows:** `run_windows.bat`

The first run installs a few small Python packages automatically. After that, just double-click the launcher any time to start JobBot.

### Android (no PC needed)

You can run this straight from your phone using **Termux** — a free terminal app that runs real Python on Android, no root required.

1. Install Termux from **F-Droid** (not the old, broken Play Store version): https://f-droid.org/packages/com.termux/
   - You'll need the F-Droid app first (also free): https://f-droid.org/
2. Get this JobBot folder onto your phone (e.g. save the zip to Downloads, or share it to your phone via Google Drive/WhatsApp/etc.) and unzip it. A file manager app (like the built-in "My Files" on Samsung) can unzip it — tap the zip and choose "Extract."
3. Open Termux and give it access to your files:
   ```
   termux-setup-storage
   ```
   (tap Allow when prompted)
4. Move into the JobBot folder — for example, if you extracted it to your phone's Downloads:
   ```
   cd storage/downloads/JobBot
   ```
5. Make the launcher runnable and start it:
   ```
   chmod +x run_termux.sh
   ./run_termux.sh
   ```
   First run will take a couple of minutes to install Python packages — that's normal.
6. Once it says "Starting JobBot Web UI," open Chrome (or any browser) on your phone and go to:
   ```
   http://127.0.0.1:5000
   ```
7. To use it again later, just reopen Termux and run `cd storage/downloads/JobBot && ./run_termux.sh`.

**Tip:** Termux will keep running as long as its notification is showing. If Android kills it in the background, swipe down and tap the Termux notification to bring it back, or disable battery optimization for Termux (Settings → Apps → Termux → Battery → Unrestricted).

### iPhone / iPad (no PC needed)

The iPhone equivalent of Termux is **iSH** — a free terminal app on the App Store that runs a real (if slightly slow) Linux environment. Setup is similar:

1. Install **iSH Shell** from the App Store: https://apps.apple.com/app/ish-shell/id1436902243
2. Get this JobBot folder onto your iPhone — e.g. AirDrop the zip from a Mac, or download it via Safari/Files app into the **Files** app, then unzip it (tap the zip → it extracts automatically).
3. Open iSH. By default it starts in its own sandboxed filesystem — to reach files in the iPhone's Files app, use iSH's built-in path:
   ```
   cd /mnt
   ```
   iSH mounts the Files app under `/mnt`. Navigate into wherever you extracted JobBot, e.g.:
   ```
   cd /mnt/Downloads/JobBot
   ```
   (If you can't see it there, open the **Files** app first, tap the JobBot folder once to "wake" iSH's view of it, then retry.)
4. Make the launcher runnable and start it:
   ```
   chmod +x run_ish.sh
   ./run_ish.sh
   ```
   First run installs Python — this can take several minutes on iSH since it emulates a CPU architecture; that's normal, let it finish.
5. Once it says "Starting JobBot Web UI," open Safari and go to:
   ```
   http://127.0.0.1:5000
   ```
6. To use it again later, reopen iSH and run `cd /mnt/Downloads/JobBot && ./run_ish.sh`.

**Heads up:** iOS suspends apps aggressively in the background, so keep iSH open (in the foreground or split-view with Safari) while using JobBot. It's noticeably slower to install packages than Termux on Android, but once set up it runs fine for browsing the dashboard.

## Using it

1. After launching, open **http://127.0.0.1:5000** in your browser.
2. From the terminal/command prompt (the window that opened), you can also run setup commands like:
   - `python jobbot.py cv-import mycv.pdf` — import your CV so JobBot can tailor applications
   - `python jobbot.py fetch` — search for jobs (you'll be asked to pick a province)
   - `python jobbot.py web` — reopen the dashboard any time
3. In the dashboard you can review each job, choose "custom ATS CV" or "own CV," edit the email draft, and select jobs to send.

## Sending emails

Before sending, you'll need to set up your email account's SMTP details and app password (Gmail requires an "app password," not your normal password — search "Gmail app password" for the quick setup). JobBot throttles sends automatically to avoid tripping spam/rate limits.

## Sharing with friends

Just zip this whole folder (including `jobbot.py`, `requirements.txt`, and the launcher scripts) and send it to them. Each person runs their own copy — nobody shares data or credentials.
