# Find Me

A small web app for **your own AirTags**, built around [FindMy.py](https://github.com/malmeloo/FindMy.py).

Sign in with an Apple ID (email, password, SMS or trusted-device 2FA), import AirTag key files, then pull location reports from Apple’s Find My network.

This is a personal dashboard. It is not an Android client, not Sign in with Apple (OAuth), and not a way to look up tags that are not yours.

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

## Stack

- FastAPI session API wrapping FindMy.py (`AppleAccount`, 2FA, `FindMyAccessory`, `fetch_location`)
- Vite + React UI and an OpenStreetMap view of last reports
