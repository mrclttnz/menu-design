# ADR-0018: Accettazione del rischio: `zlib1g` vulnerabile nell'immagine base

- **Stato:** RISK ACCEPTANCE (decisione dell'utente, 2026-11-07).
- **Data:** 2026-11-07.
- **Decisori:** utente (Gestore). Da far rivedere al security-engineer con la chiusura di SL-06a.
- **Requisiti collegati:** SR-076 (scansioni bloccanti in CI, immagini per digest).
- **Scadenza dell'accettazione:** **2026-11-21**. Dopo quella data l'eccezione smette di valere da sola e il livello `container` torna a fallire.

## Contesto
`trivy image` sull'immagine finale (Debian 13.7, `python:3.14-slim` del 2026-11-05) segnala due HIGH su `zlib1g` `1:1.3.dfsg+really1.3.1-1+b1`: **CVE-2026-76844** e **CVE-2026-85091** (CVE-2026-76844 in `gz_write`, CVE-2026-85091 in `gz_vacate`/`gzwrite`/`gzprintf`: funzioni `gz*` di zlib). Debian ha la correzione `1:1.3.dfsg+really1.3.1-1+deb13u1`, ma l'immagine slim non la include ancora. Il nuovo digest ha già corretto `apt` (CVE-2026-109518, 3.0.4).

Alternative:
- **(a)** `apt-get install --only-upgrade zlib1g` nel Dockerfile. Chiude subito, ma la build dipende dal repository Debian del momento.
- **(b)** Aspettare un'immagine base corretta, lasciando rosso il livello `container`.
- **(c)** Eccezione datata (scelta dall'utente).

## Rischio
- **Esposizione (verificata dal security-engineer, docs/reviews/SL-06a-security.md §5):** nell'immagine solo `dpkg-deb` e `libapt-pkg` importano le funzioni `gz*`, e l'app non li esegue (nessun subprocess, uid 10001, filesystem in sola lettura). CPython (`zlib`, `binascii`), libcrypto e le ruote Python usano solo l'API a flusso. Zlib gira su file statici fidati (`gzip.compress()` in `static.py`) e sulle risposte OIDC di Google via TLS. I corpi delle richieste non vengono mai decompressi e le risposte API non sono compresse.
- **Impatto e probabilità:** gravità contestuale bassa (HIGH a monte).

## Controlli
1. **Eccezione limitata ai due ID**, in `.trivyignore.yaml` e usata solo da `trivy image` (non da `trivy config`). Nessuna esclusione per pacchetto o per gravità.
2. **Scadenza automatica il 2026-11-21** con `expired_at`; un test controlla che i due ID siano gli unici e che la data coincida con questo ADR.
3. **Registrata nel debito tecnico** di `docs/STATUS.md`.

## Eventi che riaprono la decisione
- Un'immagine base con `zlib1g` corretto: si aggiorna il digest e si toglie l'eccezione.
- Un uso delle funzioni `gz*` nel codice o nelle dipendenze.
- In ogni caso, la scadenza del 2026-11-21: si rinnova solo con una nuova decisione dell'utente.
