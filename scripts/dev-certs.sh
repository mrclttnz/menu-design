#!/usr/bin/env bash
# Genera CA e certificato server usa e getta per il PostgreSQL locale (compose.yaml) in
# db/dev-certs/ (ignorata da git). L'app impone sslmode=verify-full (SR-075): il certificato
# vale per localhost, 127.0.0.1 e ::1. La chiave della CA viene eliminata dopo la firma.
# Genera anche la password dell'utente `postgres` del cluster locale (mai nel repository).
# Idempotente: non rigenera nulla se i file esistono; FORCE=1 rigenera tutto.
set -euo pipefail
cd "$(dirname "$0")/.."

dir="db/dev-certs"
if [[ -z "${FORCE:-}" && -f $dir/ca.crt && -f $dir/server.crt && -f $dir/server.key && -f $dir/admin-password ]]; then
  exit 0
fi

command -v openssl >/dev/null || { echo "ERRORE: openssl non trovato" >&2; exit 2; }
rm -rf "$dir"
mkdir -p "$dir"
chmod 700 "$dir"
umask 077

openssl ecparam -name prime256v1 -genkey -noout -out "$dir/ca.key"
openssl req -x509 -new -key "$dir/ca.key" -sha256 -days 825 \
  -subj "/CN=menu-design dev CA" -out "$dir/ca.crt"

openssl ecparam -name prime256v1 -genkey -noout -out "$dir/server.key"
openssl req -new -key "$dir/server.key" -subj "/CN=localhost" -out "$dir/server.csr"
printf 'subjectAltName=DNS:localhost,IP:127.0.0.1,IP:::1\nextendedKeyUsage=serverAuth\nbasicConstraints=CA:FALSE\n' \
  >"$dir/server.ext"
openssl x509 -req -in "$dir/server.csr" -CA "$dir/ca.crt" -CAkey "$dir/ca.key" -CAcreateserial \
  -sha256 -days 825 -extfile "$dir/server.ext" -out "$dir/server.crt"

openssl rand -hex 24 >"$dir/admin-password"
rm -f "$dir/ca.key" "$dir/ca.srl" "$dir/server.csr" "$dir/server.ext"
# Il container legge i file da root (bind mount) e li copia con il proprietario `postgres`.
chmod 644 "$dir/ca.crt" "$dir/server.crt"
chmod 600 "$dir/server.key" "$dir/admin-password"
echo "Certificati usa e getta generati in $dir/"
