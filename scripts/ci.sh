#!/usr/bin/env bash
# Esegue `make ci` dai soli livelli attivati (CI_TIERS, piano §6.1, OBJ-13).
# Ogni slice estende CI_TIERS quando introduce un livello:
#   SL-00a: lint unit contract scan
#   SL-00b: + db container      SL-01: + web e2e
# Un livello non elencato qui non gira mai in `make ci`.
set -uo pipefail
cd "$(dirname "$0")/.."

CI_TIERS=(lint unit contract scan db container)

declare -A TIER_TARGETS=(
  [lint]="lint"
  [unit]="test-unit"
  [contract]="test-contract"
  [scan]="scan"
  [db]="tier-db"
  [container]="tier-container"
)

ran=() failed=()
for tier in "${CI_TIERS[@]}"; do
  target="${TIER_TARGETS[$tier]:?livello sconosciuto: $tier}"
  echo "=== livello: $tier (make $target) ==="
  if make --no-print-directory "$target"; then ran+=("$tier:OK"); else ran+=("$tier:FAIL"); failed+=("$tier"); fi
done

echo
echo "=== riepilogo make ci ==="
echo "livelli eseguiti: ${ran[*]}"
if ((${#failed[@]})); then echo "FALLITI: ${failed[*]}" >&2; exit 1; fi
echo "tutti i livelli attivati sono verdi"
