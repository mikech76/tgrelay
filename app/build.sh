#!/bin/bash
# Сборка APK внутри контейнера с Android SDK. Запускается из папки проекта.
set -euo pipefail
cd /app

SDK="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-/opt/android-sdk}}"
[ -d "$SDK" ] || SDK=/usr/local/android-sdk
[ -d "$SDK" ] || { echo "SDK не найден"; ls /opt /usr/local; exit 1; }

BT="$(ls -d "$SDK"/build-tools/* 2>/dev/null | sort -V | tail -1)"
PLATFORM_DIR="$(ls -d "$SDK"/platforms/android-* 2>/dev/null | sort -V | tail -1)"
PLATFORM="$PLATFORM_DIR/android.jar"

echo "SDK        = $SDK"
echo "build-tools= $BT"
echo "platform   = $PLATFORM"
java -version 2>&1 | head -2

rm -rf build
mkdir -p build/res build/gen build/classes build/dex

echo "== aapt2 compile =="
"$BT/aapt2" compile --dir res -o build/res/resources.zip

echo "== aapt2 link =="
"$BT/aapt2" link \
  -o build/base.apk \
  -I "$PLATFORM" \
  --manifest AndroidManifest.xml \
  -A assets \
  build/res/resources.zip \
  --java build/gen \
  --min-sdk-version 24 \
  --target-sdk-version 34 \
  --version-code 1 \
  --version-name 1.0

echo "== javac =="
javac -source 8 -target 8 -Xlint:-options \
  -classpath "$PLATFORM" \
  -encoding UTF-8 \
  -d build/classes \
  $(find src build/gen -name '*.java')

echo "== d8 =="
"$BT/d8" --release --min-api 24 --lib "$PLATFORM" \
  --output build/dex $(find build/classes -name '*.class')

echo "== упаковка classes.dex =="
cp build/base.apk build/app.apk
if command -v zip >/dev/null 2>&1; then
  (cd build/dex && zip -q ../app.apk classes.dex)
else
  python3 - <<'PY'
import zipfile
with zipfile.ZipFile('build/app.apk', 'a', zipfile.ZIP_DEFLATED) as z:
    z.write('build/dex/classes.dex', 'classes.dex')
PY
fi

echo "== zipalign =="
"$BT/zipalign" -f 4 build/app.apk build/app-aligned.apk

echo "== подпись =="
if [ ! -f debug.keystore ]; then
  keytool -genkeypair -keystore debug.keystore -alias androiddebugkey \
    -storepass android -keypass android -keyalg RSA -keysize 2048 \
    -validity 10000 -dname "CN=Android Debug,O=Android,C=US"
fi
"$BT/apksigner" sign --ks debug.keystore --ks-pass pass:android \
  --key-pass pass:android --min-sdk-version 24 \
  --out build/tgsocks.apk build/app-aligned.apk

"$BT/apksigner" verify --print-certs build/tgsocks.apk | head -5 || true
echo "== готово =="
ls -lh build/tgsocks.apk
