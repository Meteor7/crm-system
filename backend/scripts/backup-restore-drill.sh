#!/usr/bin/env bash
set -euo pipefail

source_site="${SOURCE_SITE:-rayher-crm.localhost}"
restore_site="${RESTORE_SITE:-rayher-crm-restore-check.localhost}"
secret_root="/run/crm-local-secrets"

if [[ ! "${source_site}" =~ ^[a-z0-9.-]+$ ]] || [[ ! "${restore_site}" =~ ^[a-z0-9.-]+$ ]]; then
  echo "Site names contain unsupported characters." >&2
  exit 1
fi
if [[ "${source_site}" == "${restore_site}" ]]; then
  echo "Restore drill site must differ from the source site." >&2
  exit 1
fi
root_password="$(cat "${secret_root}/db_root_password")"
admin_password=__import__("os").environ["DEMO_BOOTSTRAP_PASSWORD"]${secret_root}/admin_password")"
if [[ -z "${root_password}" || -z "${admin_password}" ]]; then
  echo "Required restore credentials are empty." >&2
  exit 1
fi

restore_site_created=0
cleanup_restore_site() {
  if [[ "${restore_site_created}" == 1 && -d "sites/${restore_site}" ]]; then
    if [[ -f "sites/${restore_site}/site_config.json" ]]; then
      if ! bench drop-site "${restore_site}" \
        --db-root-password "${root_password}" \
        --force --no-backup >/dev/null; then
        if [[ -f "sites/${restore_site}/site_config.json" ]]; then
          echo "Restore site cleanup failed before the site was dropped." >&2
          return 1
        fi
      fi
    fi
    for _attempt in $(seq 1 20); do
      if [[ -d "sites/${restore_site}" ]]; then
        expected="$(pwd)/sites/${restore_site}"
        resolved="$(readlink -f "sites/${restore_site}")"
        if [[ "${resolved}" != "${expected}" || -L "sites/${restore_site}" ]]; then
          echo "Refusing to remove an unexpected restore residue path." >&2
          return 1
        fi
        while IFS= read -r item; do
          if [[ -L "${item}" ]]; then
            echo "Refusing to remove restore residue containing a symbolic link." >&2
            return 1
          fi
          case "${item}" in
            "${resolved}/indexes"|"${resolved}/indexes/"*) ;;
            *) echo "Refusing to remove unexpected restore residue: ${item}" >&2; return 1 ;;
          esac
        done < <(find "${resolved}" -mindepth 1 -print)
        rm -rf -- "${resolved}"
      fi
      sleep 1
    done
    if [[ -e "sites/${restore_site}" ]]; then
      echo "Restore residue was recreated after the cleanup window." >&2
      return 1
    fi
  fi
}
trap cleanup_restore_site EXIT

if [[ "${CLEANUP_RESTORE_RESIDUE:-false}" == true ]]; then
  if [[ ! -d "sites/${restore_site}" ]]; then
    echo "No restore residue directory exists."
    exit 0
  fi
  restore_site_created=1
  cleanup_restore_site
  restore_site_created=0
  echo "Validated restore index residue removed."
  exit 0
fi
if [[ -e "sites/${restore_site}" ]]; then
  echo "Restore drill site already exists; refusing to overwrite it." >&2
  exit 1
fi

bench --site "${source_site}" backup --with-files --compress >/dev/null
backup_dir="sites/${source_site}/private/backups"
db_backup="$(find "${backup_dir}" -maxdepth 1 -type f -name '*-database.sql.gz' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
public_backup="$(find "${backup_dir}" -maxdepth 1 -type f -name '*-files.tgz' ! -name '*-private-files.tgz' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
private_backup="$(find "${backup_dir}" -maxdepth 1 -type f -name '*-private-files.tgz' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
for backup in "${db_backup}" "${public_backup}" "${private_backup}"; do
  if [[ -z "${backup}" || ! -s "${backup}" ]]; then
    echo "A required backup artifact is missing or empty." >&2
    exit 1
  fi
done

restore_site_created=1
bench new-site "${restore_site}" \
  --db-root-password "${root_password}" \
  --admin-password "${admin_password}" \
  --no-mariadb-socket >/dev/null
bench --site "${restore_site}" restore "${db_backup}" \
  --db-root-password "${root_password}" \
  --with-public-files "${public_backup}" \
  --with-private-files "${private_backup}" >/dev/null
bench --site "${restore_site}" migrate >/dev/null

source_company="$(bench --site "${source_site}" execute frappe.db.count --args '["Company"]' | tail -1)"
restored_company="$(bench --site "${restore_site}" execute frappe.db.count --args '["Company"]' | tail -1)"
if [[ "${source_company}" != "${restored_company}" ]]; then
  echo "Restored Company count does not match the source." >&2
  exit 1
fi
schema_count="$(bench --site "${restore_site}" execute frappe.db.count --args '["DocType", {"name":"CRM Notification Event"}]' | tail -1)"
if [[ "${schema_count}" != 1 ]]; then
  echo "Restored CRM schema verification failed." >&2
  exit 1
fi
source_private="$(find "sites/${source_site}/private/files" -type f | wc -l)"
restored_private="$(find "sites/${restore_site}/private/files" -type f | wc -l)"
if [[ "${source_private}" != "${restored_private}" ]]; then
  echo "Restored private file count does not match the source." >&2
  exit 1
fi

echo "Backup restore drill passed on isolated temporary site: company_count=${restored_company}, private_files=${restored_private}."
