# ADR-0009: Fuso orario per famiglia, giorni come date locali, "oggi" calcolato dal database e identità del pasto

- **Stato:** ACCEPTED (2026-10-19, gate G3, confermato dopo il secondo giro della revisione critica (nessun blocco)). La possibilità di più "Altro pasto" al giorno è una decisione dell'utente.
- **Data:** 2026-10-19
  - revisione 2: identità del pasto con `meal_slot`;
  - revisione 3: OBJ-05 della revisione critica: riuso della riga di un pasto tolto e limite di 5 "Altro pasto" **attivi**, decisione dell'utente del 2026-10-19.
- **Decisori:** architect
- **Requisiti collegati:** FR-034, FR-035, FR-041, FR-060, FR-061, FR-063, NFR-011, ASM-019, ASM-058, ASM-059, KPI-1, KPI-2

## Contesto
Tutte le nozioni di "giorno", "oggi", "passato" e "inizio settimana" si calcolano nel fuso della famiglia (`Europe/Rome` per default, modificabile dall'Amministratore). Cambiare il fuso non ricalcola i dati già registrati (ASM-059). Gli eventi hanno data e ora UTC. I KPI usano le 00:00 del lunedì locali. I client possono avere orologi sbagliati o fusi diversi da quello della famiglia.

## Criteri di decisione
| Criterio | Peso (1-5) |
|---|---|
| Correttezza (cambi d'ora, cambio di fuso, mezzanotte) | 5 |
| Fonte unica di verità | 4 |
| Semplicità | 4 |

## Opzioni considerate
| Criterio | A: `date` locale + fuso IANA + "oggi" calcolato nel DB | B: pasti come istanti UTC, conversione in lettura | C: "oggi" calcolato dal client |
|---|---|---|---|
| Correttezza (5) | 5 | 2 | 2 |
| Fonte unica (4) | 5 | 3 | 1 |
| Semplicità (4) | 4 | 3 | 4 |
| **Totale pesato** | **61** | **34** | **30** |

- **B:** un cambio di fuso sposterebbe i pasti di giorno (viola ASM-059). Un pasto non è un istante.
- **C:** orologi e fusi dei dispositivi non affidabili. "Passato" diventerebbe manipolabile.

## Decisione
**Opzione A.**
- `family.timezone`: nome IANA validato contro `pg_timezone_names`. Il valore di default è `Europe/Rome`.
- **Giorni dei pasti:** il pasto è identificato da (famiglia, `date` locale, tipo di pasto, `meal_slot`). Nessun orario. Vedi "Identità del pasto" qui sotto.
- **Oggi:**
  - si calcola in SQL nella stessa transazione, con `(now() AT TIME ZONE f.timezone)::date`;
  - `ieri` vale `oggi - 1`, `passato` significa `date < oggi`;
  - l'inizio della settimana è `date_trunc('week', oggi)`, cioè il lunedì ISO;
  - "cucinato N giorni fa" è `oggi - ultima_data` in giorni interi (FR-034).
- **Istanti** (eventi, sessioni, registro di sicurezza): `timestamptz` con `now()` del server, in UTC (FR-061).
- **Scadenze locali** (KPI-1: lunedì alle 00:00) convertite in istante con `(lunedì::timestamp AT TIME ZONE f.timezone)`.
- **API:**
  - `GET /api/v1/session` e le viste del piano restituiscono `timezone` e `today`;
  - il client usa `today` per la navigazione e formatta gli istanti con `Intl.DateTimeFormat('it-IT', { timeZone: family.timezone })`, mai con il fuso del dispositivo.
- **Cambio del fuso:**
  - si esegue prima `ensure_frozen` con il fuso vecchio (ADR-0007), poi si aggiorna il fuso;
  - le date già registrate e `frozen_through` non cambiano;
  - se nel nuovo fuso "ieri" risulta precedente a `frozen_through`, quei giorni restano congelati.
- **Fonte dei dati tz:** il database IANA di PostgreSQL, aggiornato dal provider. Il client usa ICU del browser solo per mostrare i dati.

## Identità del pasto (revisione 2)

### Contesto
La revisione 1 identificava il pasto con (famiglia, data, tipo), quindi al massimo un "Altro pasto" al giorno (`docs/03-ux.md` O-05). L'utente ha deciso il 2026-10-18:
- **più "Altro pasto" nello stesso giorno, ciascuno con un nome libero** (per esempio "Aperitivo", "Dopocena");
- interfaccia in M2, **modello dei dati da M0**, così non serve una migrazione delle chiavi più avanti.

Colazione, Pranzo, Merenda e Cena restano al massimo uno per giorno.

### Opzioni
| Criterio (peso) | A: chiave naturale + `meal_slot` | B: UUID surrogato per ogni pasto | C: tabella separata per i pasti extra |
|---|---|---|---|
| Compatibilità con il modello (presenze, eventi, FK composite, pasti di default senza riga) (5) | 4 | 2 | 3 |
| Storia non ambigua (cronologia, congelamento) (4) | 5 | 5 | 4 |
| Semplicità dell'API (3) | 4 | 3 | 2 |
| Pasti "virtuali" (default senza riga) (4) | 5 | 2 | 4 |
| **Totale pesato** | **72** | **47** | **53** |

- **B:** un pasto di default senza riga non ha un ID finché non viene scritto. Servirebbe materializzare ogni pasto o mappare (data, tipo) → ID ovunque.
- **C:** due modelli di pasto in tutte le query (piano, presenze, eventi, copia).

### Decisione: opzione A, allineata a `docs/05-data.md` v2
La definizione autorevole delle colonne è in `docs/05-data.md` v2. Questo ADR ne fissa le regole architetturali, senza una chiave diversa.
- **Chiave:** il pasto è identificato da (famiglia, `meal_date`, `meal_type`, `meal_slot`). `meal_slot smallint NOT NULL` fa parte della chiave di `meal`, di `meal_item`, di `attendance` e della chiave degli eventi di modifica (ADR-0012):
  - per `breakfast`, `lunch`, `snack` e `dinner` vale sempre `0`;
  - per `other` vale da `0` a `4`, quindi al massimo **5 "Altro pasto" per giorno** (ASM-068).
- **"Altro pasto" di default:** se `other` è tra i pasti di default della famiglia, il pasto di default del giorno è lo slot `0`.
- **Togliere e rimettere un pasto (OBJ-05, decisione dell'utente), per ogni tipo e ogni slot:**
  - togliere un pasto lascia la riga con `presence='removed'` (nessuna cancellazione, nessun problema ABA delle versioni);
  - **rimettere un pasto tolto riusa la sua riga:**
    - `presence` passa da `removed` a `added`;
    - `content_version` cresce di 1;
    - il contenuto riparte vuoto (voci, nome, stato speciale);
    - **ospiti azzerati:** `guests_count = 0`, nota vuota, `guests_version` cresce di 1;
    - **presenze:** le eccezioni di presenza esplicite di quel pasto si cancellano, cioè tornano alla regola (valore `NULL`, versione + 1). Questo vale **solo per i giorni non congelati**. Nei giorni congelati le righe `frozen` e `correction` restano, perché il passato non cambia senza una correzione esplicita (ADR-0007);
  - l'operazione produce i normali eventi di modifica, quindi la cronologia distingue le due "vite" del pasto per istante.
- **"Altro pasto" aggiunti a un giorno:**
  - al massimo **5 "Altro pasto" attivi** (`presence <> 'removed'`) per giorno (ASM-068, decisione dell'utente). Il sesto risponde `quota_exceeded` (`quota=other_meals_per_day`, ADR-0010);
  - il nuovo pasto riusa il primo slot con `presence='removed'`, oppure, se non ce n'è, il primo slot libero da 0 a 4;
  - il calcolo avviene nella transazione, con il lock sulla riga della famiglia o un nuovo tentativo in caso di conflitto sulla chiave.
- **Nome:** `meal.name varchar(40) NULL`, da 1 a 40 caratteri, ammesso solo per `other`.
  - `NULL` si mostra come "Altro pasto" localizzato (chiave i18n `meal.type.other`);
  - il nome è un contenuto dell'utente, non si traduce (ASM-025);
  - fa parte dell'unità (a) "contenuto del pasto": la sua modifica incrementa `content_version` e produce un evento (ADR-0008, ADR-0012).
- **Versioni:** ogni occorrenza (slot) ha i propri `content_version` e `guests_version`. Due "Altro pasto" dello stesso giorno non vanno in conflitto tra loro (FR-044).
- **Presenze:** la settimana tipo non ha `other` (ASM-032), quindi in ogni slot di "Altro pasto" tutti sono presenti per default (FR-050). Le eccezioni e le righe congelate hanno lo slot nella chiave.
- **Congelamento (ADR-0007):** `effective_meals` restituisce (data, tipo, slot). Al congelamento si materializzano anche gli "Altro pasto" aggiunti, ciascuno con il suo slot.
- **Sposta, scambia, copia (FR-042, FR-043):**
  - l'origine e la destinazione si indicano con (data, tipo, slot);
  - copiare un giorno copia anche i suoi "Altro pasto" con il loro nome, in nuovi slot del giorno di destinazione (estende AC-026.4).
- **API:**
  - le risorse del pasto sono `/api/v1/meals/{date}/{mealType}/{slot}`, con `slot = 0` per i tipi standard;
  - le risposte includono `mealType`, `slot` e `name`;
  - in M0 e M1 l'interfaccia usa solo lo slot `0`, ma il server applica già le regole generali.
- **Rotte del frontend (riconciliazione con `docs/03-ux.md`):**
  - la rotta della SPA `/piano/:data/:pastoId` resta;
  - `pastoId` è un identificativo **solo del client**, ricavato in modo biunivoco da tipo e slot:
    - il tipo da solo per lo slot `0` (per esempio `cena`, `altro`), così gli indirizzi di M0 e M1 non cambiano;
    - `<tipo>-<slot>` per gli slot da 1 a 4 (per esempio `altro-2`);
  - il client converte `pastoId` in (`mealType`, `slot`) per chiamare l'API. Il server non conosce `pastoId`;
  - un `pastoId` non valido mostra `error.notFound`.

### Azioni per gli altri ruoli
- **product-analyst:** nuovo FR (più "Altro pasto" al giorno con nome libero, UI M2, modello M0), con ASM-068 (massimo 5 al giorno), chiusura di Q-024 di `docs/03-ux.md` (risposta B estesa) e aggiornamento di ASM-025.
- **data-architect:** fatto in `docs/05-data.md` v2. Questo ADR è allineato.
- **ux-designer:** O-05 superata. Interfaccia per aggiungere, nominare e togliere gli "Altro pasto" in M2. Formato di `pastoId` come sopra.

## Conseguenze
- Positive: una sola definizione di "oggi", immune agli orologi dei client. I cambi d'ora non toccano le date dei pasti.
- Negative e costi: il client deve ottenere `today` dal server, e dopo la mezzanotte deve aggiornarlo, per esempio a ogni ritorno in primo piano dell'app.
- Azioni successive: il tester simula l'orologio del database o del server attorno alla mezzanotte, nelle notti dei cambi d'ora (ultima domenica di marzo e di ottobre) e al cambio di fuso.

## Quando rivedere
Se si introducono famiglie distribuite su più fusi, oppure orari dei pasti.
