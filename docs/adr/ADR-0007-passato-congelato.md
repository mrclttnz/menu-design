# ADR-0007: Passato congelato con materializzazione "prima di cambiare" e soglia di congelamento per famiglia

- **Stato:** ACCEPTED (2026-10-19, gate G3, confermato dopo il secondo giro della revisione critica (nessun blocco))
- **Data:** 2026-10-18
- **Decisori:** architect. Revisione del data-architect.
- **Requisiti collegati:** FR-012, FR-036, FR-041, FR-049, FR-050, FR-051, FR-053, FR-060, FR-063, ASM-033, ASM-058, ASM-059, SR-047, US-048

## Contesto
FR-063 chiede che i pasti passati conservino le presenze che avevano, anche se cambiano la settimana tipo o le persone della famiglia. Le correzioni esplicite devono restare possibili. Le presenze dei pasti futuri si ricavano invece dalla settimana tipo (o "sempre presente"), dalle eccezioni e dall'appartenenza alla famiglia dal giorno di ingresso. FR-012 impone che, all'uscita di una persona, si cancellino la sua settimana tipo e le eccezioni future, mentre le presenze passate restano come "ex membro". I requisiti lasciano all'architetto la scelta tra presenze materializzate e settimana tipo versionata.

## Criteri di decisione
| Criterio | Peso (1-5) |
|---|---|
| Correttezza e robustezza (il passato non cambia mai per errore) | 5 |
| Compatibilità con le cancellazioni (FR-012, SR-047) | 5 |
| Semplicità | 4 |
| Prestazioni di lettura | 3 |
| Minimizzazione dei dati | 3 |

## Opzioni considerate
| Criterio | A: materializzazione prima di cambiare, con soglia | B: settimana tipo versionata e periodi di appartenenza | C: righe di presenza generate anche per il futuro | D: ricostruzione dagli eventi |
|---|---|---|---|---|
| Correttezza (5) | 5 | 4 | 4 | 3 |
| Cancellazioni (5) | 5 | 2 | 5 | 2 |
| Semplicità (4) | 4 | 3 | 2 | 1 |
| Prestazioni (3) | 4 | 3 | 5 | 2 |
| Minimizzazione (3) | 4 | 3 | 2 | 4 |
| **Totale pesato** | **90** | **60** | **74** | **47** |

### Opzione A: materializzazione "prima di cambiare"
- Pro:
  - la correttezza non dipende da un job;
  - le letture del futuro restano un calcolo semplice;
  - le cancellazioni di FR-012 non toccano il passato, perché è già materializzato.
- Contro: bisogna chiamare `ensure_frozen` in tutte le operazioni che cambiano gli input (elenco chiuso, verificato da test).

### Opzione B: settimana tipo versionata
- Contro:
  - all'uscita di una persona FR-012 cancella la settimana tipo, quindi il passato andrebbe comunque fotografato;
  - query temporali in ogni lettura;
  - le versioni storiche della settimana tipo si conservano a lungo.

### Opzione C: righe generate anche per il futuro
- Contro: orizzonte futuro illimitato (FR-035). Rigenerazioni a ogni cambio della settimana tipo.

### Opzione D: ricostruzione dagli eventi
- Contro: complessità alta, letture lente, e gli eventi non sono pensati come fonte di verità.

## Decisione
**Opzione A.**

### Elementi del modello
Il dettaglio dello schema lo definisce il data-architect.
- La famiglia ha `frozen_through date`: l'ultimo giorno locale già congelato.
- Una tabella di presenze esplicite per (famiglia, data, tipo di pasto, `meal_slot`, persona). Lo slot distingue più "Altro pasto" nello stesso giorno (ADR-0009, revisione 2), con `present` e `source` ∈ {`exception`, `frozen`, `correction`}. Contiene:
  - le eccezioni sui pasti futuri;
  - le presenze congelate dei giorni passati;
  - le correzioni sui passati.
- Al congelamento si materializza anche l'**elenco dei pasti esistenti in quel giorno** (pasti di default di allora, più quelli aggiunti, meno quelli tolti). Così un cambio dei pasti di default non altera il passato.

### Regola di calcolo
Per un pasto non congelato, la presenza di una persona è determinata così:
- se la persona non è membro in quel giorno (`joined_on > giorno` oppure uscita), non conta;
- altrimenti, se esiste una riga esplicita, vale la riga;
- altrimenti, per "Altro pasto", la persona è presente;
- altrimenti vale la cella della settimana tipo;
- altrimenti la persona è presente.

`joined_on` è la data locale di ingresso, quindi la persona conta in tutti i pasti di quel giorno (ASM-058). Per un profilo vale il giorno di creazione.

### Il congelamento
`ensure_frozen(tx, family)` funziona così:
1. blocca la riga della famiglia (`FOR UPDATE`);
2. calcola `ieri` nel fuso della famiglia (ADR-0009);
3. per i giorni in (`frozen_through`, `ieri`] scrive i pasti esistenti e le righe `frozen` per le celle senza riga esplicita, usando gli input **attuali**;
4. aggiorna `frozen_through`.

### Invariante e sue chiamate
**Invariante:** gli input del calcolo (settimana tipo, appartenenze, pasti di default, fuso) non cambiano mai per un giorno ≤ ieri che non sia già congelato.

Per garantirla, `ensure_frozen` si chiama, nella stessa transazione e **prima** della modifica, in ogni operazione che cambia un input:
- modifica della settimana tipo;
- ingresso, uscita o rimozione di una persona;
- creazione o eliminazione di un profilo;
- collegamento di un profilo (M2);
- cambio dei pasti di default;
- cambio del fuso (ASM-059: dopo il cambio, `frozen_through` non si ricalcola).

### Altri aspetti
- **Letture:** i giorni ≤ `frozen_through` si leggono dalle righe. I giorni successivi, compresi i passati non ancora congelati, si calcolano con la regola. Per l'invariante il risultato coincide con quello che il congelamento scriverebbe.
- **Worker:** ogni notte, dopo la mezzanotte locale, congela il giorno precedente di ogni famiglia (ADR-0013). Serve solo a mantenere le letture semplici, non alla correttezza.
- **Correzioni (FR-041, FR-051):** sui giorni passati aggiornano la riga (`source = correction`), con concorrenza ottimistica sull'unità "presenza di una persona a un pasto" (ADR-0008) e un evento di modifica (ADR-0012).
- **Uscita o rimozione (FR-012):** si eseguono `ensure_frozen`, poi la cancellazione di settimana tipo, gusti ed eccezioni future. La persona diventa un tombstone senza nome ("ex membro"), referenziato dalle righe passate (SR-047).

## Conseguenze
- Positive: il passato è immutabile per costruzione. Il futuro si calcola in modo semplice. Il job non è critico.
- Negative e costi: circa 100 righe al giorno per famiglia al massimo (5 pasti per 20 persone). L'elenco delle operazioni che chiamano `ensure_frozen` va mantenuto.
- Azioni successive:
  - il data-architect modella le tabelle;
  - il tester scrive un test di proprietà: sequenze casuali di modifiche e avanzamenti del giorno, il passato non cambia salvo correzioni esplicite;
  - test attorno alla mezzanotte, ai cambi d'ora e al cambio di fuso.

## Quando rivedere
Se si introducono altri input del calcolo delle presenze (per esempio regole stagionali), oppure se servono viste storiche della settimana tipo.
