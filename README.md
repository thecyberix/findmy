# Find Me

A personal dashboard and Android app for **your own AirTags**, built around [FindMy.py](https://github.com/malmeloo/FindMy.py).

Sign in with an Apple ID (email, password, SMS or trusted-device 2FA), import AirTag key files, then pull location reports from Apple’s Find My network.

This is for tags you already own. It is not Sign in with Apple (OAuth), and not a way to look up tags that are not yours.

## Disclaimer

**Use at your own risk.** This project is unofficial and is not affiliated with, endorsed by, or supported by Apple Inc. It talks to undocumented Find My / Apple account endpoints and uses third-party Anisette services. Apple can change or break those APIs at any time, and misuse (including aggressive login attempts or shared Anisette abuse) may lock or restrict your Apple ID.

- Prefer **Trusted device** 2FA when signing in.
- Never commit or share Apple credentials, session files, or AirTag key JSON — anyone with those keys can query that tag.
- The Android app name “FindMy” is not an Apple product; Apple’s Find My branding belongs to Apple.

## AirTags need keys, not just login

Apple ID sign-in is **not enough** to list AirTags. Reports on the Find My network are encrypted. The decryption keys sit in iCloud Keychain on Apple devices that already have those items in Find My. FindMy.py can fetch reports once it has the keys; it still cannot join the keychain circle by itself ([issue 173](https://github.com/malmeloo/FindMy.py/issues/173)).

iCloud.com / Find My iPhone also will not show AirTags. Those APIs only cover devices that upload their own GPS (iPhone, iPad, Mac, Watch).

### Get the keys without a Mac

Use [export-findmy](https://github.com/stek29/export-findmy) on Linux or Windows. It joins iCloud Keychain via escrow recovery and writes FindMy.py JSON.

You will need:

1. The Apple ID that owns the tags
2. A 2FA code
3. The **screen lock passcode** of an iPhone or iPad that already shows the AirTags in Find My

Then import those `.json` files here and hit Refresh locations.

### Get the keys with a Mac

On a Mac signed into the same Apple ID:

```bash
python -m findmy decrypt --out-dir devices/
```

Import the JSON files in this app.

Do not share accessory JSON. Anyone with those files can query that tag.

## Demo mode

Use **Try the demo** to walk the UI with sample tags. Live Apple login still will not invent AirTags until you import keys.

## Run locally

Needs Python 3.12+ and Node 22+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

npm install
npm run build

python run.py
```

Open [http://127.0.0.1:43147](http://127.0.0.1:43147).

FindMy.py may download Anisette libraries into `data/ani_libs.bin` on first live login.

## Android app

```bash
cd android
./gradlew.bat assembleDebug
```

Install `app/build/outputs/apk/debug/app-debug.apk`. The app is **FindMy**: Apple ID once (session encrypted on device), add/remove AirTag JSON, map shows only the selected tag, optional daily ~20:00 alerts for very low battery or no report for over a day.

## Stack

- FastAPI session API wrapping FindMy.py (`AppleAccount`, 2FA, `FindMyAccessory`, `fetch_location`)
- Vite + React UI and an OpenStreetMap view of last reports
