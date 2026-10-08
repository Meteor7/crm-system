# CRM HTTPS reverse proxy

Production serves the CRM at `https://crm.example.invalid`. Nginx on the host is the only
TLS termination point: port 80 redirects to HTTPS, and port 443 forwards the CRM UI, API and
Socket.IO to the Compose frontend on loopback. The Compose stack itself stays HTTP-only. The
backend trusts the scheme the frontend forwards (`FORWARDED_ALLOW_IPS` in
`backend/compose.yaml`), so Frappe marks its cookies `Secure` behind this proxy.

`crm-https.conf.template` reproduces the production configuration. Rendered with the values
below, it is byte for byte the production host's
`/etc/nginx/conf.d/crm.plancksemicon.cn.conf`, apart from the template's leading comments.
`backend/tests/https-proxy-contract.ps1` checks the template in the release gate.

| Variable | Production value |
| --- | --- |
| `CRM_DOMAIN` | `crm.example.invalid` |
| `CRM_UPSTREAM` | `127.0.0.1:4174` |
| `TLS_CERTIFICATE` | `/etc/ssl/certs/crm/crm.plancksemicon.cn.crt` |
| `TLS_CERTIFICATE_KEY` | `/etc/ssl/private/crm/crm.plancksemicon.cn.key` |

To rebuild the proxy on a host, install the certificate and private key first (see
`docs/内网系统HTTPS与域名解析SOP.md`), then:

```bash
export CRM_DOMAIN=crm.example.invalid
export CRM_UPSTREAM=127.0.0.1:4174
export TLS_CERTIFICATE=/etc/ssl/certs/crm/crm.plancksemicon.cn.crt
export TLS_CERTIFICATE_KEY=/etc/ssl/private/crm/crm.plancksemicon.cn.key
envsubst '${CRM_DOMAIN} ${CRM_UPSTREAM} ${TLS_CERTIFICATE} ${TLS_CERTIFICATE_KEY}' \
  < deploy/nginx/crm-https.conf.template \
  | sudo tee "/etc/nginx/conf.d/$CRM_DOMAIN.conf" >/dev/null
sudo nginx -t
sudo systemctl reload nginx
```

The frontend must listen on `127.0.0.1:4174` only, so that the LAN reaches the CRM through
Nginx alone. Keep the private key out of this repository.

HSTS is off. The certificate comes from the internal CA and is renewed by hand; with HSTS, an
expired or untrusted certificate would lock users out instead of showing a warning they can
report. The current certificate expires on 2027-09-09.

On the production host, `/etc/nginx/sites-enabled/default.disabled` still links Ubuntu's
default site. Nginx loads every file in `sites-enabled` whatever its name, so
`http://192.168.1.33/` shows the stock welcome page. Removing that link, then `nginx -t` and a
reload, lets the CRM's port-80 server redirect such requests to HTTPS as well.
