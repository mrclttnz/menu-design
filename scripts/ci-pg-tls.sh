#!/usr/bin/env bash
# CI: abilita TLS sul servizio postgres di GitHub Actions (non accetta comando o volumi).
# Genera i certificati usa e getta (scripts/dev-certs.sh), li copia nel container e ricarica la
# configurazione: `ssl` si applica con reload. Uso: scripts/ci-pg-tls.sh <nome-container>
set -euo pipefail
cd "$(dirname "$0")/.."
name="${1:?uso: ci-pg-tls.sh <container>}"

./scripts/dev-certs.sh
docker exec -u root "$name" install -d -m 0700 -o postgres -g postgres /tls
docker cp db/dev-certs/server.crt "$name:/tls/server.crt"
docker cp db/dev-certs/server.key "$name:/tls/server.key"
docker exec -u root "$name" chown postgres:postgres /tls/server.crt /tls/server.key
docker exec -u root "$name" chmod 0644 /tls/server.crt
docker exec -u root "$name" chmod 0600 /tls/server.key
for setting in "ssl_cert_file='/tls/server.crt'" "ssl_key_file='/tls/server.key'" \
  "ssl_min_protocol_version='TLSv1.3'" "max_connections=200" "ssl=on"; do
  docker exec -u postgres "$name" psql -U postgres -v ON_ERROR_STOP=1 \
    -c "alter system set ${setting%%=*} = ${setting#*=}"
done
# max_connections richiede un riavvio: riavvia il container (poi ssl e attivo).
docker restart "$name" >/dev/null
for _ in $(seq 1 40); do
  if docker exec "$name" pg_isready -U postgres >/dev/null 2>&1; then
    [ "$(docker exec -u postgres "$name" psql -U postgres -Atc "show ssl")" = on ] && echo "PostgreSQL con TLS pronto" && exit 0
  fi
  sleep 1
done
echo "ERRORE: PostgreSQL non torna pronto dopo il riavvio" >&2
exit 1
