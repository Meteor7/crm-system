#!/usr/bin/env bash
# Behind the host's TLS proxy, Frappe marks its cookies Secure only when the backend sees
# an HTTPS request: the frontend must pass X-Forwarded-Proto on, and gunicorn must trust it
# (FORWARDED_ALLOW_IPS in backend/compose.yaml). A plain HTTP request keeps ordinary
# cookies, so stacks served without TLS still sign in.
set -euo pipefail
base_url=${1:?usage: forwarded-https.sh BASE_URL}
headers() {
  curl --silent --show-error --fail --max-time 30 --dump-header - --output /dev/null "$@" "$base_url/api/method/ping"
}
forwarded_headers=$(headers --header 'X-Forwarded-Proto: https')
plain_headers=$(headers)
forwarded=$(grep -i '^set-cookie: sid=' <<<"${forwarded_headers//$'\r'/}" || true)
plain=$(grep -i '^set-cookie: sid=' <<<"${plain_headers//$'\r'/}" || true)
[[ -n $forwarded && -n $plain ]] || { echo 'The ping response set no session cookie.' >&2; exit 1; }
shopt -s nocasematch
[[ $forwarded == *'; secure'* ]] || { echo 'A request forwarded as HTTPS got a session cookie without Secure.' >&2; exit 1; }
[[ $plain != *'; secure'* ]] || { echo 'A plain HTTP request got a Secure session cookie.' >&2; exit 1; }
echo 'Session cookie: Secure when forwarded as HTTPS, ordinary over plain HTTP.'
