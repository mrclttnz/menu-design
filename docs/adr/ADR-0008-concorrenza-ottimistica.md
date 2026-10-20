# ADR-0008: Concorrenza ottimistica con versione per unità e precondizioni HTTP (`ETag`, `If-Match`, `412`)

- **Stato:** ACCEPTED (2026-10-19, gate G3, confermato dopo il secondo giro della revisione critica (nessun blocco))
- **Data:** 2026-10-18. Precisazione del 2026-10-19 (G4, Q-T1): `If-Match` malformato. Precisazione del 2026-10-20: `params.units[]` nel `412` su più unità.
- **Decisori:** architect. Revisione del data-architect e della UX.
- **Requisiti collegati:** FR-041, FR-042, FR-043, FR-044, FR-046, FR-061, US-027 (AC-027.1…7), NFR-015

## Contesto
FR-044 definisce le unità di modifica:
- (a) contenuto di un pasto;
- (b) presenza di una persona a un pasto;
- (c) ospiti di un pasto;
- (d) scheda di un piatto (campi, fonti, tag, stato);
- (e) settimana tipo di una persona;
- in più, il gusto di una persona su un piatto.

Un salvataggio su un'unità cambiata dopo la lettura non deve sovrascrivere in silenzio: deve mostrare il conflitto e offrire "ricarica" o "sovrascrivi". Unità diverse, anche dello stesso pasto, non vanno in conflitto. Sovrascrivere registra entrambe le modifiche nella cronologia.

## Criteri di decisione
| Criterio | Peso (1-5) |
|---|---|
| Aderenza a FR-044 | 5 |
| Robustezza | 4 |
| Semplicità | 4 |
| API riutilizzabile da client nativi | 3 |

## Opzioni considerate
| Criterio | A: versione intera per unità + `If-Match` | B: confronto di `updated_at` | C: ultima scrittura vince | D: lock pessimistici o "lease" di modifica | E: sincronizzazione in tempo reale (CRDT) |
|---|---|---|---|---|---|
| FR-044 (5) | 5 | 4 | 1 | 3 | 4 |
| Robustezza (4) | 5 | 3 | 2 | 3 | 4 |
| Semplicità (4) | 4 | 4 | 5 | 2 | 1 |
| Client nativi (3) | 5 | 4 | 3 | 2 | 2 |
| **Totale pesato** | **76** | **60** | **42** | **41** | **46** |

- **B:** la precisione degli istanti e gli orologi rendono fragile il confronto.
- **C:** viola FR-044.
- **D:** lock lasciati appesi sui telefoni, complessità.
- **E:** sproporzionato.

## Decisione
**Opzione A.**

- **Versioni:** ogni unità ha una colonna `version integer` che parte da 1 e cresce di 1 a ogni scrittura, più `modified_by` e `modified_at`, che servono al messaggio di conflitto e all'indicatore di FR-046.

  | Unità | Dove sta la versione |
  |---|---|
  | (a) Contenuto del pasto | `content_version` della riga del pasto (famiglia, data, tipo, `meal_slot`, ADR-0009 revisione 2). Copre piatti, voci libere, stato speciale, presenza del pasto nel giorno e nome di un "Altro pasto". |
  | (b) Presenza | Riga di presenza esplicita (famiglia, data, tipo, persona), ADR-0007 |
  | (c) Ospiti | `guests_version` sulla riga del pasto (famiglia, data, tipo, `meal_slot`), separata dal contenuto. Ogni "Altro pasto" (slot) ha le proprie versioni di contenuto e ospiti. |
  | (d) Scheda del piatto | `version` del piatto. Una modifica a fonti o tag la incrementa. |
  | (e) Settimana tipo | `version` della settimana tipo della persona |
  | Gusto | `version` della riga (piatto, persona) |

- **Unità che non esistono ancora** (pasto senza righe, presenza senza eccezione, gusto "sconosciuto"):
  - la versione esposta è `0`;
  - la scrittura con `If-Match: "0"` è un `INSERT … ON CONFLICT DO NOTHING`;
  - se nessuna riga viene inserita, si risponde `412`.
- **Pasto tolto e rimesso** (ADR-0009, OBJ-05): si riusa la stessa riga, e `content_version` continua a crescere. Una scrittura con la versione letta prima della rimozione riceve `412`, senza problema ABA.
- **Protocollo HTTP:**
  - le letture espongono `version` nel corpo per ogni unità, e `ETag` sulle risorse singole;
  - le scritture su un'unità richiedono `If-Match`. Senza, la risposta è `428`;
  - **formato ammesso (Q-T1, 2026-10-19):** solo un ETag forte con un intero non negativo tra virgolette, `"<n>"` (regex `^"(0|[1-9][0-9]{0,17})"$`: al massimo 18 cifre, sempre entro il `bigint` di PostgreSQL, THR-107). Qualsiasi altro valore dà `422 validation` con `errors: [{field: "If-Match", code: "invalid_value"}]`, senza scrittura né evento. Rientrano nel caso: `abc`, numeri negativi, ETag deboli (`W/"3"`), valori senza virgolette, elenchi (`"1", "2"`), header vuoto e `*`. **`*` non è mai supportato**, perché ogni scrittura deve dichiarare la versione che ha letto. Solo l'header assente dà `428`;
  - l'aggiornamento è `UPDATE … SET …, version = version + 1 WHERE <chiave> AND family_id = $f AND version = $atteso`. Zero righe aggiornate danno `412` con `problem+json` `code=conflict`, lo stato attuale dell'unità, `modifiedBy` (ID, il nome lo risolve il client) e `modifiedAt`;
  - "Ricarica": il client scarta le modifiche e usa lo stato ricevuto;
  - "Sovrascrivi": il client ripete la richiesta con la versione ricevuta nel `412`. Ogni scrittura riuscita genera il suo evento, quindi la cronologia registra entrambe le modifiche (AC-027.3).
- **Operazioni su più unità** (sposta, scambia, copia, FR-042 e FR-043):
  - il corpo contiene la mappa `expectedVersions` delle unità coinvolte;
  - la transazione applica tutto o niente;
  - il `412` (`code=conflict`) elenca le unità in conflitto in `params.units[]`. Ogni elemento ha `key` (la stessa chiave di `expectedVersions`), `reason`, `current` (stato attuale con la versione), `modifiedBy` e `modifiedAt`. `reason` vale `version_changed` per una versione superata, oppure `choice_required` per una destinazione non vuota senza `mode`. La forma è definita nella tabella di ADR-0010 (2026-10-20, piano §11.3);
  - le scelte "sostituisci, unisci o annulla" (AC-025.4, AC-026.2) sono parametri espliciti della richiesta.
- **Isolamento:** `READ COMMITTED` con `UPDATE` condizionato. Basta, perché la condizione sulla versione è valutata sulla riga aggiornata.

## Conseguenze
- Positive: semantica HTTP standard, riutilizzabile dalle app native. Nessun lock. Granularità esattamente uguale alle unità di FR-044 (AC-027.6 e AC-027.7 sono soddisfatti per costruzione).
- Negative e costi: ogni schermata di modifica deve conservare le versioni lette. La UX deve progettare la finestra di conflitto.
- Azioni successive:
  - la UX definisce il messaggio di conflitto;
  - il data-architect aggiunge le colonne di versione;
  - il tester copre AC-027.1…7 con richieste parallele.

## Quando rivedere
Se arriva la modifica offline (FR-058, fuori dall'MVP): serviranno code di modifiche e risoluzione dei conflitti al rientro, che questo schema già supporta.
