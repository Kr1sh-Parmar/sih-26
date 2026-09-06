#!/usr/bin/env bash
# CLAUDE.md hard rule #3: zero network calls at inspection time. A CDN font,
# an icon sprite or an analytics beacon will surface the moment the cable comes
# out at the demo — which is exactly when it must not.
#
# Only RESOURCE positions count: src=, href=, CSS url(), and fetch/import
# targets. A bare URL inside an error string (React ships one) is inert and is
# not a finding — flagging it would train everyone to ignore this script.
set -u
pattern='(src|href)=["'"'"']https?://|url\(["'"'"']?https?://|(fetch|importScripts)\(["'"'"']https?://'
hits=$(grep -rEoh "$pattern[^"'"'"' )]*" dist/ 2>/dev/null \
  | grep -vE 'https?://(localhost|127\.0\.0\.1)' \
  | grep -vE 'http://www\.w3\.org/' \
  | sort -u)
if [ -n "$hits" ]; then
  echo "check-offline: FAIL — the build fetches from the network:"
  echo "$hits" | sed 's/^/  /'
  exit 1
fi
echo "check-offline: pass — no external resource is fetched by dist/"
