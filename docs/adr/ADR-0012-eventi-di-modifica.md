# ADR-0012: Eventi di modifica registrati dall'applicazione nella stessa transazione, compatti e in sola aggiunta

- **Stato:** ACCEPTED (2026-10-19, gate G3, confermato dopo il secondo giro della revisione critica (nessun blocco))
- **Data:** 2026-10-18 (revisione 3)
  - revisione 2: dettagli Python;
  - revisione 3: autore come persona e formato compatto da M0, decisioni dell'utente del 2026-10-18.
- **Decisori:** utente, architect. Revisione del data-architect e della UX.
- **Requisiti collegati:** FR-041, FR-044, FR-045, FR-046, FR-061, FR-062, FR-064, SR-022, SR-047, SR-057, US-028, US-049 (AC-049.1…4), KPI-1, KPI-2, KPI-5, KPI-7
- **Collegati:** `docs/05-data.md` (tabella `change_event`, §14 stima dello spazio), `docs/03-ux.md` DD-09

## Contesto
Da M0, ogni modifica a contenuto dei pasti, presenze, ospiti, settimana tipo e stato dei piatti registra:
- data e ora UTC;
- autore;
- **ruolo dell'autore in quel momento**;
- oggetto;
- valori prima e dopo.

Le persone si indicano solo con l'identificativo. Un'operazione fallita non lascia eventi. Gli eventi alimentano la cronologia (M1, descrizioni composte nel client secondo DD-09) e i KPI.

`change_event` è la tabella che cresce di più (circa il 45% della crescita, `docs/05-data.md` §14), con il limite di 500 MB di Supabase Free.

## Criteri di decisione
| Criterio | Peso (1-5) |
|---|---|
| Atomicità con la modifica (AC-049.4) | 5 |
| Completezza (nessuna modifica senza evento) | 5 |
| Leggibilità semantica (cronologia, KPI) | 4 |
| Testabilità | 4 |
| Semplicità | 4 |

## Opzioni considerate
| Criterio | A: registrazione applicativa esplicita | B: trigger generici nel database | C: outbox o bus di eventi | D: estensione di audit (pgaudit) |
|---|---|---|---|---|
| Atomicità (5) | 5 | 5 | 3 | 4 |
| Completezza (5) | 4 | 5 | 4 | 3 |
| Leggibilità (4) | 5 | 2 | 4 | 1 |
| Testabilità (4) | 5 | 3 | 3 | 2 |
| Semplicità (4) | 4 | 3 | 1 | 3 |
| **Totale pesato** | **101** | **82** | **67** | **59** |

## Decisione
**Opzione A.**

### Registrazione
- `history.record_change(tx, unit=…, op=…, key=…, before=…, after=…)` è chiamata dai servizi di dominio nella stessa transazione SQLAlchemy della modifica.
- Autore e ruolo vengono dal `RequestContext`. Il ruolo è letto dalla membership nella stessa transazione.

### Autore come persona (decisione dell'utente)
- `actor_kind` ∈ {`person`, `platform_operator`, `system`};
- `actor_person_id` referenzia la riga `person` della famiglia, non l'account;
- quando una persona esce o l'account viene eliminato, la sua riga diventa un tombstone senza nome. La cronologia mostra quindi "ex membro" o "persona eliminata" senza riscrivere eventi e senza dati dell'account (SR-047, AC-016.2);
- il recupero da parte del Gestore usa `actor_kind='platform_operator'` (FR-064).

### Formato compatto da M0 (decisione dell'utente)
- **Solo i campi cambiati:** `before` e `after` contengono solo i campi o le voci cambiati, mai l'intera unità.
- **Contenuto del pasto:** le voci si descrivono come insiemi di differenze:
  - `+` voci aggiunte;
  - `-` voci tolte;
  - `~` voci modificate, con i soli campi cambiati;
  - più gli eventuali cambi di stato speciale o di presenza del pasto.
- **Chiavi JSON brevi:** un dizionario unico in codice (modulo `history.codec`), per esempio `i` (voce), `d` (piatto), `c` (portata), `t` (testo libero), `n` (non cucinato), `p` (posizione), `s` (stato speciale), `pr` (presente), `g` (ospiti), `gn` (nota degli ospiti), `st` (stato del piatto), `r` (ruolo).
- **Versione del formato:** ogni payload ha `"v": 1`. Un cambio di formato aumenta `v`, e il decodificatore gestisce tutte le versioni esistenti (gli eventi di M0 restano leggibili, AC-028.5).
- **Validazione in scrittura:** con modelli Pydantic per (`unit_type`, `op`, `v`). Un payload non conforme fa fallire la transazione.
- **Invertibilità:** per ogni campo o voce cambiati si salvano sia il valore prima sia quello dopo. Così lo stato di un'unità in un istante passato si ricostruisce partendo dallo stato attuale e annullando a ritroso gli eventi successivi. È ciò che serve a KPI-1 (stato del piano alle 00:00 del lunedì) e a KPI-2. Un test di proprietà (Hypothesis) verifica che "stato attuale meno gli eventi successivi a t" coincida con lo stato registrato a t.
- **Risparmio:** stimato al 30-50% di `change_event` (`docs/05-data.md` §14, mitigazione 2), da misurare nella prima slice.

### Fattibilità di DD-09 (descrizioni composte nel client)
La composizione nel client è fattibile, perché ogni evento è strutturato e finito.
- **API:** `GET /api/v1/history` restituisce:
  - gli eventi **decodificati**, con chiavi lunghe e stabili documentate in OpenAPI come unione discriminata per `unitType` e `op`, quindi le chiavi brevi restano interne al server;
  - una mappa `refs` che risolve, al momento della lettura, gli ID della pagina in etichette:
    - persone, compresi i tombstone con `status='former'`;
    - piatti, compresi quelli archiviati, e "piatto eliminato" se l'ID non esiste più;
    - portate: `base_code` da tradurre, oppure il nome personalizzato.
- **Client:**
  - sceglie la chiave i18n `history.<unitType>.<op>`, più chiavi di dettaglio per campo (`history.field.<campo>`);
  - interpola i nomi con ICU;
  - i testi liberi (voci libere, nota degli ospiti, nome di un "Altro pasto") si mostrano così come sono (ASM-025).
- **Quante chiavi servono:** le combinazioni di `unit_type` e `op` sono una ventina. Un test verifica che ogni combinazione dichiarata nei modelli Pydantic abbia una chiave nel catalogo `it` (lo stesso meccanismo degli `ErrorCode`, ADR-0010).
- **Privacy:** il server non salva né restituisce frasi. I nomi non entrano mai nelle righe degli eventi (SR-047).

### Chiave dell'evento
`meal_date`, `meal_type`, `meal_slot` (ADR-0009), `subject_person_id`, `dish_id`, con un vincolo di forma per tipo di unità (`docs/05-data.md`).

### Immutabilità (SR-022, SR-057)
- `menu_app` ha solo `INSERT` e `SELECT`, con la RLS per famiglia (`p_family_select` e `p_family_insert`);
- un trigger rifiuta ogni `UPDATE`;
- la cancellazione avviene solo per cascata con l'eliminazione definitiva della famiglia.

### Completezza (inventario in pytest)
- ogni rotta che modifica un'unità tracciata dichiara `tracks=[...]` in `authz` (`AuthzRoute`, ADR-0002), esposto come `x-authz.tracks`;
- i test d'integrazione che verificano la registrazione sono marcati `@pytest.mark.tracks("<operation_id>")`;
- un test di inventario confronta `app.routes` con i marker raccolti (hook in `conftest.py`);
- una fixture verifica un evento per unità modificata in caso di successo, e nessun evento in caso di fallimento (AC-049.4);
- lo stesso meccanismo, con il marker `cross_family`, copre SR-009 e SR-042.

### Visite settimanali (FR-062)
Tabella `weekly_visit` separata, legata alla persona, con `ON CONFLICT DO NOTHING`.

## Conseguenze
- Positive:
  - eventi semantici, compatti e invertibili, utili a cronologia e KPI;
  - atomicità garantita dalla transazione e immutabilità garantita dai privilegi;
  - nessun testo nel database.
- Negative e costi:
  - il codec e i modelli per versione vanno mantenuti;
  - la ricostruzione di uno stato passato richiede di applicare gli eventi a ritroso. Avviene solo per i KPI, sull'esportazione della famiglia del Gestore, non in linea;
  - la completezza dipende dal test di inventario.
- Azioni successive:
  - il data-architect aggiorna le note di `before` e `after` in `docs/05-data.md`;
  - la UX elenca le chiavi `history.*`;
  - il tester scrive il test di invertibilità.

## Quando rivedere
- Se emergono modifiche senza evento: aggiungere un trigger di controllo.
- Se la tabella supera il 30% dello spazio del database.
