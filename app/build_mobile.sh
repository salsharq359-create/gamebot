#!/usr/bin/env bash
# بناء جيم بوت لأندرويد أو آيفون.
#   ./build_mobile.sh <API_URL> <REALTIME_URL> apk    # أندرويد: يعمل على Windows و macOS و Linux
#   ./build_mobile.sh <API_URL> <REALTIME_URL> ipa    # آيفون: يحتاج macOS مع Xcode وحساب Apple Developer
# مثال:  ./build_mobile.sh https://api.yourdomain.com https://api.yourdomain.com apk
# يتطلب تثبيت Flet CLI: pip install flet-cli==1.0.3
set -euo pipefail
API="${1:?أدخل عنوان API بصيغة https://}"
RT="${2:?أدخل عنوان الخادم الفوري بصيغة https://}"
TARGET="${3:-apk}"
if [[ "$API" != https://* || "$RT" != https://* ]]; then
  echo "خطأ: يجب أن تبدأ العناوين بـ https:// (أندرويد وآيفون يرفضان الاتصال غير المشفّر)." >&2
  exit 1
fi
if [[ "$TARGET" == "ipa" && "$(uname -s)" != "Darwin" ]]; then
  echo "خطأ: بناء ملف الآيفون يحتاج macOS مع Xcode. على هذا الجهاز استخدم apk." >&2
  exit 1
fi
cd "$(dirname "$0")"
printf '{"api_url": "%s", "realtime_url": "%s"}\n' "$API" "$RT" > server.json
flet build "$TARGET" --exclude tests
echo "تم. الملف في build/$TARGET/"
