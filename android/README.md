# g-script for Android

A small Android app that opens the g-script phone page full screen, remembers which PC to use, and
**alerts you when the AI is done or needs your OK** (even with the screen off).

You chat and approve from the phone; the building happens in Roblox Studio on your PC.

## Get the APK (pick one)

> Using the whole g-script repository? Its **Actions → Build Android APK** workflow builds this for you; skip to "Use it".

**A. Let GitHub build it for you (no Android tools needed)**
1. Make a free GitHub account, create a new empty repository.
2. Upload everything in this folder (keep the `.github` folder) to the repository's main branch.
3. Open the repository's **Actions** tab, choose **Build APK**, press **Run workflow**.
4. When it finishes (about 5 minutes), open the run and download the **g-script-apk** artifact. Unzip it: `app-debug.apk`.

**B. Android Studio**
1. Install Android Studio, choose **Open**, pick this folder, let it sync.
2. **Build > Build APK(s)**. The file is in `app/build/outputs/apk/debug/app-debug.apk`.

Copy the APK to your phone and open it (allow "install unknown apps" for your file manager or browser once).

## Use it
1. On your PC open g-script, turn on **Phone**.
2. In the app, paste the link the PC shows:
   The phone must be on the same Wi-Fi as the PC. Tip: you can also *Share* the link to g-script from any app.
3. Your PC asks you to **Allow** the phone (compare the two words). No codes to type.
4. Type what to build. Allow notifications when asked to get "Done" and "Approval needed" alerts.

## Good to know
- This project was written without being compiled (no Android tooling was available where it was made).
  If a build error appears, copy the first error line to the developer: it is usually a one-line fix.
- Alerts can be delayed when the phone has been idle for a long time. For faster alerts, set the app's
  battery usage to "Unrestricted".
- Needs your PC on, g-script open, and an AI chat tab open and visible, on the same Wi-Fi.
