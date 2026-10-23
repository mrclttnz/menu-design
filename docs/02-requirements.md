# Requisiti: Menu Design

> Documento di proprietà del product-analyst. Versione 2, 2026-10-18.
> **Stato: Approvato (G2, 2026-10-18), con le modifiche CHG-001 … CHG-019 (ASM-067 … ASM-070 confermate al gate G3 il 2026-10-19; ASM-071 superata) decise dall'utente durante la fase di design P3 (2026-10-18), e CHG-020 (login con email e password rinviato dopo M2) decisa dall'utente durante il gate G4 (2026-10-19).** Vedi la sezione "Modifiche dopo G2" in fondo al documento.
>
> Fonti:
> - visione approvata `docs/01-vision.md` (rev. 3, gate G1 approvato il 2026-10-17), citata come "visione";
> - note di elicitazione con le decisioni dell'utente del 2026-10-18, citate come "elic. 2026-10-18";
> - decisioni dell'utente sulle obiezioni della revisione critica e sulle proposte del security engineer, 2026-10-18, citate come "dec. 2026-10-18" con il riferimento (OBJ-nn, SD-n);
> - `security-standard.md` di Bottega, citato come "SS §n".
>
> Le ipotesi della visione (ASM-001 … ASM-025) restano valide e non vengono rinumerate. Qui sono richiamate solo quando servono. Le nuove ipotesi partono da ASM-026.
>
> Gli identificativi sono stabili: un elemento eliminato resta nel documento, marcato `~~RIMOSSO~~` con il motivo.
>
> Novità della versione 2:
> - definizione di "passato" e regola del passato congelato;
> - invariante "almeno un Amministratore" anticipata a M1, con comando di recupero del Gestore;
> - eventi di modifica registrati da M0;
> - nuove priorità per M2;
> - integrazione delle SR del security engineer (SR-033 … SR-063) e delle decisioni SD-1 … SD-7;
> - correzioni della revisione critica.

## Glossario

| Termine | Definizione |
|---|---|
| Famiglia | Gruppo che condivide archivio piatti, piano dei pasti e presenze. È l'unità di isolamento dei dati (tenant). |
| Fuso orario della famiglia | Fuso orario salvato per ogni famiglia, `Europe/Rome` per default. Tutte le nozioni di "giorno", "oggi", "passato" e "inizio settimana" si calcolano in questo fuso. |
| Oggi | Il giorno di calendario corrente nel fuso orario della famiglia. |
| Pasto passato | Pasto di un giorno precedente a oggi. I pasti di oggi non sono ancora passati. I pasti passati restano sempre modificabili, nei limiti del ruolo, e ogni modifica entra nella cronologia. |
| Persona della famiglia | Chiunque faccia parte di una famiglia, con o senza account. Ha presenze, settimana tipo e gusti. Conta nei pasti a partire dal giorno in cui è entrata nella famiglia. |
| Account | Identità di accesso di una persona. Per Google è identificata dalla coppia (provider, `sub`), mai dall'email. Nell'MVP (M0-M2) l'unico metodo di accesso è Google. L'account con email e password è rinviato al backlog dopo M2 (FR-002, CHG-020). Solo per chi ha dichiarato almeno 14 anni. Nel modello dati può appartenere a più famiglie, ma l'interfaccia dell'MVP ne mostra una sola (ASM-002). |
| Profilo senza account | Persona della famiglia che non accede all'app, per esempio un minore di 14 anni. È gestita da Amministratore o Pianificatore. Chi la crea dichiara di esercitare la responsabilità genitoriale o di averne il consenso. |
| Ruolo | Insieme fisso di permessi di un account in una famiglia: Amministratore, Pianificatore o Membro. Qualunque account (quindi dai 14 anni) può avere qualunque ruolo. Un invito può assegnare al massimo Pianificatore. |
| Gestore della piattaforma | Il proprietario del prodotto. Agisce solo tramite comandi da console e non legge i contenuti delle famiglie. |
| Ospite | Persona esterna alla famiglia, registrata solo come numero più una nota libera su un pasto. Non ha gusti né profilo. |
| Tipo di pasto | Colazione, Pranzo, Merenda, Cena, Altro pasto. In un giorno ci possono essere più "Altro pasto", ognuno con un nome libero, "Altro pasto" per default (FR-072, CHG-003). |
| Punteggio priorità | Numero intero da 1 a 10 associato a un piatto, unico per la famiglia, 5 per default. Indica quanto la famiglia vuole proporre quel piatto (FR-070, CHG-001). |
| Ordinamento preferito | Ordine dei piatti scelto da ogni account per il selettore e l'archivio: nome, priorità oppure non cucinato da più tempo. È salvato sul server (FR-071, CHG-002). |
| Ultima visita | Data e ora dell'ultima apertura del piano da parte di un account. Ne esiste una sola per account, conservata sul server e sovrascritta a ogni visita. Serve a FR-046 (FR-062, CHG-004). |
| Pasto di default | Tipo di pasto che la famiglia vuole vedere ogni giorno nel piano. |
| Pasto | Un tipo di pasto in un giorno specifico, per esempio "Cena di martedì 3 novembre". |
| Contenuto di un pasto | Piatti assegnati, voci libere, stato speciale, e la presenza stessa del pasto nel giorno (aggiunto o tolto). |
| Portata | Categoria di un piatto. Lista base: antipasto, primo, secondo, contorno, piatto unico, dolce, bevanda, altro. La famiglia può aggiungerne altre. Un piatto ha una o più portate. |
| Piatto | Elemento dell'archivio della famiglia, con nome, portate, stato, note, tag, tempo di preparazione, fonti della ricetta e gusti. |
| Stato del piatto | "da provare" oppure "collaudato". Il cambio di stato è sempre manuale (ASM-017). |
| Piatto archiviato | Piatto già usato in un piano e poi tolto dalle scelte. Resta visibile nei piani passati e nello storico e si può ripristinare. |
| Voce libera | Testo inserito in un pasto senza collegarlo a un piatto dell'archivio, per esempio "avanzi di ieri". |
| Pasto speciale | Pasto marcato "fuori casa", "ristorante" o "saltato". Conta come pianificato, ma non si cucina niente. |
| Cucinato | Un piatto è cucinato in un pasto passato, non speciale, in cui era assegnato e non è marcato "non cucinato" (ASM-003). |
| Ultima volta cucinato | Data più recente in cui il piatto risulta cucinato. È ricavata dal piano. |
| Gusto | Valutazione di una persona su un piatto: piace, neutro o non piace. Se non è stata data, il gusto è "sconosciuto". |
| Fonte della ricetta | Riferimento a dove si trova la ricetta: tipo (link, libro, rivista, altro), riferimento (URL, oppure titolo e pagina) e nota. Un piatto può averne più di una. |
| Tag | Etichetta libera definita dalla famiglia, per esempio "veloce", "vegetariano", "estivo". |
| Tempo di preparazione | Fascia: meno di 30 minuti, 30-60 minuti, più di 60 minuti. |
| Piatto principale | Assegnazione di un piatto in un pasto con portata primo, secondo o piatto unico (ASM-026, confermata). |
| Settimana tipo | Per ogni persona, giorno della settimana e tipo di pasto (escluso "Altro pasto"): presente o assente. Una modifica vale da oggi in avanti. |
| Eccezione di presenza | Presenza o assenza registrata su un singolo pasto, diversa da quanto dice la settimana tipo. |
| Coperti | Persone della famiglia presenti a un pasto più ospiti. |
| Evento di modifica | Registrazione di una modifica a piano, presenze, ospiti o stato di un piatto: data e ora, autore, ruolo dell'autore in quel momento, oggetto e valori prima e dopo. Alimenta la cronologia e i KPI. |
| Visita settimanale | Indicazione che un account ha aperto il piano almeno una volta in una certa settimana. Serve solo per KPI-7 (FR-062). |
| Piatto pianificato almeno una volta | Piatto che è stato assegnato almeno una volta a un pasto. Il dato è permanente: resta vero anche se il piatto viene poi tolto da tutti i pasti (Q-028). |
| Codice di creazione | Codice monouso emesso dal Gestore che permette di creare una nuova famiglia. |
| Link di invito | Link monouso, valido 7 giorni e revocabile, per entrare in una famiglia esistente come Membro o Pianificatore. |
| Cronologia modifiche | Vista, per la famiglia, degli eventi di modifica: chi, quando, con quale ruolo, cosa. |
| Registro di sicurezza | Registro interno, in sola aggiunta, degli eventi rilevanti per la sicurezza. Non è visibile alle famiglie. |
| Riautenticazione | Autenticazione completata da non più di 10 minuti, richiesta per le operazioni critiche (SR-039). |
| Periodo di ripensamento | I 7 giorni tra la richiesta di eliminazione di una famiglia e la cancellazione definitiva (ASM-022). |
| M0 / M1 / M2 | Milestone di rilascio dell'MVP (visione). |
| Apertura al pubblico | Milestone successiva all'MVP. La sua condizione di ingresso è ASM-011. |

## Ruoli e permessi

Legenda:
- **Sì** = consentito.
- **No** = negato dal server.
- **Propri** = solo sui propri dati.
- **Se presente** = solo per i pasti a cui la persona risulta presente.
- **R** = richiede riautenticazione (SR-039).
- **n/a** = non applicabile.

Note sui ruoli:
- I permessi dipendono **solo dal ruolo**, non dall'età: un account dai 14 anni può avere qualunque ruolo (Q-012).
- Il **profilo senza account** non accede all'app. Ogni sua colonna vale n/a, e le azioni sui suoi dati le svolgono Amministratore o Pianificatore.
- Il **Gestore** agisce solo da console e non legge i contenuti delle famiglie.
- **Pasti passati:** sono sempre modificabili da tutti, nei limiti di questa matrice (dec. 2026-10-18, OBJ-01).

### Piattaforma e accesso

| Azione \ Ruolo | Anonimo | Gestore (console) | Amministratore | Pianificatore | Membro | Profilo senza account |
|---|---|---|---|---|---|---|
| Emettere, elencare, revocare codici di creazione | No | Sì | No | No | No | n/a |
| Creare la famiglia iniziale (bootstrap M0) | No | Sì | No | No | No | n/a |
| Aggiungere un account come Amministratore (recupero, FR-064) | No | Sì, su richiesta dall'email dell'account, passata come hash (CHG-016) | No | No | No | n/a |
| Avviare un'esportazione su richiesta durante la beta (FR-065) | No | Sì, senza leggere il contenuto | No | No | No | n/a |
| Leggere i contenuti di una famiglia | No | **No** | Solo la propria | Solo la propria | Solo la propria | n/a |
| Consultare statistiche aggregate su tutte le famiglie | No | Sì, solo aggregati (SR-055) | No | No | No | n/a |
| Consultare il registro di sicurezza | No | Sì | No | No | No | n/a |
| Creare una famiglia con un codice di creazione | Sì, autenticandosi, senza appartenere a una famiglia | No | No (appartiene già a una famiglia, ASM-050) | No (ASM-050) | No (ASM-050) | n/a |
| Accettare un link di invito | Sì, autenticandosi, senza appartenere a una famiglia | No | No (ASM-050) | No (ASM-050) | No (ASM-050) | n/a |
| Rifiutare un link di invito | Sì, chi ha il link | No | Sì, chi ha il link | Sì, chi ha il link | Sì, chi ha il link | n/a |
| Modificare il proprio nome visualizzato | n/a | n/a | Propri | Propri | Propri | n/a |
| Modificare il nome visualizzato di un altro account | No | No | No (ASM-054) | No | No | n/a |
| Vedere e revocare le proprie sessioni | n/a | n/a | Propri | Propri | Propri | n/a |
| Eliminare il proprio account | n/a | n/a | Sì, R, se non è l'ultimo Amministratore | Sì, R | Sì, R | n/a |
| Esportare i propri dati in self-service (dall'apertura al pubblico) | n/a | n/a | Propri | Propri | Propri | n/a |
| Chiedere al Gestore l'esportazione dei propri dati (beta) | n/a | n/a | Propri | Propri | Propri | n/a |

### Famiglia e persone

| Azione \ Ruolo | Anonimo | Gestore (console) | Amministratore | Pianificatore | Membro | Profilo senza account |
|---|---|---|---|---|---|---|
| Modificare il nome della famiglia | No | No | Sì | No | No | n/a |
| Modificare il fuso orario della famiglia | No | No | Sì | No | No | n/a |
| Configurare i pasti di default | No | No | Sì | Sì | No | n/a |
| Gestire portate personalizzate e tag (creare, rinominare, eliminare) | No | No | Sì | Sì | No | n/a |
| Generare, elencare, revocare link di invito (ruolo massimo Pianificatore) | No | No | Sì | No | No | n/a |
| Assegnare o cambiare i ruoli Membro e Pianificatore | No | No | Sì | No | No | n/a |
| Nominare o revocare un Amministratore | No | No | Sì, R | No | No | n/a |
| Rimuovere una persona dalla famiglia | No | No | Sì | No | No | n/a |
| Vedere l'email verificata di chi è entrato con un invito (SR-073, CHG-013) | No | No | Sì | No | No | n/a |
| Scaricare un'esportazione della famiglia (beta) | No | No (non riceve il file) | Sì, solo se è ancora Amministratore. R da M2 (SR-072) | No | No | n/a |
| Uscire dalla famiglia | n/a | n/a | Sì, se non è l'ultimo Amministratore | Sì | Sì | n/a |
| Creare un profilo senza account, con dichiarazione di responsabilità genitoriale | No | No | Sì | Sì | No | n/a |
| Modificare o eliminare un profilo senza account, compreso il nome | No | No | Sì | Sì | No | n/a |
| Generare un invito collegato a un profilo e confermare il collegamento | No | No | Sì | No | No | n/a |
| Richiedere o annullare l'eliminazione della famiglia | No | No | Sì, R | No | No | n/a |
| Esportare i dati della famiglia in self-service (dall'apertura al pubblico) | No | No | Sì, R | No | No | n/a |
| Chiedere al Gestore l'esportazione dei dati della famiglia (beta) | No | No | Sì | No | No | n/a |

### Archivio piatti

| Azione \ Ruolo | Anonimo | Gestore (console) | Amministratore | Pianificatore | Membro | Profilo senza account |
|---|---|---|---|---|---|---|
| Consultare l'archivio | No | No | Sì | Sì | Sì | n/a |
| Creare un piatto "da provare" | No | No | Sì | Sì | Sì | n/a |
| Creare un piatto "collaudato" | No | No | Sì | Sì | No | n/a |
| Modificare un piatto (campi, fonti) | No | No | Sì | Sì | Propri, "da provare" e mai pianificati (ASM-029) | n/a |
| Assegnare tag esistenti a un piatto | No | No | Sì | Sì | Propri modificabili (ASM-055) | n/a |
| Cambiare lo stato di un piatto | No | No | Sì | Sì | No | n/a |
| Impostare il punteggio priorità di un piatto (CHG-001) | No | No | Sì | Sì | No (ASM-067) | n/a |
| Scegliere il proprio ordinamento preferito (CHG-002) | n/a | n/a | Propri | Propri | Propri | n/a |
| Archiviare o ripristinare un piatto | No | No | Sì | Sì | No | n/a |
| Eliminare definitivamente un piatto mai pianificato | No | No | Sì | Sì | Propri (ASM-029) | n/a |
| Importare piatti da CSV | No | No | Sì | Sì | No | n/a |
| Esprimere i propri gusti | No | No | Sì | Sì | Sì | n/a |
| Esprimere i gusti di un profilo senza account | No | No | Sì | Sì | No | n/a |
| Vedere i gusti di tutte le persone della famiglia | No | No | Sì | Sì | Sì (ASM-030, confermata) | n/a |

### Piano, presenze e cronologia

| Azione \ Ruolo | Anonimo | Gestore (console) | Amministratore | Pianificatore | Membro | Profilo senza account |
|---|---|---|---|---|---|---|
| Consultare il piano | No | No | Sì | Sì | Sì | n/a |
| Modificare il contenuto dei pasti, passati compresi | No | No | Sì | Sì | No | n/a |
| Aggiungere, rinominare o togliere un "Altro pasto" in un giorno (CHG-003) | No | No | Sì | Sì | No | n/a |
| Modificare la propria settimana tipo | n/a | n/a | Propri | Propri | Propri | n/a |
| Modificare le proprie presenze, passate comprese | n/a | n/a | Propri | Propri | Propri | n/a |
| Modificare settimana tipo e presenze di altri, profili compresi | No | No | Sì | Sì | No | n/a |
| Aggiungere o modificare gli ospiti di un pasto, anche passato | No | No | Sì | Sì | Se presente | n/a |
| Vedere la cronologia modifiche | No | No | Sì | Sì | Sì (ASM-044, confermata) | n/a |
| Modificare o cancellare la cronologia | No | No | No | No | No | n/a |

### Durante il periodo di ripensamento (FR-016)

La famiglia è in sola lettura (ASM-061). Restano consentite solo queste azioni. Tutte le altre sono rifiutate dal server, con un messaggio che indica la data di cancellazione.

| Azione \ Ruolo | Amministratore | Pianificatore | Membro |
|---|---|---|---|
| Consultare piano, archivio, cronologia | Sì | Sì | Sì |
| Annullare l'eliminazione | Sì, R | No | No |
| Chiedere l'esportazione (beta) o esportare in self-service (dopo l'MVP) | Famiglia e propri | Propri | Propri |
| Uscire dalla famiglia | Sì, se non è l'ultimo Amministratore | Sì | Sì |
| Eliminare il proprio account | Sì, R, se non è l'ultimo Amministratore | Sì, R | Sì, R |
| Vedere e revocare le proprie sessioni, modificare il proprio nome | Sì | Sì | Sì |

## Requisiti funzionali

Priorità MoSCoW: M = Must, S = Should, C = Could, W = Won't (non nell'MVP). La milestone indica il rilascio previsto (ASM-020 e ASM-027, confermate). "Apertura" indica la milestone di apertura al pubblico, che è fuori dall'MVP.

### Accesso, famiglia e persone

| ID | Descrizione | Priorità | Milestone | Fonte |
|---|---|---|---|---|
| FR-001 | Il sistema permette di autenticarsi con un account Google. L'account si identifica con il `sub` di Google, e si accetta solo un'email verificata (SR-033). | M | M0 | visione, SR-033 |
| FR-002 | Il sistema permette di creare un account con email e password **solo dentro il flusso di accettazione di un invito valido o di uso di un codice di creazione valido** (SR-035). L'account si attiva solo dopo la verifica dell'email. Un'email già associata a un altro account non viene mai collegata in automatico (SR-034). *Rinviato con CHG-020: tutte le famiglie tester hanno un account Google, quindi nell'MVP si accede solo con Google. Era M, M2.* | W (rinviato, CHG-020) | Backlog dopo M2 | visione, ASM-024, SR-034, SR-035, CHG-020 |
| FR-003 | Un account con email e password reimposta la password tramite un link inviato via email. Dopo la reimpostazione riceve un'email di notifica (SR-036). *Rinviato con CHG-020 insieme a FR-002. Era M, M2.* | W (rinviato, CHG-020) | Backlog dopo M2 | visione, SR-036, CHG-020 |
| FR-004 | La sessione resta attiva sul dispositivo per 30 giorni dall'ultimo utilizzo (scadenza mobile), e comunque al massimo 90 giorni dal login (scadenza assoluta, SR-037). L'utente può fare logout in qualunque momento. | M | M0 | elic. 2026-10-18, SR-037 |
| FR-005 | Il Gestore, con un comando da console, emette un codice di creazione monouso, elenca i codici con il loro stato (attivo, usato, scaduto, revocato) e ne revoca uno. | M | M2 | visione |
| FR-006 | Un utente autenticato **che non appartiene a nessuna famiglia** inserisce un codice di creazione valido, dichiara di avere almeno 14 anni, prende visione dell'informativa (FR-068) e crea una nuova famiglia, di cui diventa Amministratore. Il codice viene consumato. | M | M2 | visione |
| FR-007 | Il Gestore, con un comando da console, crea la famiglia iniziale e indica l'email Google del suo futuro Amministratore. Il primo login Google con quell'email verificata diventa Amministratore, e da quel momento il legame passa al `sub`. Un bootstrap non riscattato scade dopo 7 giorni (SR-033). | M | M0 | visione, ASM-020, SR-033 |
| FR-008 | L'Amministratore genera un link di invito con ruolo **Membro o Pianificatore** (SR-044) e, opzionalmente, un profilo senza account da collegare (FR-014). Può copiarlo o condividerlo, ed elencare e revocare gli inviti in sospeso. Ogni link è monouso, scade dopo 7 giorni e rispetta i limiti di SR-063. | M | M1 | visione, ASM-023, ASM-028, dec. 2026-10-18 SD-1 |
| FR-009 | Chi apre un link di invito valido e **non appartiene a nessuna famiglia** si autentica, dichiara di avere almeno 14 anni, prende visione dell'informativa (FR-068) ed entra nella famiglia con il ruolo indicato. Chi dichiara meno di 14 anni viene bloccato. Chi ha il link può anche **rifiutarlo**: l'invito viene consumato e l'Amministratore vede "rifiutato". Aprire il link non consuma l'invito (SR-043). | M | M1 | visione, dec. 2026-10-18 OBJ-07 |
| FR-010 | L'Amministratore assegna e cambia i ruoli Membro e Pianificatore degli account della famiglia. Gli Amministratori vedono chi è entrato, quando, con quale ruolo e con quale email verificata (SR-044, SR-073, CHG-013). | M | M1 | elic. 2026-10-18, Q-012 |
| FR-011 | Una famiglia ha **sempre almeno un Amministratore**. Il server lo garantisce in modo atomico anche con richieste concorrenti. L'ultimo Amministratore non può uscire, eliminare il proprio account né perdere il ruolo. *Nella versione 1 FR-011 comprendeva anche l'interfaccia per più Amministratori (M2): ora quella parte è FR-066 e l'invariante è anticipata a M1.* | M | M1 | visione, dec. 2026-10-18 OBJ-02 |
| FR-012 | L'Amministratore può rimuovere una persona dalla famiglia, e ogni account può uscirne. All'uscita o alla rimozione si cancellano gusti, settimana tipo ed eccezioni future della persona. Le presenze passate restano, pseudonimizzate come "ex membro" (SR-047). I piatti creati dalla persona restano alla famiglia. | M | M1 | visione, ASM-033 (confermata) |
| FR-013 | Amministratore e Pianificatore creano, modificano ed eliminano profili senza account. Un profilo ha solo un nome visualizzato (SR-014). Alla creazione, chi crea il profilo dichiara di esercitare la responsabilità genitoriale sulla persona, o di avere il consenso di chi la esercita. La dichiarazione si registra con data e autore (SR-064). | M | M1 | visione, dec. 2026-10-18 SD-5 |
| FR-014 | Un profilo senza account si collega a un account tramite un invito dedicato (FR-008). Dopo l'accettazione, il trasferimento di gusti, settimana tipo, presenze e storico avviene solo quando un Amministratore lo conferma (SR-045). Se l'Amministratore rifiuta, il profilo resta invariato. | M | M2 | visione, dec. 2026-10-18 SD-2 |
| FR-015 | La famiglia ha un nome, modificabile dall'Amministratore, e una configurazione dei pasti di default, scelti tra Colazione, Pranzo, Merenda, Cena e Altro pasto. | M | M0 | visione |
| FR-016 | L'Amministratore, dopo la riautenticazione, richiede l'eliminazione della famiglia. Per 7 giorni la famiglia è in sola lettura, salvo le azioni elencate nella matrice "Durante il periodo di ripensamento", e un Amministratore riautenticato può annullare. Alla scadenza tutti i dati della famiglia vengono cancellati definitivamente. | M | M2 | visione, ASM-022, SD-3 |
| FR-017 | Ogni account, dopo la riautenticazione, elimina il proprio account in autonomia con una conferma esplicita. Il vincolo di FR-011 resta valido. | M | M2 | elic. 2026-10-18, SD-3 |
| FR-018 | L'Amministratore, dopo la riautenticazione, esporta in self-service tutti i dati della famiglia in JSON e CSV. Durante la beta chiusa la stessa esigenza è coperta da FR-065. | M per l'apertura al pubblico, W nell'MVP | Apertura | elic. 2026-10-18, dec. 2026-10-18 OBJ-05 |
| FR-019 | Ogni account esporta in self-service i propri dati personali in JSON e CSV. Durante la beta chiusa la stessa esigenza è coperta da FR-065. | M per l'apertura al pubblico, W nell'MVP | Apertura | elic. 2026-10-18, dec. 2026-10-18 OBJ-05 |

### Archivio piatti

| ID | Descrizione | Priorità | Milestone | Fonte |
|---|---|---|---|---|
| FR-020 | Un piatto ha questi campi: nome (obbligatorio), una o più portate (almeno una), stato ("da provare" o "collaudato"), note, tempo di preparazione (opzionale, a fasce) e fonti della ricetta (FR-024). | M | M0 | elic. 2026-10-18 |
| FR-021 | Il sistema fornisce la lista base delle portate: antipasto, primo, secondo, contorno, piatto unico, dolce, bevanda, altro. | M | M0 | elic. 2026-10-18 |
| FR-022 | Amministratore e Pianificatore aggiungono, rinominano ed eliminano portate personalizzate della famiglia. Una portata in uso non si può eliminare. | S | M2 | elic. 2026-10-18, dec. 2026-10-18 OBJ-05 |
| FR-023 | Amministratore e Pianificatore definiscono tag liberi della famiglia, anche mentre modificano un piatto, e li rinominano o eliminano. Rinominare un tag aggiorna tutti i piatti che lo usano, eliminarlo lo toglie dai piatti. Un Membro può assegnare tag **già esistenti** solo ai piatti che può modificare (ASM-055). | M | M2 | elic. 2026-10-18, dec. 2026-10-18 OBJ-07 |
| FR-024 | Un piatto ha da 0 a 10 fonti della ricetta. Ogni fonte ha un tipo (link, libro, rivista, altro), un riferimento (URL per il tipo link, titolo e pagina per libro e rivista, testo per altro) e una nota opzionale. Un link si apre in una nuova scheda. | M | M0 | elic. 2026-10-18 |
| FR-025 | Lo stato di un piatto si cambia solo manualmente, da "da provare" a "collaudato" e viceversa. | M | M0 | visione, ASM-017 |
| FR-026 | Quando un piatto "da provare" risulta cucinato per la prima volta, il sistema propone a Pianificatori e Amministratori di promuoverlo a "collaudato". La proposta si può accettare o ignorare. | M | M2 | visione, ASM-017 |
| FR-027 | Ogni account esprime il proprio gusto su ogni piatto (piace, neutro, non piace) oppure lo rimuove, tornando a "sconosciuto". Amministratore e Pianificatore esprimono i gusti dei profili senza account. | M | M1 | elic. 2026-10-18 |
| FR-028 | Un Membro può aggiungere piatti solo con stato "da provare". Può modificare ed eliminare i piatti che ha creato finché restano "da provare" e non sono mai stati pianificati (ASM-029). | M | M1 | elic. 2026-10-18 |
| FR-029 | Un piatto mai pianificato si può eliminare definitivamente. Un piatto pianificato almeno una volta si può solo archiviare: esce dalle scelte, resta visibile nei piani passati e nello storico, e si può ripristinare. "Pianificato almeno una volta" è un dato permanente: resta vero anche se il piatto viene poi tolto da tutti i pasti (Q-028, CHG-005). | M | M0 | elic. 2026-10-18, CHG-005 |
| FR-030 | L'archivio permette di cercare per nome, con una ricerca parziale che ignora maiuscole e accenti (ASM-047), e di filtrare per portata e per stato. Per default i piatti archiviati sono nascosti, ma un filtro li mostra. | M | M0 | elic. 2026-10-18 |
| FR-031 | L'archivio permette di filtrare per tag e per tempo di preparazione, e di ordinare per nome o per "non cucinato da più tempo". In questo ordinamento i piatti mai cucinati vengono per primi. Resta M2. L'ordinamento per priorità e la memorizzazione della scelta sono in FR-071. | M | M2 | elic. 2026-10-18, CHG-002 |
| FR-032 | Mentre si digita il nome di un nuovo piatto, il sistema mostra i piatti della famiglia con nome simile. I nomi duplicati restano ammessi. | S | M2 | elic. 2026-10-18 |
| FR-033 | Amministratore e Pianificatore importano piatti da un file CSV, con anteprima, validazione per riga e gestione dei duplicati secondo ASM-040. **Decisione esplicita dell'utente: priorità Could.** È una novità rispetto alla visione. | C | M2 | elic. 2026-10-18, dec. 2026-10-18 OBJ-05 |
| FR-034 | Per ogni piatto il sistema ricava "ultima volta cucinato" e "cucinato N giorni fa" dal piano, secondo la definizione di "cucinato" del glossario. N si conta in giorni di calendario nel fuso della famiglia. | M | M0 | visione, ASM-003 |

### Piano dei pasti

| ID | Descrizione | Priorità | Milestone | Fonte |
|---|---|---|---|---|
| FR-035 | Il piano si consulta per qualunque intervallo di giorni, passati o futuri, fino a 62 giorni per vista. La vista predefinita è la settimana corrente, da lunedì a domenica nel fuso della famiglia, e si naviga alla settimana precedente o successiva. | M | M0 | visione, ASM-018, ASM-019 |
| FR-036 | Ogni giorno mostra i pasti di default della famiglia. Pianificatori e Amministratori possono aggiungere a un singolo giorno un tipo di pasto non di default, oppure togliere da quel giorno un pasto di default. Colazione, Pranzo, Merenda e Cena compaiono al massimo una volta per giorno. "Altro pasto" può comparire più volte, ognuno con un proprio nome (FR-072). | M | M0 | visione, CHG-003 |
| FR-037 | Pianificatori e Amministratori assegnano a un pasto uno o più piatti dell'archivio, indicando per ciascuno la portata in quel pasto, scelta tra le portate del piatto. Possono riordinarli e toglierli. I piatti archiviati non si possono scegliere. | M | M0 | visione |
| FR-038 | Pianificatori e Amministratori aggiungono a un pasto voci libere di testo. Una voce libera si può "salvare in archivio": diventa un nuovo piatto e la voce viene sostituita dal piatto (ASM-042). | M | M0 | elic. 2026-10-18 |
| FR-039 | Pianificatori e Amministratori marcano un pasto come speciale: "fuori casa", "ristorante" o "saltato". Vale per ogni pasto, compreso ciascun "Altro pasto". Un pasto speciale conta come pianificato e i suoi eventuali piatti non contano come cucinati. | M | M0 | elic. 2026-10-18, CHG-003 |
| FR-040 | Durante la scelta di un piatto per un pasto, per ogni piatto il sistema mostra "cucinato N giorni fa" oppure "mai cucinato", e permette di filtrare i soli piatti "da provare". In M0 e M1 il selettore ordina **solo per nome** (decisione dell'utente, Q-023). Da M2 vale l'ordinamento preferito dell'account (FR-071). | M | M0 | visione, CHG-002 |
| FR-041 | I pasti passati restano **sempre modificabili**, nei limiti della matrice. Pianificatori e Amministratori ne modificano il contenuto (aggiungono, tolgono o sostituiscono piatti, marcano un piatto "non cucinato") e tutte le presenze. Un Membro corregge le proprie presenze e gli ospiti dei pasti a cui era presente. "Ultima volta cucinato" si aggiorna di conseguenza, e ogni correzione genera un evento di modifica (FR-061). | M | M0 (contenuto), M1 (presenze e ospiti) | visione, dec. 2026-10-18 OBJ-01 |
| FR-042 | Pianificatori e Amministratori spostano un piatto o il contenuto di un intero pasto su un altro giorno o pasto, e scambiano tra loro due piatti o due pasti. Presenze e ospiti restano legati al giorno (ASM-053). | M | M1 | elic. 2026-10-18 |
| FR-043 | Pianificatori e Amministratori copiano un giorno o una settimana, anche passati, su un giorno o una settimana di destinazione, secondo ASM-041. | M | M1 | elic. 2026-10-18 |
| FR-044 | Concorrenza ottimistica. Le unità di modifica sono: (a) il contenuto di un pasto; (b) la presenza di una persona a un pasto; (c) gli ospiti di un pasto; (d) la scheda di un piatto (campi, fonti, tag, stato); (e) la settimana tipo di una persona. Il gusto di una persona su un piatto è un'unità a sé. Se una persona salva un'unità modificata da altri dopo averla letta, il sistema non sovrascrive in silenzio: mostra il conflitto e permette di ricaricare o di sovrascrivere esplicitamente. Le modifiche su unità diverse, anche dello stesso pasto, non entrano in conflitto. | M | M1 | elic. 2026-10-18, Q-010, dec. 2026-10-18 OBJ-06 |
| FR-045 | La cronologia modifiche, costruita dagli eventi di FR-061, è consultabile da tutti gli account della famiglia per giorno e per pasto, e mostra autore, ruolo dell'autore in quel momento, data e ora, e la modifica. | M | M1 | elic. 2026-10-18 |
| FR-046 | Nel piano, ogni pasto modificato da altri dopo l'ultima visita dell'utente mostra un indicatore "modificato da <nome> il <data e ora>". L'ultima visita è quella conservata sul server (FR-062), quindi l'indicatore è coerente tra dispositivi diversi. | S | M1 | elic. 2026-10-18, CHG-004 |
| FR-047 | Tutti gli account della famiglia consultano il piano con piatti, voci libere, pasti speciali, presenti, ospiti e coperti, con i comandi consentiti dal proprio ruolo. Da ogni piatto si raggiungono le sue fonti della ricetta. | M | M1 | visione |
| FR-048 | Durante la scelta e nella vista del piano, il sistema avvisa se un piatto assegnato a un pasto ha gusto "non piace" per una persona presente, account o profilo, e mostra il nome di quella persona. L'avviso non impedisce l'assegnazione. | M | M2 | visione, ASM-016, elic. 2026-10-18 |

### Presenze

| ID | Descrizione | Priorità | Milestone | Fonte |
|---|---|---|---|---|
| FR-049 | Ogni persona ha una settimana tipo: per ogni giorno della settimana e per ogni tipo di pasto tranne "Altro pasto", è presente o assente. Vale anche per i tipi non di default. Se la settimana tipo non è stata compilata, la persona è presente. | M | M1 | visione ASM-014, elic. 2026-10-18 |
| FR-050 | A **ogni** "Altro pasto" di un giorno, qualunque sia il suo nome, tutte le persone della famiglia risultano presenti per default, e la presenza è modificabile come per gli altri pasti. Ogni "Altro pasto" ha presenze e ospiti propri. Un "Altro pasto" tolto e poi aggiunto di nuovo (CHG-017) riparte con tutti presenti: le eccezioni precedenti si cancellano. | M | M1 | elic. 2026-10-18, ASM-032, CHG-003 |
| FR-051 | Su un singolo pasto, passato o futuro, si registra un'eccezione di presenza (assente o presente) per una persona. Ogni account modifica le proprie eccezioni. Amministratore e Pianificatore modificano quelle di tutti, profili compresi. | M | M1 | elic. 2026-10-18, dec. 2026-10-18 OBJ-01 |
| FR-052 | A un pasto, passato o futuro, si associano ospiti: un numero da 0 a 50 e una nota libera. Possono modificarli gli account presenti a quel pasto, i Pianificatori e gli Amministratori. | M | M1 | elic. 2026-10-18 |
| FR-053 | Ogni pasto mostra i coperti (persone presenti più ospiti) e l'elenco nominativo dei presenti e degli assenti. Per i pasti speciali vale ASM-052. | M | M1 | visione |

### Trasversali

| ID | Descrizione | Priorità | Milestone | Fonte |
|---|---|---|---|---|
| FR-054 | L'app è installabile come PWA. Senza connessione mostra in sola lettura l'ultimo piano caricato, con l'indicazione "dati aggiornati al <data e ora>". Le modifiche sono disabilitate finché manca la connessione. I dati offline più vecchi di 7 giorni non si mostrano e si cancellano (SR-071, CHG-011). | S | M2 | elic. 2026-10-18, dec. 2026-10-18 OBJ-05, CHG-011 |
| FR-055 | L'interfaccia è in italiano, con internazionalizzazione predisposta (NFR-011). | M | M0 | visione |
| FR-056 | Notifiche via email o push. | W | dopo l'MVP | elic. 2026-10-18 |
| FR-057 | Suggerimenti automatici di piatti o di piani. | W | dopo l'MVP | elic. 2026-10-18 |
| FR-058 | Modifica del piano senza connessione. | W | dopo l'MVP | elic. 2026-10-18 |
| FR-059 | MFA opzionale per gli account con email e password. Per gli account Google l'MFA è delegata a Google. | W | dopo l'MVP | elic. 2026-10-18 |

### Nuovi requisiti della versione 2

| ID | Descrizione | Priorità | Milestone | Fonte |
|---|---|---|---|---|
| FR-060 | Ogni famiglia ha un fuso orario, `Europe/Rome` per default, modificabile dall'Amministratore. Giorni, "oggi", pasti passati, inizio settimana e scadenze dei KPI si calcolano in quel fuso. Un pasto è passato quando il suo giorno è precedente a oggi. Cambiare il fuso non ricalcola i dati passati (ASM-059). | M | M0 | dec. 2026-10-18 OBJ-01 |
| FR-061 | Ogni modifica a contenuto dei pasti, presenze, ospiti, settimana tipo e stato dei piatti registra un evento di modifica con data e ora (UTC), autore, **ruolo dell'autore in quel momento**, oggetto e valori prima e dopo. Gli eventi si registrano da M0, anche se la cronologia visibile (FR-045) arriva in M1. Le persone si indicano solo con l'identificativo (SR-047). | M | M0 | dec. 2026-10-18 OBJ-04 |
| FR-062 | Il sistema registra due dati di visita, senza altri dettagli di navigazione: <br>(a) per ogni account e per ogni settimana, se l'account ha aperto il piano almeno una volta (visita settimanale). Serve per KPI-7 e si conserva come i dati del piano; <br>(b) **per ogni account, la data e ora dell'ultima apertura del piano** (ultima visita). È un solo valore, sovrascritto a ogni visita e conservato sul server. Serve per FR-046, si conserva finché esiste l'account e si cancella con esso. <br>Entrambi sono dati personali, classificati in `docs/05-data.md`, inclusi nell'esportazione dei dati dell'account e citati nell'informativa (FR-068). *Modificato da CHG-004: nella versione approvata a G2 esisteva solo il dato (a).* | M (a), S (b, segue FR-046) | M1 | dec. 2026-10-18 OBJ-04, CHG-004 |
| FR-063 | **Passato congelato.** Una modifica alla settimana tipo vale da oggi in avanti. Una persona conta nei pasti solo dal giorno in cui è entrata nella famiglia (ASM-058). I pasti passati conservano le presenze che avevano, anche se cambiano settimana tipo o persone della famiglia. Le correzioni esplicite su pasti passati (FR-041, FR-051) restano possibili. Il meccanismo (presenze materializzate o settimana tipo versionata) lo sceglie l'architetto con un ADR. | M | M1 | dec. 2026-10-18 OBJ-03 |
| FR-064 | **Recupero dell'Amministratore (semplificato, CHG-016).** Quando una famiglia non ha più un Amministratore, un membro con account lo chiede al Gestore scrivendo dall'email del proprio account. Il Gestore esegue il comando da console e inserisce **solo l'email del membro**, a un prompt interattivo. L'email viene trasformata in hash localmente e non compare mai sulla riga di comando. Il comando:<br>- verifica che l'hash corrisponda a un account con una persona attiva in una famiglia, e ricava la famiglia da quella persona (nell'MVP un account ha una sola persona attiva, ASM-002). Non mostra nessun altro dato (né nomi, né altri membri, né contenuti);<br>- aggiunge quell'account come Amministratore di quella famiglia.<br>Non ci sono soglie di inattività, verifiche su altri Amministratori o limiti giornalieri: il Gestore interviene su richiesta. Tutta la famiglia vede nell'app l'avviso "<nome> è diventato Amministratore tramite il supporto". L'evento entra nel registro di sicurezza e nella cronologia. La procedura è descritta nel runbook (`docs/09-release.md`). *Storia: sostituisce la verifica forte con attesa di 72 ore (ASM-057, CHG-009), e poi la condizione "nessun Amministratore utilizzabile" (ASM-071) con il limite di 5 esecuzioni al giorno (CHG-016). Parole dell'utente: "non stiamo parlando di un sistema che gestisce cose critiche, facciamoci meno paranoie. Se non c'è più un amministratore, il gestore interviene su richiesta e aggiunge un altro amministratore".* | M | M1 | dec. 2026-10-18 OBJ-08, CHG-009, CHG-016 |
| FR-065 | **Esportazione su richiesta durante la beta.** Su richiesta di un account (dati propri) o di un Amministratore (dati della famiglia), il Gestore avvia con un comando da console un'esportazione in JSON e CSV. Il file è scaricabile solo dal richiedente dentro l'app, per 24 ore, e il Gestore non ne legge il contenuto (SR-067). Il file della famiglia è scaricabile solo finché il richiedente è Amministratore, e con riautenticazione da M2 (SR-072). Si risponde entro un mese (GDPR art. 12(3), 15, 20). | M | M1 | dec. 2026-10-18 OBJ-05 |
| FR-066 | L'Amministratore, dopo la riautenticazione, nomina un altro account Amministratore o revoca il ruolo a un Amministratore, nel rispetto di FR-011. È l'interfaccia per più Amministratori. | M | M2 | visione, dec. 2026-10-18 OBJ-02, SD-1, SD-3 |
| FR-067 | Ogni account modifica il proprio nome visualizzato. Un login Google successivo non lo sovrascrive (SR-054). | M | M1 | SR-054, dec. 2026-10-18 OBJ-07 |
| FR-068 | Durante l'accettazione di un invito e la creazione di una famiglia, l'utente prende visione di un'informativa privacy breve, in linguaggio semplice e comprensibile anche da chi ha 14-17 anni, e di una sintesi delle condizioni d'uso. Si registrano versione e data della presa visione. A un cambio sostanziale della versione, l'informativa si ripresenta al login successivo (SR-030, SR-056). | M | M1 | SR-030, SR-056, dec. 2026-10-18 (Q-017) |
| FR-069 | Ogni account vede le proprie sessioni attive e può revocarne una o tutte tranne quella corrente (SR-038). | S | M1 | SR-038 |

### Nuovi requisiti dopo G2 (decisioni dell'utente in fase di design, 2026-10-18)

| ID | Descrizione | Priorità | Milestone | Fonte |
|---|---|---|---|---|
| FR-070 | **Punteggio priorità.** Ogni piatto ha un punteggio priorità intero da 1 a 10, 5 per default. Il punteggio è unico per la famiglia, non per persona. Lo modificano Pianificatori e Amministratori. Un Membro non lo modifica: i piatti che crea partono da 5 (ASM-067). Il punteggio compare nella scheda del piatto, nel selettore e nell'archivio. È incluso nelle esportazioni e, come colonna opzionale `priorita`, nell'import CSV (ASM-040). | S | M2 | CHG-001 (decisione utente) |
| FR-071 | **Ordinamento preferito.** Ogni account sceglie l'ordinamento del selettore dei piatti e dell'archivio tra: nome (A-Z), priorità (dalla più alta, a parità per nome) e non cucinato da più tempo (mai cucinati per primi, a parità per nome). La scelta è salvata sul server per account, quindi vale su tutti i dispositivi. Il default è "nome". In M0 e M1 il selettore ordina solo per nome (FR-040). | S | M2 | CHG-002 (decisione utente) |
| FR-072 | **Più "Altro pasto" nello stesso giorno, con nome libero.** Pianificatori e Amministratori possono aggiungere a un giorno più "Altro pasto". Ognuno ha un nome libero di 1-40 caratteri, "Altro pasto" per default, scelto ogni volta e modificabile, con al massimo 5 per giorno (ASM-068). Ogni "Altro pasto" è un pasto a sé, con contenuto, stato speciale, presenze (FR-050) e ospiti propri. Copia e spostamento (FR-042, FR-043) mantengono il nome. **L'interfaccia per più pasti e per il nome arriva in M2. Il modello dati li supporta da M0**, così non serve una migrazione. In M0 e M1 l'interfaccia aggiunge al massimo un "Altro pasto" per giorno, con il nome predefinito. | S (interfaccia), M (modello dati da M0) | M2 (interfaccia), M0 (modello) | CHG-003 (decisione utente), Q-024 |

## Misurazione dei KPI (definizioni operative)

Questa sezione precisa come si calcolano i KPI della visione con i dati richiesti sopra. Le differenze rispetto alla visione sono elencate in "Aggiornamenti alla visione".

- **Fonte dei dati:** i KPI si calcolano solo sulla famiglia del Gestore, a partire dalla sua esportazione (FR-065) (Q-016). Non si usano strumenti di analitica di terze parti (SR-031).
- **KPI-1 (copertura):** una settimana è coperta se, alle 00:00 del lunedì nel fuso della famiglia, ogni pasto di default dei 7 giorni ha almeno un piatto, una voce libera o uno stato speciale. Lo stato a quell'ora si ricostruisce dagli eventi di FR-061.
- **KPI-2 (tempo):** una sessione di pianificazione è una sequenza di eventi di modifica dello stesso autore sui pasti della stessa settimana, con pause di al massimo 30 minuti tra un evento e il successivo. La durata è il tempo tra il primo e l'ultimo evento. Il KPI è la mediana delle durate per settimana.
- **KPI-4 (ripetizioni):** si contano solo i piatti principali (ASM-026).
- **KPI-5 (piatti provati):** si contano i passaggi "da provare" → "collaudato" registrati negli eventi di FR-061.
- **KPI-7 (partecipazione):** è la quota di settimane in cui almeno un account con ruolo Membro in quel momento ha aperto il piano (FR-062) oppure ha inserito un'eccezione di presenza (FR-061). Questa definizione sostituisce ASM-051 per decisione dell'utente. Il target resta ≥ 30% (ASM-021) finché l'utente non lo riconsidera.

## Requisiti non funzionali

| ID | Categoria | Requisito misurabile | Priorità |
|---|---|---|---|
| NFR-001 | Prestazioni (client) | Le pagine principali (piano della settimana, archivio piatti, dettaglio piatto, selezione piatto) hanno un Largest Contentful Paint ≤ 2,0 s, misurato come **mediana di 5 esecuzioni** di Lighthouse per pagina, nel profilo mobile predefinito (rete 4G lenta simulata, CPU rallentata 4x), su una famiglia con 500 piatti e 8 persone. La misura si esegue ogni notte e prima di ogni rilascio, non a ogni pull request (CHG-018). La misura in sé non cambia. | M |
| NFR-002 | Prestazioni (server) | Tempo di risposta del server p95 ≤ 500 ms per le letture e ≤ 800 ms per le scritture, con 25 utenti concorrenti (ASM-035) e dati di 50 famiglie, misurato con un test di carico di 10 minuti. L'import CSV (FR-033) è escluso: vedi NFR-003. | M |
| NFR-003 | Prestazioni (import) | Un import CSV di 1.000 righe produce l'anteprima entro 10 s e completa l'importazione entro 30 s. Segue la priorità di FR-033. | C |
| NFR-004 | Scalabilità | Il sistema regge fino a 50 famiglie e 250 account (anno uno) rispettando NFR-001 e NFR-002, senza modifiche architetturali. Limiti per famiglia secondo ASM-034 e SR-060. | M |
| NFR-005 | Disponibilità | Disponibilità mensile ≥ 99%, calcolata come quota di controlli riusciti sul totale dei controlli del mese. Il controllo esterno (NFR-007) chiama ogni ≤ 5 minuti un endpoint di salute che verifica anche il database. Le manutenzioni programmate contano come indisponibilità. "Best effort" significa che non ci sono penali né turni di reperibilità: il Gestore interviene quando riceve l'allarme. Un singolo fermo di un'ora è accettabile e rientra nell'1%. | S |
| NFR-006 | Backup e ripristino | Backup completo almeno settimanale (RPO ≤ 7 giorni), cifrato, conservato nell'UE e ruotato entro 30 giorni. Ripristino provato almeno ogni 3 mesi con RTO ≤ 24 ore (ASM-036), compresa la riapplicazione delle cancellazioni (SR-048). Ogni prova di ripristino è registrata in `docs/09-release.md`. | M |
| NFR-007 | Osservabilità | Un controllo esterno di disponibilità ogni ≤ 5 minuti. Errori del server (HTTP 5xx ed eccezioni non gestite) raccolti, senza dati sensibili (SR-051), e notificati al Gestore entro 15 minuti dal primo evento. | M |
| NFR-008 | Accessibilità | Conformità a WCAG 2.2 livello AA. Verifica: zero violazioni "serious" o "critical" con uno strumento automatico (per esempio axe) su tutte le pagine, più una verifica manuale con sola tastiera e con screen reader (VoiceOver iOS, TalkBack Android) dei flussi US-008, US-021 e US-024. | M |
| NFR-009 | Compatibilità | Funziona sulle ultime 2 versioni stabili di Chrome (Android e desktop), Safari iOS, Firefox ed Edge. Usabile da 360 px di larghezza senza scorrimento orizzontale. | M |
| NFR-010 | Installabilità | La PWA supera i controlli di installabilità di Chrome e si installa da Safari iOS ("Aggiungi a Home"). La consultazione offline (FR-054) funziona dopo almeno un caricamento online del piano. Segue la priorità di FR-054. | S |
| NFR-011 | Internazionalizzazione | Il 100% dei testi dell'interfaccia sta in file di risorse per lingua, e un controllo automatico in CI fallisce se trova testo dell'interfaccia scritto nel codice. Date, ore e numeri sono formattati in base alla lingua, al formato locale (it-IT nell'MVP) e al fuso della famiglia. Aggiungere una lingua richiede solo nuovi file di risorse, senza modifiche al codice applicativo. I contenuti degli utenti non si traducono (ASM-025). | M |
| NFR-012 | Usabilità | (a) Dalla vista settimana, assegnare un piatto dell'archivio a un pasto richiede al massimo 3 interazioni (tocchi o selezioni, digitazione esclusa), verificato con un test end-to-end che conta le interazioni. (b) In un test di usabilità con il Pianificatore della famiglia del Gestore, comporre un piano di 14 pasti partendo dalla copia della settimana precedente e cambiandone 5 richiede un tempo mediano ≤ 10 minuti su 3 sessioni in settimane diverse (KPI-2, ASM-005). | S |
| NFR-013 | Usabilità (stati) | Ogni elenco o vista ha uno stato vuoto con un messaggio e l'azione successiva suggerita, uno stato di caricamento e uno stato di errore con possibilità di riprovare. Verifica: checklist della UX in `docs/03-ux.md`, più un test end-to-end per ogni stato vuoto delle viste principali. | M |
| NFR-014 | Portabilità | Spostare l'hosting su un altro provider richiede solo modifiche di configurazione e di infrastruttura, non del codice applicativo. Le dipendenze da servizi proprietari di un singolo provider sono elencate in un ADR. | S |
| NFR-015 | Manutenibilità | Tutte le operazioni dell'interfaccia passano da un'interfaccia server documentata con OpenAPI e versionata, che una futura app nativa può riutilizzare. Nessuna logica di autorizzazione vive solo nel client. Ogni operazione dichiara chi può chiamarla (SR-042). | M |
| NFR-016 | Residenza dei dati | Database, backup, log e file di esportazione risiedono nell'UE (SR-027). | M |
| NFR-017 | Capacità di archiviazione | Gli eventi di modifica (FR-061) si salvano in forma compatta da M0. Nella prima slice si misura la dimensione reale per evento e per famiglia, e la si annota in `docs/05-data.md`. Un allarme al Gestore scatta al 70% della quota di archiviazione del piano di hosting. Il passaggio al piano a pagamento (per esempio Supabase Pro) avviene solo se necessario, confrontato con le alternative gratuite (visione, "Vincoli"). (CHG-006, Q-027)<br>*Precisazione (G4, piano v3 I-P3, 2026-10-20):* "prima slice" va letta come la prima slice in cui esistono le tabelle che crescono e il job di misura. La misura si fa in **SL-10a** (worker di M0 e misura dello spazio, con gli eventi di modifica di M0) e si **ripete in SL-27** (chiusura di M1, con i dati delle presenze). Entrambi i risultati si annotano in `docs/05-data.md`. Il requisito non cambia. | M |

## Requisiti di sicurezza e privacy

Le SR-001 … SR-032 sono della versione 1, aggiornate con le osservazioni del security engineer. Le SR-033 … SR-063 derivano dalle sue proposte, integrate con gli esiti delle decisioni SD-1 … SD-7. Le SR-064 … SR-067 sono nuove. Il dettaglio di motivazione e verifica delle SR-033 … SR-063 è nella sezione "Dettaglio delle SR proposte dal security engineer".

### Autenticazione e sessioni

| ID | Requisito | Fonte | Milestone | Priorità |
|---|---|---|---|---|
| SR-001 | L'autenticazione Google usa OpenID Connect con flusso Authorization Code e PKCE, con una libreria consolidata. Chiede solo gli scope `openid`, `email` e `profile`. Il token si valida secondo SR-033, e l'account si lega al `sub` con `email_verified` vero. | SS §4, FR-001 | M0 | M |
| SR-002 | Le password si conservano solo come hash Argon2id, oppure bcrypt con costo ≥ 12. Lunghezza minima 12 caratteri e massima 128, nessuna regola di composizione obbligatoria. Controllo contro le password compromesse senza inviare a terzi la password né l'hash completo (SR-036). | SS §4, FR-002 | Backlog dopo M2 (segue FR-002, CHG-020) | M (se FR-002 viene realizzato) |
| SR-003 | Login, registrazione, recupero password, accettazione inviti, uso dei codici, import, esportazioni e API autenticata hanno i limiti di frequenza di SR-059. Al superamento il server risponde `429` con `Retry-After`. *CHG-020: registrazione e recupero password valgono solo quando FR-002 e FR-003 vengono realizzati.* | SS §4 | M0 / M1 / M2 | M |
| SR-004 | I messaggi di errore e i tempi di risposta di login, registrazione, recupero password, inviti e codici non rivelano se un account, un'email, un invito o un codice esistono (SR-034, SR-036). *CHG-020: nell'MVP la parte M2 riguarda solo i codici di creazione; registrazione e recupero password seguono FR-002 e FR-003.* | SS §4 | M0 / M2 | M |
| SR-005 | Il cookie di sessione è `__Host-`, `HttpOnly`, `Secure` e `SameSite=Lax` o più restrittivo (SR-037). La sessione si rigenera al login. La sessione viene invalidata al logout, al cambio password e all'eliminazione dell'account. L'accesso alla famiglia si revoca alla richiesta successiva dopo la rimozione. Scadenza mobile di 30 giorni e assoluta di 90 giorni. | SS §4, FR-004 | M0 | M |
| SR-006 | Un account con email e password non accede ai dati prima della verifica dell'email. I link di verifica e di recupero sono monouso e scadono entro 24 ore (verifica) e 1 ora (recupero). | SS §4, FR-002, FR-003 | Backlog dopo M2 (segue FR-002, CHG-020) | M (se FR-002 viene realizzato) |
| SR-007 | Link di invito e codici di creazione contengono un segreto di almeno 128 bit generato con un CSPRNG. Il segreto si conserva solo come hash, è monouso, scade (7 giorni gli inviti, 30 giorni i codici, ASM-038) ed è revocabile. Aprire il link con `GET` non consuma l'invito, e il consumo è atomico (SR-043). Link non validi, scaduti, usati, rifiutati o revocati producono lo stesso messaggio generico. | SS §4, §7 | M1 / M2 | M |
| SR-033 | Validazione del token ID di Google: firma RS256 con le chiavi di Google, `iss`, `aud`, `exp`, `nonce`, `state`, `email_verified=true`. L'account è la coppia (provider, `sub`). Il bootstrap si lega all'email solo fino al primo login, poi al `sub`, e scade dopo 7 giorni. Dei dati di Google si conservano solo quelli previsti da SR-014. | SS §4, FR-001, FR-007 | M0 | M |
| SR-034 | Nessuna unione automatica tra un account Google e un account email e password con la stessa email. Una registrazione con un'email già in uso riceve la stessa risposta di una nuova, e all'indirizzo arriva un'email informativa. | SS §4, FR-002 | Backlog dopo M2 (segue FR-002, CHG-020) | M (se FR-002 viene realizzato) |
| SR-035 | La registrazione con email e password esiste solo dentro i flussi di un invito o di un codice validi. Gli account non verificati si cancellano dopo 7 giorni. L'email può avere al massimo 254 caratteri e la password al massimo 128. | visione, SS §4, FR-002 | Backlog dopo M2 (segue FR-002, CHG-020) | M (se FR-002 viene realizzato) |
| SR-036 | Robustezza del login con password: controllo delle password compromesse locale o a k-anonimato, calcolo di hash anche per email inesistenti, ritardo progressivo senza blocco permanente, email di notifica dopo una reimpostazione. | SS §4 | Backlog dopo M2 (segue FR-002, CHG-020) | M (se FR-002 viene realizzato) |
| SR-037 | La sessione è un identificativo opaco di ≥ 128 bit generato con un CSPRNG, conservato sul server solo come hash. Il cookie è `__Host-`, con `Path=/`. Il token non è mai in storage JS, IndexedDB, cache del service worker o URL. Scadenza mobile di 30 giorni e assoluta di 90 giorni. | SS §4, §7, FR-004 | M0 | M |
| SR-038 | Ogni account vede le proprie sessioni attive e le revoca. Vale dalla richiesta successiva. | SS §4, FR-069 | M1 | S |
| SR-039 | **Decisa (SD-3).** Richiedono una riautenticazione entro 10 minuti: eliminazione della famiglia e relativo annullamento, eliminazione del proprio account, esportazione dei dati della famiglia, nomina o revoca di un Amministratore, e da M2 il download di un'esportazione della famiglia (SR-072). Per Google: `prompt=login`, `max_age`, verifica di `auth_time`. La nuova autenticazione deve riguardare la stessa identità (SR-068). | SS §4, FR-016, FR-017, FR-018, FR-066 | M2 (l'esportazione all'apertura al pubblico) | M |
| SR-040 | Sicurezza degli accessi del Gestore: MFA su tutti i servizi della piattaforma, credenziali della console fuori da file versionati e dalla cronologia della shell, ruolo di database della console senza lettura dei contenuti delle famiglie. Ogni comando scrive un evento nel registro di sicurezza. I comandi di recupero (FR-064) ed esportazione (FR-065) seguono SR-066 e SR-067. | SS §1, §6 | M0 | M |

### Autorizzazione e isolamento

| ID | Requisito | Fonte | Milestone | Priorità |
|---|---|---|---|---|
| SR-008 | L'autorizzazione è negata per default e si verifica sul server a ogni richiesta, a livello di oggetto. La famiglia si ricava dall'appartenenza dell'account autenticato, mai da un parametro del client. Un accesso a una risorsa di un'altra famiglia produce "non trovato" e un evento nel registro di sicurezza. Vale anche per i riferimenti nel corpo delle richieste (SR-041). | SS §5 | M0 | M |
| SR-009 | La matrice "Ruoli e permessi", comprese le righe del periodo di ripensamento, si applica sul server con una logica centralizzata (SR-042). Esiste un test negativo per ogni cella "No", e il test di inventario in CI fallisce se un'operazione non ha la dichiarazione di autorizzazione o il test "altra famiglia". | SS §5 | M0 | M |
| SR-010 | I campi scrivibili di ogni operazione sono una lista esplicita: niente mass assignment. Per esempio, un Membro non può impostare lo stato "collaudato", e nessun utente può impostare famiglia, ruolo, autore o date degli eventi. Un campo non consentito produce il rifiuto della richiesta (`403` per un permesso mancante, `422` per un campo sconosciuto). | SS §5, FR-028 | M0 | M |
| SR-011 | Il vincolo "almeno un Amministratore" si verifica sul server, in modo atomico rispetto a modifiche concorrenti di ruoli, uscite ed eliminazioni di account. | FR-011, dec. 2026-10-18 OBJ-02 | **M1** | M |
| SR-012 | Il Gestore non ha accesso ai contenuti delle famiglie da nessuna interfaccia applicativa. I comandi da console operano su codici, bootstrap, recupero dell'Amministratore, avvio delle esportazioni e conteggi aggregati, e non stampano contenuti delle famiglie. Il recupero riceve un'email in input e ne verifica solo la corrispondenza con un membro, senza rivelare altro (SR-066). Il ruolo di database della console non legge i contenuti (SR-040). L'accesso diretto al database è limitato agli incidenti e registrato (ASM-045). | visione Q-013 | M0 | M |
| SR-041 | Ogni identificativo nel corpo o nei parametri di una richiesta si verifica come appartenente alla famiglia dell'account, nella stessa transazione della scrittura. | SS §5 | M0 | M |
| SR-042 | Il filtro per famiglia si applica in un unico livello di accesso ai dati, eventualmente con la Row-Level Security del database (ADR). Gli identificativi non sono sequenziali. L'inventario delle autorizzazioni è verificato in CI. | SS §5, NFR-015 | M0 | M |
| SR-043 | Inviti e codici: un `GET` non consuma nulla, l'accettazione è una `POST` autenticata con protezione CSRF, il segreto non compare in log né nel `Referer`, e il consumo è atomico. Il nome della famiglia si mostra solo dopo il login (DD-07 di `docs/03-ux.md`, confermata). | SS §4, §9, §10 | M1 / M2 | M |
| SR-044 | **Decisa (SD-1).** Un link di invito assegna solo Membro o Pianificatore. Amministratore si assegna solo dall'interno (FR-066), con riautenticazione. Gli Amministratori vedono ogni ingresso. | SS §1, FR-008 | M1 | M |
| SR-045 | **Decisa (SD-2).** Il collegamento di un profilo a un account trasferisce i dati solo dopo la conferma di un Amministratore, che vede nome visualizzato ed email dell'account. Prima della conferma l'account non vede lo storico del profilo come proprio. | FR-014, GDPR art. 5(1)(f) | M2 | M |
| SR-063 | Limiti su inviti e codici: al massimo 20 inviti in sospeso per famiglia e 20 generati al giorno, al massimo 20 codici di creazione attivi sul sistema. Un nuovo invito collegato a un profilo revoca il precedente. | SS §1, FR-005, FR-008 | M1 / M2 | M |

### Dati personali e privacy

| ID | Requisito | Fonte | Milestone | Priorità |
|---|---|---|---|---|
| SR-013 | All'accettazione di un invito o alla creazione di una famiglia si conservano solo il fatto "dichiarato ≥14" e la data, mai la data di nascita. Se la persona dichiara meno di 14 anni, l'operazione è bloccata e l'invito resta valido. La soglia è confermata dall'art. 2-quinquies del Codice privacy (ASM-015, verificata dal security engineer). | visione, GDPR art. 8 | M1 | M |
| SR-014 | Minimizzazione. Per un account si conservano solo nome visualizzato, email, identificativo del provider (`sub`), dichiarazione di età, presa visione dell'informativa, ordinamento preferito (FR-071), ultima visita (un solo valore, FR-062, CHG-004) e, per email e password, l'hash della password. L'ultima visita non si usa per altre finalità, non compare nelle statistiche del Gestore e non è visibile agli altri account: si mostra solo, in forma derivata, l'indicatore di FR-046. L'email di un account è visibile solo agli Amministratori della sua famiglia (SR-073), mai a Pianificatori, Membri o Gestore. Per un profilo senza account si conservano solo un nome visualizzato e la dichiarazione di responsabilità genitoriale (SR-064). | SS §8, GDPR art. 5 | M0 | M |
| SR-015 | Ogni dato personale è classificato in `docs/05-data.md` con finalità e durata di conservazione. I dati dei minori sono marcati come tali. Presenze, settimana tipo e ospiti sono dato riservato (SR-055). Nessun dato è di categoria particolare (art. 9) per progetto. | SS §8 | M0 | M |
| SR-016 | Le esportazioni, self-service o tramite Gestore, sono scaricabili solo dal richiedente, generate su richiesta e cancellate dal server dopo 24 ore (ASM-046), o prima nei casi di SR-072. Il perimetro è quello di SR-072. Nei CSV le celle che iniziano con `=`, `+`, `-`, `@`, tabulazione o ritorno a capo sono neutralizzate. | SS §8, GDPR art. 15, 20 | M1 | M |
| SR-017 | L'eliminazione di un account cancella i suoi dati personali subito dal database e dai backup entro 30 giorni, con la rotazione. La pseudonimizzazione è effettiva (SR-047), e le cancellazioni si riapplicano dopo un ripristino (SR-048). | SS §8, GDPR art. 17 | M2 | M |
| SR-018 | Alla scadenza del periodo di ripensamento si cancellano definitivamente tutti i dati della famiglia. Dai backup escono entro 30 giorni, e le cancellazioni si riapplicano dopo un ripristino (SR-048). | GDPR art. 17, FR-016 | M2 | M |
| SR-019 | Conservazione. I dati della famiglia restano finché esiste la famiglia, quelli dell'account (comprese ultima visita e ordinamento preferito) finché esiste l'account, con il limite per l'inattività di SR-050. Inviti e codici scaduti o usati si cancellano dopo 30 giorni. Il registro di sicurezza si conserva 12 mesi (ASM-037), con l'IP completo solo per 90 giorni (SR-051). I log applicativi si conservano al massimo 30 giorni (SR-051). | SS §8, GDPR art. 5(1)(e) | M0 | M |
| SR-026 | La cache offline della PWA contiene solo i dati della famiglia dell'account corrente. Si svuota al logout, all'eliminazione dell'account, quando la sessione non è più valida, alla rimozione dalla famiglia, all'eliminazione della famiglia e al cambio di account sullo stesso dispositivo (SR-046). I dati più vecchi di 7 giorni non si mostrano e si cancellano (SR-071). | SS §8, FR-054 | M2 | M |
| SR-027 | Dati, backup, log ed esportazioni risiedono nell'UE. I fornitori che trattano dati personali sono elencati con la loro sede, hanno un accordo di trattamento accettato (SR-052), e quelli fuori dall'UE richiedono garanzie adeguate. | visione, GDPR capo V, art. 28 | M0 | M |
| SR-029 | Negli ambienti di sviluppo e test si usano solo dati sintetici. | SS §8 | M0 | M |
| SR-030 | **Precondizione di M1** (decisa, Q-017). Prima che entrino persone diverse dalla famiglia del Gestore esistono un'informativa privacy breve, scritta dall'utente su un modello, in linguaggio semplice e comprensibile anche da chi ha 14-17 anni, e una sintesi delle condizioni d'uso, mostrate secondo FR-068. L'informativa cita anche la registrazione dell'ultima visita e della visita settimanale al piano (FR-062, CHG-004), la visibilità dell'email agli Amministratori (SR-073), il recupero dell'Amministratore tramite il supporto (FR-064) e la durata di 7 giorni della cache offline (SR-071). L'informativa completa e i termini restano la condizione di ingresso dell'apertura al pubblico (ASM-011). | GDPR art. 12-13 | M1 | M |
| SR-031 | Nessuno strumento di analitica o tracciamento di terze parti. Gli unici servizi terzi lato client sono quelli di autenticazione. | visione ASM-009 | M0 | M |
| SR-032 | Accanto al campo note dei piatti e alla nota degli ospiti, l'interfaccia invita a non inserire dati sanitari (Q-015). | GDPR art. 9 | M0 | S |
| SR-046 | Le risposte autenticate hanno `Cache-Control: no-store`. La cache offline è legata all'account. Il service worker si serve con `no-cache`. | SS §8 | M0 / M2 | M |
| SR-047 | Cronologia e registro di sicurezza fanno riferimento alle persone solo con l'identificativo. Dopo una cancellazione non resta traccia del nome in nessuna tabella. | GDPR art. 17 | M0 (eventi), M1 (cronologia) | M |
| SR-048 | Un registro delle cancellazioni, conservato per ≥ 30 giorni, permette di riapplicarle dopo ogni ripristino da backup. | GDPR art. 17, NFR-006 | M1 | M |
| SR-049 | Un login Google senza famiglia, senza invito e senza codice non crea un account persistente. Un eventuale stato temporaneo si cancella entro 24 ore. | SS §8, GDPR art. 5(1)(c) | M0 | M |
| SR-050 | **Decisa (SD-4).** Una famiglia o un account senza accessi da 24 mesi riceve un avviso, e dopo altri 30 giorni senza accessi viene eliminato come in FR-016 o FR-017. Deve essere attivo entro l'apertura al pubblico. | GDPR art. 5(1)(e) | Apertura | M |
| SR-052 | Prima di M1 esistono il registro dei trattamenti (art. 30) e un accordo di trattamento (art. 28) con ogni fornitore. L'informativa spiega il ruolo di Google come titolare autonomo. | GDPR art. 28, 30 | M1 | M |
| SR-053 | La procedura di gestione delle violazioni dei dati (72 ore, registro delle violazioni, contatto privacy, comando di revoca globale delle sessioni) è in `docs/09-release.md` e viene provata prima di M2. | GDPR art. 33, 34 | M1 | M |
| SR-054 | Diritti degli interessati: rettifica del proprio nome (FR-067); le richieste non coperte dall'app passano dal contatto privacy, con risposta entro 30 giorni; per i profili senza account i diritti si esercitano tramite l'Amministratore. | GDPR art. 12, 16, 18, 21 | M1 | M |
| SR-055 | Presenze, settimana tipo e ospiti sono dato riservato: mai in log, notifiche, statistiche o condivisione pubblica. Le statistiche del Gestore sono solo aggregati su tutte le famiglie, mai per singola famiglia né su presenze o gusti. | SR-012, GDPR art. 25 | M1 | M |
| SR-056 | Si registrano versione e data della presa visione dell'informativa. A un cambio sostanziale l'informativa si ripresenta al login successivo. | GDPR art. 5(2), 13 | M1 | M |
| SR-064 | **Nuova (SD-5).** Chi crea un profilo senza account dichiara di esercitare la responsabilità genitoriale sulla persona, o di avere il consenso di chi la esercita. La dichiarazione si registra con data e autore, e senza di essa il profilo non viene creato. | GDPR art. 8, Codice privacy art. 2-quinquies c. 2 | M1 | M |
| SR-065 | **Aggiornata con CHG-015 (SD-6).** La sezione 8 del threat model (`docs/06-threat-model.md`) è adottata come **DPIA v1** per la beta, a partire da M1. L'utente, come titolare, la rivede, la data e la firma prima di M1. Prima dell'apertura al pubblico la DPIA viene rivista da un professionista (GDPR art. 35). Gli eventi elencati nel threat model §8.6 riaprono la valutazione. | GDPR art. 35, provv. Garante n. 467/2018 | M1 / Apertura | M |

### Registro di sicurezza, log e abusi

| ID | Requisito | Fonte | Milestone | Priorità |
|---|---|---|---|---|
| SR-020 | Il registro di sicurezza riporta, in formato strutturato, con data e ora UTC, attore (identificativo), ruolo, famiglia (identificativo), esito, IP (SR-051) e ID di correlazione:<br>- accessi e sessioni: login riusciti e falliti, logout, creazione e verifica dell'account, recupero e reimpostazione della password, riautenticazioni riuscite e fallite, revoche di sessioni;<br>- inviti: creazione, accettazione, rifiuto e revoca, dichiarazione di età bloccata;<br>- ruoli e persone: cambio di ruolo, nomina e revoca di un Amministratore, rimozione o uscita dalla famiglia;<br>- profili: creazione con dichiarazione di responsabilità genitoriale, richiesta, conferma o rifiuto di un collegamento;<br>- eliminazioni: richiesta, annullamento ed esecuzione dell'eliminazione di una famiglia o di un account;<br>- esportazioni, generazione e download;<br>- console: emissione, uso e revoca di codici, ogni comando compresi bootstrap, recupero ed esportazione;<br>- abusi: superamento di un limite di frequenza, accessi negati, compresi quelli verso altre famiglie (SR-057). | SS §9 | M0 | M |
| SR-021 | Log e registro di sicurezza non contengono password, token, segreti di inviti o codici, cookie, né contenuti delle famiglie. I ritorni a capo nell'input sono neutralizzati. Gli utenti ricevono errori generici. | SS §9 | M0 | M |
| SR-022 | La cronologia modifiche è visibile solo agli account della famiglia, non si modifica né si cancella dall'interfaccia, e si conserva come i dati del piano. | FR-045 | M1 | M |
| SR-023 | TLS 1.2 o superiore con HSTS. Header di sicurezza attivi (CSP restrittiva, `nosniff`, `Referrer-Policy`, `frame-ancestors`), protezione CSRF sulle richieste che modificano dati, CORS con una lista esplicita di origini. | SS §7, §10 | M0 | M |
| SR-024 | Ogni input è validato sul server con uno schema esplicito, con i limiti di ASM-034 e SR-060. Le fonti di tipo link accettano solo `http` e `https`, sono rese con `rel="noopener noreferrer"` e non vengono mai aperte dal server. I testi degli utenti sono codificati in output. | SS §2, §3, §10 | M0 | M |
| SR-025 | L'import CSV accetta solo file UTF-8 di al massimo 1 MB e 1.000 righe, validati riga per riga, senza esecuzione di formule e soggetti ai limiti di frequenza. | SS §2, §10, FR-033 | M2 | M (se FR-033 viene realizzato) |
| SR-028 | Backup e database sono cifrati a riposo. | SS §7, §12 | M0 | M |
| SR-051 | Log applicativi conservati al massimo 30 giorni nell'UE. Raccolta degli errori con scrubbing di cookie, header, corpi e segreti, senza session replay. **Decisa (SD-7):** IP completo nel registro di sicurezza per 90 giorni, poi troncato. | SS §9 | M0 | M |
| SR-057 | Il registro di sicurezza è in sola aggiunta per il ruolo dell'applicazione, con orari UTC del server e l'elenco completo degli eventi (vedi SR-020). | SS §9 | M0 | M |
| SR-058 | Allarmi di sicurezza al Gestore entro 15 minuti, sulle soglie del dettaglio di SR-058. | SS §9 | M1 | S |
| SR-059 | Valori dei limiti di frequenza (tabella nel dettaglio di SR-059). Al superamento il server risponde `429` con `Retry-After`. I contatori sono condivisi tra le istanze e sopravvivono a un riavvio. Sostituisce ASM-048. Si aggiungono i limiti per account e per famiglia di SR-070. Righe "Callback OIDC" e "Login fallito per IP" rinviate (CHG-021). | SS §4, §10 | M0 / M1 / M2 | M |
| SR-060 | Corpo delle richieste ≤ 64 KB (1 MB per l'import), profondità JSON ≤ 10, paginazione al massimo 100, intervallo del piano ≤ 62 giorni, quote per famiglia atomiche. | SS §2, §10 | M0 | M |
| SR-061 | Le email partono solo dai flussi previsti, non contengono testo libero di altri utenti, hanno un tetto giornaliero con allarme all'80%, e il dominio ha SPF, DKIM e DMARC. *CHG-020: senza FR-002 e FR-003 nessun flusso dell'MVP (M0-M2) invia email dall'app. La SR si applica dal primo flusso email realizzato: email e password (backlog dopo M2) oppure avviso di inattività di SR-050 (apertura al pubblico).* | SS §4, §10 | Primo flusso email (backlog dopo M2 o Apertura), CHG-020 | M |
| SR-062 | Avvisi e tetti di spesa sui servizi a consumo. Al raggiungimento di una quota gratuita si degrada in modo documentato. | visione | M0 | S |
| SR-066 | **Riscritta con CHG-016 (recupero semplificato).** Il comando di recupero dell'Amministratore (FR-064):<br>- non riceve l'identificativo della famiglia. Accetta solo l'email del membro, inserita a un prompt interattivo e trasformata in **hash localmente**. L'email in chiaro non compare mai sulla riga di comando, quindi non finisce nella cronologia della shell, né nei log;<br>- verifica, all'interno di una funzione del database, che l'hash corrisponda a un account con una sola persona attiva, e ricava la famiglia da quella persona. Restituisce solo "corrispondenza sì/no". Non rivela nomi, famiglie, altri membri, email o contenuti, e non permette di elencarli. Se l'account non ha esattamente una persona attiva, il comando fallisce con un esito generico;<br>- aggiunge l'account come Amministratore, senza altre condizioni;<br>- scrive l'evento, riuscito o non riuscito, nel registro di sicurezza, e quello riuscito nella cronologia della famiglia;<br>- genera l'avviso visibile a tutta la famiglia;<br>- invalida le sessioni dell'account promosso, che deve rifare il login.<br>Il Gestore annota nel runbook la data e il riferimento della richiesta, senza copiarne il contenuto. Il metodo di hash, normalizzazione compresa, è definito dall'architect e dal data-architect, in modo coerente con il confronto nel database. *Rimossi con CHG-016: la condizione "nessun Amministratore utilizzabile" (ASM-071) e il limite di 5 esecuzioni al giorno.* | SS §1, §9 | M1 | M |
| SR-067 | **Nuova (OBJ-05).** L'esportazione avviata dalla console (FR-065):<br>- è eseguita dal servizio applicativo con il perimetro di autorizzazione del richiedente (propri dati, oppure famiglia se il richiedente è Amministratore);<br>- l'output del comando contiene solo l'identificativo del job e il suo stato;<br>- il file è scaricabile solo dal richiedente autenticato nell'app, per 24 ore;<br>- generazione e download entrano nel registro di sicurezza.<br>Il Gestore non riceve né apre il file. Il perimetro e il ciclo di vita dei file seguono SR-072. | SS §1, §8, SR-012, SR-016 | M1 | M |

### SR dal threat model (CHG-008 … CHG-015, decisioni dell'utente del 2026-10-18)

Proposte dal security engineer in `docs/06-threat-model.md` §9, integrate con gli esiti decisi dall'utente. Le minacce di riferimento (THR-NNN) sono nel threat model.

| ID | Requisito | Fonte | Milestone | Priorità |
|---|---|---|---|---|
| SR-068 | **Accettata (CHG-008).** Riautenticazione legata alla stessa identità. La riautenticazione vale solo se il nuovo token ID ha la stessa coppia (provider, `sub`) dell'account della sessione, e un `auth_time` presente, non precedente all'avvio del flusso (tolleranza 60 s) e non futuro. Altrimenti l'ora di autenticazione della sessione non cambia e si registra l'evento `reauth.mismatch`. Per email e password (dopo M2, se FR-002 viene realizzato, CHG-020) si verifica la password dello stesso account. Precisa SR-039. | THR-008, THR-009 | M2 | M |
| SR-069 | ~~RIFIUTATA~~ (CHG-009, decisione dell'utente del 2026-10-18). Proponeva il recupero dell'Amministratore in due fasi, con avviso e opposizione nell'app, attesa di 72 ore e codice di supporto. L'utente ha scelto il recupero semplice di FR-064 e SR-066. Il rischio residuo è descritto nella sezione "Rischi residui accettati". | THR-050 | n/a | n/a |
| SR-070 | **Accettata (CHG-010).** Limiti per account e per famiglia, che si aggiungono a SR-059 e SR-060:<br>- al massimo 60 scritture al minuto **per account**, sommando tutte le sessioni;<br>- al massimo 5.000 scritture tracciate al giorno per famiglia (scritture che generano un evento di modifica, FR-061), con `429` e allarme al Gestore;<br>- al massimo 20 sessioni attive per account: al login oltre il limite si revoca la sessione usata meno di recente. | THR-013, THR-046, THR-100 | M0 | M |
| SR-071 | **Accettata in forma ridotta (CHG-011, decisione dell'utente: solo scadenza).** I dati della cache offline (FR-054) più vecchi di 7 giorni non si mostrano e si cancellano all'apertura dell'app. Il **contenuto non cambia** rispetto ad ASM-043: restano in cache anche l'elenco nominativo di presenti e assenti e le note degli ospiti. Rischio residuo accettato: vedi la sezione "Rischi residui accettati". | THR-072, RDP-03 | M2 | S (segue FR-054) |
| SR-072 | **Accettata (CHG-012).** Perimetro e ciclo di vita delle esportazioni:<br>- il download di un'esportazione della famiglia richiede che il richiedente sia **ancora** Amministratore di quella famiglia;<br>- i file della famiglia di un account si cancellano quando l'account perde il ruolo, esce o viene rimosso;<br>- da M2 il download di un'esportazione della famiglia richiede la riautenticazione (SR-039);<br>- l'esportazione della famiglia contiene i contenuti della famiglia e i nomi visualizzati, ma **non** email, ultima visita, ordinamento preferito, sessioni o IP degli altri account;<br>- l'esportazione dei propri dati contiene i dati del proprio account e quelli della propria persona.<br>Precisa SR-016 e SR-067. | THR-060, THR-063, THR-112 | M1 (riautenticazione da M2) | M |
| SR-073 | **Accettata (CHG-013).** Nell'elenco delle persone e nell'evento di ingresso, gli Amministratori vedono il nome visualizzato **e l'email verificata** di ogni account entrato con un invito. L'email non è visibile a Pianificatori e Membri. L'informativa lo spiega (SR-030). | THR-030 | M1 | M |
| SR-074 | **Accettata (CHG-014).** Separazione e igiene degli accessi operativi del Gestore:<br>- MFA resistente al phishing (passkey o chiave di sicurezza) su Google Cloud, Supabase, GitHub, registrar e DNS;<br>- le credenziali operative non restano in cache nell'ambiente dove si installano dipendenze o si esegue codice di terzi (container o utente del sistema operativo separati);<br>- la console usa un'identità che accede solo al proprio segreto;<br>- disco cifrato;<br>- `maint replay-deletions` e `db/bootstrap.sql` si eseguono come job cloud;<br>- la verifica è annotata in `docs/09-release.md`. | THR-052, THR-090 | M0 (prima di trattare dati di altre famiglie, al più tardi prima di M1) | M |
| SR-075 | **Accettata (CHG-014).** Hardening di Supabase e rilevazione degli accessi al database (aggiorna ADR-0016):<br>- "Enforce SSL" attivo;<br>- `CONNECTION LIMIT` per ruolo;<br>- password di `postgres` casuale e gestita;<br>- registrazioni di Supabase Auth disattivate e nessun bucket Storage;<br>- rilevazione automatica delle connessioni anomale per ruolo, con allarme, al posto della revisione mensile dei log;<br>- **network restrictions**: prima di M1 si verifica se sono disponibili sul piano Free. Se lo sono, si attivano con un IP di uscita statico (circa 5 €/mese, costo accettato dall'utente). Se non lo sono, il rischio residuo si registra nella DPIA (SR-065). | THR-040 … THR-043 | M0 (base), prima di M1 (completo) | M |
| SR-076 | **Accettata (CHG-014).** Catena di fornitura:<br>- attesa di 7 giorni prima di adottare le nuove versioni delle dipendenze;<br>- script d'installazione npm bloccati, salvo una allow-list;<br>- immagini base fissate per digest;<br>- scansioni obbligatorie del threat model §11, bloccanti in CI;<br>- Workload Identity Federation limitata al repository e al branch `main`. | THR-090 … THR-093 | M0 | M |

### Rischi residui accettati dall'utente

| Rischio | Riferimento | Livello residuo | Decisione |
|---|---|---|---|
| Link di invito come segreto al portatore: chi ottiene il link, per esempio da una chat inoltrata, può entrare come Membro o Pianificatore entro 7 giorni. | THR-030, RDP-02 | Medio | **Accettato esplicitamente dall'utente** (2026-10-18, CHG-015). Mitigazioni attive: ruolo massimo Pianificatore, monouso, 7 giorni, revoca, ingressi visibili agli Amministratori con email verificata (SR-073). |
| Recupero semplificato dell'Amministratore: chi controlla l'email di un membro della famiglia, o chi inganna il Gestore, può ottenere il ruolo di Amministratore anche se la famiglia ha già un Amministratore attivo, senza opposizione preventiva. | THR-050, RDP-02 | Medio (stima del product-analyst, da rivalutare dal security engineer) | **Accettato** dall'utente con CHG-009 e CHG-016 ("facciamoci meno paranoie"). Mitigazioni: richiesta dall'email dell'account, verifica dell'hash sull'account, avviso visibile a tutta la famiglia, cronologia e registro di sicurezza. Gli Amministratori esistenti possono revocare il ruolo (FR-066, da M2). |
| Cache offline con presenze nominative e note degli ospiti, su un dispositivo perso o di un ex membro rimasto offline, per al massimo 7 giorni. | THR-072, RDP-03 | Medio (il threat model lo indica come Medio senza la riduzione del contenuto) | **Accettato** con la scelta di CHG-011. |
| Endpoint del database esposto, se le network restrictions non sono disponibili sul piano Free. | THR-040, THR-041 | Medio | Da registrare nella DPIA (SR-075). |

### Dettaglio delle SR proposte dal security engineer

> Sezione scritta dal security-engineer il 2026-10-18 e integrata dal product-analyst il 2026-10-18. Gli esiti delle decisioni SD-1 … SD-7 sono indicati in ogni SR interessata e nella tabella finale. I requisiti vincolanti sono quelli delle tabelle sopra. Questa sezione ne conserva motivazione e verifica.
>
> Verifica di ASM-015: la soglia italiana di 14 anni è confermata dall'art. 2-quinquies del Codice privacy (D.Lgs. 196/2003, come modificato dal D.Lgs. 101/2018). Lo stesso articolo chiede che l'informativa per i minori sia scritta in modo chiaro e semplice, come già previsto da SR-030. Prima della pubblicazione dell'informativa conviene controllare il testo vigente su Normattiva.

#### Autenticazione e sessioni

**SR-033 · Validazione dell'identità Google e chiave dell'account · M0 · Priorità M**
- **Requisito:** il token ID di Google si accetta solo se la firma è verificata con le chiavi pubblicate da Google (algoritmo fisso RS256), se `iss`, `aud` (il client ID dell'app), `exp` e `nonce` sono validi, se il parametro `state` corrisponde e se `email_verified` è vero. L'account si identifica con la coppia (provider, `sub`), mai con l'email. Il bootstrap (FR-007) collega la famiglia a un'email solo fino al primo login con quell'email verificata: da quel momento il legame passa al `sub`. Un bootstrap non riscattato scade dopo 7 giorni. Della risposta di Google si conservano solo i dati di SR-014: non si conservano foto profilo, lingua o altri claim.
- **Motivazione:** chi usa l'email come chiave è esposto al furto dell'account se l'email cambia o viene riassegnata. Un token non validato del tutto permette di impersonare un utente.
- **Verifica:** test automatici: token con `aud` o `iss` errati, scaduto, firmato con un'altra chiave, con `nonce` diverso o con `email_verified=false` → login rifiutato. Un utente con lo stesso `sub` ed email cambiata ritrova il proprio account. Un bootstrap più vecchio di 7 giorni non si riscatta.
- **Fonte:** SS §4, FR-001, FR-007, SR-001.

**SR-034 · Nessun collegamento automatico tra metodi di accesso · Backlog dopo M2 (segue FR-002, CHG-020; era M2) · Priorità M se FR-002 viene realizzato**
- **Requisito:** un account Google e un account email e password con la stessa email non vengono mai uniti in automatico. Se in un flusso di registrazione si usa un'email già associata a un account, il sistema risponde con lo stesso messaggio di una registrazione nuova ("controlla la tua email"). All'indirizzo arriva un'email che spiega che l'account esiste già e come accedere. Un eventuale collegamento tra metodi è fuori dall'MVP.
- **Motivazione:** l'unione automatica permette il pre-hijacking: un attaccante registra la password sull'email della vittima prima che la vittima entri con Google, e conserva l'accesso dopo l'unione. La risposta diversa per un'email già registrata rivela invece chi usa il servizio.
- **Verifica:** test: registrazione email e password con l'email di un account Google esistente → nessun nuovo accesso all'account esistente, risposta e tempi di risposta indistinguibili dal caso di un'email nuova, email informativa inviata.
- **Fonte:** SS §4, FR-002, SR-004.

**SR-035 · Registrazione email e password solo dentro un flusso autorizzato · Backlog dopo M2 (segue FR-002, CHG-020; era M2) · Priorità M se FR-002 viene realizzato**
- **Requisito:** un account email e password si crea solo dentro il flusso di accettazione di un invito valido o di uso di un codice di creazione valido. Non esiste una pagina di registrazione aperta. Gli account non verificati vengono cancellati dopo 7 giorni. L'email è lunga al massimo 254 caratteri e la password al massimo 128, per limitare il costo dell'hash.
- **Motivazione:** la registrazione chiusa della visione vale anche per le email. Una registrazione aperta permette di creare account a raffica, di usare il servizio per mandare email a indirizzi arbitrari e di consumare le quote gratuite.
- **Verifica:** test: richiesta di registrazione senza un invito o un codice valido → rifiutata. Un job di pulizia cancella gli account non verificati più vecchi di 7 giorni, con un test che lo dimostra. Una password di 129 caratteri viene rifiutata prima dell'hash.
- **Fonte:** visione ("Accesso a registrazione chiusa"), SS §4, FR-002.

**SR-036 · Robustezza del login con password · Backlog dopo M2 (segue FR-002, CHG-020; era M2) · Priorità M se FR-002 viene realizzato**
- **Requisito:**
  - il controllo delle password compromesse non invia mai a terzi la password né il suo hash completo: si usa un elenco locale oppure un servizio a k-anonimato, che riceve solo un prefisso dell'hash;
  - per un'email inesistente il login esegue comunque un calcolo di hash, così il tempo di risposta non rivela se l'account esiste;
  - dopo i tentativi falliti si applica un ritardo progressivo per identità (SR-059), non un blocco permanente, così un attaccante non può bloccare l'account della vittima;
  - dopo ogni reimpostazione della password il titolare riceve un'email di notifica, che non contiene la password né un link di accesso.
- **Motivazione:** SR-002 e SR-004 fissano il principio ma non chiudono l'enumerazione tramite i tempi di risposta, la fuga della password verso il servizio di controllo e il blocco dell'account come forma di disservizio.
- **Verifica:** test: la differenza tra i tempi medi di login con email esistente e inesistente è inferiore al 10% su 100 tentativi. Un test con un servizio finto verifica che esca solo il prefisso dell'hash. Dopo una reimpostazione viene inviata la notifica.
- **Fonte:** SS §4, SR-002, SR-003, SR-004.

**SR-037 · Token di sessione · M0 · Priorità M**
- **Requisito:** la sessione è un identificativo opaco di almeno 128 bit generato con un CSPRNG, conservato sul server solo come hash. Il cookie usa il prefisso `__Host-`, con `Path=/` e senza `Domain`. Il token non si trova mai in `localStorage`, `sessionStorage`, IndexedDB, nella cache del service worker né in un URL. Valgono la scadenza mobile di 30 giorni e quella assoluta di 90 giorni (ASM-039, che questa SR conferma).
- **Motivazione:** un token leggibile da JavaScript si ruba con un solo XSS. Un token conservato in chiaro nel database si ruba con una fuga dei dati o dei backup. Senza scadenza assoluta, una sessione rubata su un telefono resta valida per sempre.
- **Verifica:** test di integrazione sugli attributi del cookie. Ispezione del database: nessun token in chiaro. Test: una sessione con ultimo uso recente ma creata 91 giorni prima viene rifiutata. Ricerca automatica nel codice client di accessi allo storage con il token.
- **Fonte:** SS §4, §7, FR-004, SR-005.

**SR-038 · Elenco e revoca delle sessioni · M1 · Priorità S**
- **Requisito:** ogni account vede le proprie sessioni attive (tipo di dispositivo e browser, data approssimativa dell'ultimo uso, senza indirizzo IP completo) e può revocarne una o tutte tranne quella corrente ("esci da tutti gli altri dispositivi"). L'effetto vale dalla richiesta successiva.
- **Motivazione:** le sessioni durano 30-90 giorni su telefoni che si perdono, si cambiano o restano a figli e parenti. Senza revoca remota, l'unico rimedio di un account Google è revocare l'accesso dalle impostazioni di Google, che non chiude la sessione dell'app.
- **Verifica:** test: dopo "esci da tutti gli altri dispositivi" una richiesta con il cookie di un'altra sessione viene rifiutata, mentre la sessione corrente resta valida. L'evento entra nel registro di sicurezza.
- **Fonte:** SS §4, FR-004.

**SR-039 · Riautenticazione per le operazioni critiche · M2 · Priorità M (decisa, SD-3 = b)**
- **Requisito:** queste operazioni richiedono un'autenticazione completata da non più di 10 minuti: richiesta e annullamento dell'eliminazione della famiglia, eliminazione del proprio account, esportazione self-service dei dati della famiglia, nomina o revoca del ruolo Amministratore. Per Google si ripete il login con `prompt=login` e `max_age`, verificando `auth_time`. Per email e password si reinserisce la password (solo quando FR-002 sarà realizzato, CHG-020). *Nota del product-analyst: nella proposta originale la parte sui ruoli era M1. Dopo la decisione SD-1, in M1 non esiste più un'interfaccia per assegnare il ruolo Amministratore, che arriva in M2 con FR-066. Per questo la SR è tutta M2.*
- **Motivazione:** la sessione dura settimane su dispositivi condivisi in casa. Chi prende in mano il telefono sbloccato di un Amministratore non deve poter cancellare la famiglia, esportare i dati di tutti, minori compresi, o nominarsi Amministratore.
- **Verifica:** test: con una sessione autenticata da più di 10 minuti, ognuna di queste operazioni restituisce "riautenticazione richiesta" e non produce effetti. Dopo la riautenticazione l'operazione riesce.
- **Fonte:** SS §4 (MFA e protezione degli account privilegiati), FR-016, FR-017, FR-018, FR-066.

**SR-040 · Sicurezza degli accessi del Gestore · M0 · Priorità M**
- **Requisito:**
  - gli account del Gestore sui servizi della piattaforma (hosting, database, progetto Google Cloud del client OAuth, provider email, DNS e registrar del dominio, repository, servizio di monitoraggio degli errori, backup) hanno l'MFA attiva;
  - i comandi da console usano credenziali che non stanno in chiaro in file versionati né nella cronologia della shell;
  - il ruolo di database usato dalla console ha permessi solo sulle tabelle di codici, bootstrap e registro di sicurezza, più le viste di conteggio aggregato (SR-055). Non ha accesso in lettura ai contenuti delle famiglie. *Integrazione del product-analyst:* il comando di recupero (FR-064, SR-066) ha in più la sola scrittura del ruolo di appartenenza e dell'evento in cronologia. Il comando di esportazione (FR-065, SR-067) si limita ad accodare un job eseguito dal servizio applicativo;
  - ogni comando eseguito scrive un evento nel registro di sicurezza.
- **Motivazione:** il Gestore è il punto più privilegiato del sistema. Chi compromette uno di questi account ottiene tutti i dati di tutte le famiglie, oppure può sostituire il client OAuth o il DNS e rubare gli accessi. SR-012 è oggi solo una regola procedurale (ASM-045): un ruolo di database ristretto la rende tecnica per tutto ciò che passa dalla console.
- **Verifica:** una checklist in `docs/09-release.md`, con la data di verifica dell'MFA su ciascun servizio. Test: il ruolo della console riceve "permesso negato" su `SELECT` dalle tabelle di piatti, piano, presenze e gusti.
- **Fonte:** SS §1 (minimo privilegio), §6, SR-012, ASM-045.

#### Autorizzazione e isolamento delle famiglie

**SR-041 · Riferimenti tra oggetti verificati sulla famiglia · M0 · Priorità M**
- **Requisito:** ogni identificativo presente nel corpo o nei parametri di una richiesta (piatto da assegnare, portata, tag, persona, profilo da collegare, pasto di destinazione di uno spostamento o di una copia) si verifica come appartenente alla famiglia dell'account, nella stessa transazione della scrittura. Un riferimento a un oggetto di un'altra famiglia produce "non trovato" e nessuna scrittura.
- **Motivazione:** SR-008 protegge la risorsa indicata nell'URL, ma il caso più frequente di BOLA è il riferimento nel corpo. Per esempio, assegnare a un proprio pasto il piatto di un'altra famiglia ne fa comparire nome e fonti nel proprio piano.
- **Verifica:** test negativi per ogni operazione che accetta riferimenti: un account della famiglia A che usa l'identificativo di un piatto, una persona, un tag o una portata della famiglia B → "non trovato", e il database resta invariato.
- **Fonte:** SS §5, SR-008.

**SR-042 · Isolamento centralizzato e inventario delle autorizzazioni · M0 · Priorità M**
- **Requisito:**
  - il filtro per famiglia si applica in un unico punto dell'accesso ai dati (livello di repository o equivalente), non nei singoli gestori delle richieste. L'architetto valuta come difesa aggiuntiva la Row-Level Security del database (ADR);
  - gli identificativi esposti dall'API non sono sequenziali (UUID casuali o equivalenti);
  - ogni operazione dell'API dichiara nella specifica OpenAPI chi può chiamarla. Un test in CI fallisce se esiste un'operazione senza questa dichiarazione o senza un test negativo "altra famiglia".
- **Motivazione:** un solo endpoint dimenticato espone i dati di tutte le famiglie, minori compresi. Con il filtro centralizzato e il controllo in CI, il nuovo endpoint dimenticato diventa un test rosso.
- **Verifica:** il test di inventario in CI. Revisione del codice: nessuna query sui dati delle famiglie fuori dal livello che applica il filtro.
- **Fonte:** SS §5, NFR-015, SR-008, SR-009.

**SR-043 · Gestione sicura dei link di invito e dei codici · M1 (inviti) / M2 (codici) · Priorità M**
- **Requisito:**
  - aprire un link di invito con una richiesta `GET` non consuma e non modifica nulla. L'accettazione, e anche il rifiuto (FR-009), avviene solo con una richiesta `POST` protetta da CSRF;
  - il segreto del link non finisce nei log del server, del proxy o della piattaforma di hosting, né nell'header `Referer`. Per esempio, sta nel frammento dell'URL (`#`), oppure viene scambiato subito con uno stato lato server seguito da un redirect a un URL senza segreto. La pagina dell'invito usa `Referrer-Policy: no-referrer`;
  - il consumo di un invito o di un codice è atomico: con due accettazioni simultanee dello stesso segreto, al massimo una riesce.
- **Motivazione:** WhatsApp e altre app aprono i link per costruire l'anteprima: un invito consumato da un `GET` verrebbe bruciato dal bot. Un segreto nell'URL finisce nei log di accesso, consultabili da chiunque gestisca l'infrastruttura. Senza atomicità, un link "monouso" fa entrare due persone.
- **Verifica:** test: un `GET` sul link lascia l'invito valido. Ricerca del segreto nei log dopo un'accettazione → zero occorrenze. Test di concorrenza con due accettazioni parallele → una riuscita e un rifiuto generico.
- **Fonte:** SS §4, §9, §10, SR-007, FR-008, FR-009, FR-006.

**SR-044 · Ruolo massimo di un invito · M1 · Priorità M (decisa, SD-1 = b)**
- **Requisito:** un link di invito può assegnare solo il ruolo Membro o Pianificatore. Il ruolo Amministratore si assegna solo dopo l'ingresso, da un Amministratore riautenticato (SR-039, FR-066, M2), oppure in emergenza con il comando di recupero del Gestore (FR-064, M1). A ogni ingresso, gli Amministratori vedono nell'app chi è entrato, quando e con quale ruolo.
- **Motivazione:** il link viaggia su canali non controllati (chat di gruppo, inoltri, backup delle chat). Chi intercetta un invito da Amministratore ottiene il controllo totale della famiglia: può rimuovere gli altri, esportare tutti i dati ed eliminare la famiglia.
- **Verifica:** test: la creazione di un invito con ruolo Amministratore viene rifiutata. Dopo un'accettazione, l'evento è visibile agli Amministratori.
- **Fonte:** SS §1 (minimo privilegio), FR-008, ASM-028.

**SR-045 · Conferma del collegamento di un profilo · M2 · Priorità M (decisa, SD-2 = b)**
- **Requisito:** quando un invito collegato a un profilo senza account viene accettato, l'account entra nella famiglia, ma il trasferimento di gusti, settimana tipo, presenze e storico del profilo avviene solo dopo che un Amministratore conferma, vedendo il nome visualizzato e l'email dell'account che ha accettato. Se l'Amministratore rifiuta, il profilo resta com'è e l'account può essere rimosso.
- **Motivazione:** il profilo contiene la storia di un minore, comprese le abitudini di presenza in casa. Se il link viene intercettato o inoltrato per errore, quei dati passano a uno sconosciuto senza che nessuno se ne accorga.
- **Verifica:** test: dopo l'accettazione e prima della conferma, l'account non vede lo storico del profilo come proprio. Dopo la conferma il trasferimento avviene. Dopo un rifiuto il profilo resta invariato.
- **Fonte:** FR-014, SS §5, GDPR art. 5(1)(f).

**SR-046 · Dati nel client e cache della PWA · M0 (header) / M2 (offline) · Priorità M**
- **Requisito:**
  - le risposte autenticate dell'API hanno `Cache-Control: no-store`. Solo la cache gestita dall'app (SR-026) conserva dati;
  - la cache offline è legata all'identificativo dell'account e si svuota, oltre ai casi di SR-026, anche quando il server risponde che la sessione non è valida, che l'account non appartiene più alla famiglia o che la famiglia è stata eliminata, e quando sullo stesso dispositivo entra un account diverso;
  - lo script del service worker si serve con `Cache-Control: no-cache`, così un aggiornamento di sicurezza arriva a tutti i client.
- **Motivazione:** SR-026 copre il logout volontario. Una persona rimossa dalla famiglia, invece, conserva sul telefono l'ultimo piano con presenze e nomi, e un telefono condiviso mostrerebbe i dati di un account a un altro.
- **Verifica:** test end-to-end: dopo la rimozione dell'account dalla famiglia, la prima apertura online svuota la cache, e una successiva apertura offline non mostra dati. Test degli header.
- **Fonte:** SS §8, FR-054, SR-026, FR-012.

#### Privacy e conservazione

**SR-047 · Pseudonimizzazione effettiva nella cronologia e nei registri · M0 (eventi) / M1 (cronologia) · Priorità M**
- **Requisito:** gli eventi di modifica (FR-061), la cronologia modifiche e il registro di sicurezza fanno riferimento alle persone solo tramite identificativo. Nomi ed email si risolvono al momento della lettura e non vengono copiati nel testo delle voci. Quando un account o un profilo viene eliminato o rimosso, le voci mostrano "utente eliminato", "ex membro" o "persona eliminata" senza residui del nome.
- **Motivazione:** se la descrizione di una modifica salva il nome per esteso (per esempio "Luca: assente a cena"), la cancellazione di SR-017 e di ASM-033 resta incompleta, e il nome continua a esistere in migliaia di righe.
- **Verifica:** test: dopo l'eliminazione di un account con nome e email noti, una ricerca di quel nome e di quell'email in tutte le tabelle del database restituisce zero righe (backup esclusi, coperti da SR-048).
- **Fonte:** GDPR art. 17, SR-017, SR-022, ASM-033.

**SR-048 · Cancellazioni rispettate dopo un ripristino · M1 · Priorità M**
- **Requisito:** il sistema mantiene un registro delle cancellazioni eseguite (account, famiglie, persone rimosse, profili), con solo identificativi e data, conservato almeno quanto il backup più vecchio (≥ 30 giorni). Dopo ogni ripristino da backup, le cancellazioni del registro si riapplicano prima di riaprire il servizio.
- **Motivazione:** ripristinare un backup di 20 giorni prima farebbe risorgere account e famiglie già cancellati, violando il diritto alla cancellazione proprio nel momento di un incidente.
- **Verifica:** la prova di ripristino trimestrale (NFR-006) include un account cancellato dopo il backup. Dopo il ripristino, l'account non esiste. Il risultato si registra in `docs/09-release.md`.
- **Fonte:** GDPR art. 17, NFR-006, SR-017, SR-018.

**SR-049 · Nessun dato per chi non entra in una famiglia · M0 · Priorità M**
- **Requisito:** un login Google senza famiglia, senza invito e senza codice (AC-001.5) non crea un account persistente. Se il flusso richiede uno stato temporaneo, questo si cancella entro 24 ore.
- **Motivazione:** chiunque abbia un account Google può completare il login. Senza questa regola il database accumula dati personali di estranei, senza finalità, e diventa un bersaglio per l'esaurimento delle quote gratuite.
- **Verifica:** test: dopo un login senza famiglia, nessuna riga nella tabella degli account. Dopo 24 ore, nessuno stato temporaneo residuo.
- **Fonte:** SS §8 (minimizzazione), GDPR art. 5(1)(c) ed (e), FR-001.

**SR-050 · Conservazione dei dati delle famiglie inattive · Apertura al pubblico · Priorità M (decisa, SD-4 = b)**
- **Requisito:** una famiglia in cui nessun account accede da 24 mesi riceve un avviso via email agli Amministratori. Se nessuno accede nei 30 giorni successivi, la famiglia si elimina come in FR-016. Un account senza accessi da 24 mesi si tratta allo stesso modo, rispettando il vincolo di FR-011. Deve essere attivo entro l'apertura al pubblico. *Nota del product-analyst:* l'avviso richiede l'invio di email. Per gli account solo Google si usa l'email verificata dell'account. L'avviso rientra tra i flussi consentiti da SR-061.
- **Motivazione:** SR-019 conserva i dati "finché la famiglia esiste", cioè per sempre per una famiglia tester che smette di usare l'app. Il principio di limitazione della conservazione chiede un termine.
- **Verifica:** test con un orologio simulato: famiglia inattiva da 24 mesi → avviso. Dopo altri 30 giorni senza accessi → eliminazione con evento nel registro di sicurezza.
- **Fonte:** GDPR art. 5(1)(e), SR-019.

**SR-051 · Log applicativi e monitoraggio degli errori · M0 · Priorità M (IP: decisa, SD-7 = b)**
- **Requisito:**
  - i log applicativi e di accesso si conservano al massimo 30 giorni, nell'UE;
  - lo strumento di raccolta degli errori (NFR-007) non riceve cookie, header `Authorization`, corpi delle richieste, parametri degli URL che contengono segreti, né contenuti delle famiglie. Lo scrubbing è attivo nella configurazione e coperto da un test. Il session replay è disattivato. Il servizio risiede nell'UE o ha garanzie adeguate (SR-027);
  - gli indirizzi IP nel registro di sicurezza si troncano (ultimo ottetto IPv4, ultimi 80 bit IPv6) dopo 90 giorni.
- **Motivazione:** gli strumenti di monitoraggio degli errori inviano per default richiesta e contesto a un servizio terzo. Senza scrubbing, cookie di sessione e dati dei minori escono dal perimetro. SR-019 fissa la conservazione del solo registro di sicurezza, non quella dei log applicativi.
- **Verifica:** test: un'eccezione provocata in una richiesta con cookie e corpo noti produce un evento senza quei valori. Configurazione della conservazione verificata nel pannello del provider e annotata in `docs/09-release.md`.
- **Fonte:** SS §9, GDPR art. 5(1)(c) ed (e), NFR-007, SR-021.

**SR-052 · Fornitori e registro dei trattamenti · M1 · Priorità M**
- **Requisito:** prima che entrino persone diverse dalla famiglia del Gestore (M1), esistono:
  - un registro delle attività di trattamento (GDPR art. 30) con finalità, categorie di dati, minori compresi, durate di conservazione e misure di sicurezza;
  - per ogni fornitore che tratta dati personali per conto del Gestore (hosting, database, backup, email, monitoraggio degli errori), un accordo di trattamento dei dati (art. 28) accettato, con sede e garanzie per i trasferimenti (SR-027).

  L'informativa (SR-030) spiega che Google, come fornitore dell'accesso, è un titolare autonomo.
- **Motivazione:** SR-027 chiede l'elenco dei fornitori, ma non l'accordo che li vincola. Il trattamento di dati di minori rende difficile sostenere l'esenzione dal registro.
- **Verifica:** il documento del registro esiste ed è citato in `docs/05-data.md`. Ogni fornitore elencato ha la data di accettazione del DPA.
- **Fonte:** GDPR art. 28, 30, SR-027.

**SR-053 · Procedura per le violazioni dei dati · M1 · Priorità M**
- **Requisito:** `docs/09-release.md` contiene la procedura di gestione di una violazione dei dati personali:
  - rilevazione e contenimento: revoca delle sessioni, rotazione dei segreti;
  - valutazione del rischio;
  - notifica al Garante entro 72 ore, quando richiesta;
  - comunicazione agli interessati, quando il rischio è elevato;
  - registrazione di ogni violazione, anche se non notificata (art. 33(5)).

  Esiste un contatto privacy pubblicato nell'informativa. Esiste un comando che revoca tutte le sessioni di tutti gli account.
- **Motivazione:** con dati di minori e dati che rivelano quando una casa è vuota, una violazione è probabilmente da notificare. Senza una procedura scritta, i tempi di 72 ore non si rispettano.
- **Verifica:** la procedura è nel documento. Il comando di revoca globale è coperto da un test. La procedura è provata almeno una volta con una simulazione prima di M2.
- **Fonte:** GDPR art. 33, 34, SS §6.

**SR-054 · Altri diritti degli interessati · M1 · Priorità M**
- **Requisito:**
  - ogni account modifica il proprio nome visualizzato (rettifica, art. 16), che non viene sovrascritto dai login Google successivi (FR-067);
  - le richieste che l'app non copre (opposizione, limitazione, chiarimenti, ed esportazione durante la beta, FR-065) arrivano al contatto privacy di SR-053 e ricevono risposta entro 30 giorni;
  - per i profili senza account i diritti si esercitano tramite l'Amministratore (esportazione della famiglia, modifica o eliminazione del profilo), e l'informativa lo spiega.
- **Motivazione:** i requisiti coprono accesso, portabilità e cancellazione, ma non la rettifica né un canale per gli altri diritti.
- **Verifica:** test: il nome modificato resta dopo un nuovo login Google. Il contatto privacy è presente nell'informativa.
- **Fonte:** GDPR art. 12, 16, 18, 21.

**SR-055 · Presenze come dato riservato e statistiche del Gestore · M1 · Priorità M**
- **Requisito:**
  - settimana tipo, eccezioni di presenza e ospiti si classificano in `docs/05-data.md` come dato personale riservato, perché rivelano quando la casa è vuota e le abitudini dei minori. Non compaiono mai in log, notifiche, statistiche o in una futura condivisione pubblica (ASM-010);
  - le statistiche che il Gestore può consultare (Q-016) sono solo conteggi aggregati su tutte le famiglie (per esempio numero di famiglie, account, piatti, pasti pianificati), mai per singola famiglia identificabile, e mai su presenze o gusti.
- **Motivazione:** la combinazione "chi è assente e quando" è il dato più sensibile del prodotto per la sicurezza fisica delle persone. Le statistiche per famiglia aggirerebbero SR-012.
- **Verifica:** revisione della classificazione in `docs/05-data.md`. Test: le viste o i comandi di statistica del Gestore non accettano un identificativo di famiglia e non leggono le tabelle delle presenze.
- **Fonte:** SR-012, SR-015, ASM-010, Q-016, GDPR art. 25.

**SR-056 · Prova dell'informativa fornita · M1 · Priorità M**
- **Requisito:** per ogni account si conservano la versione dell'informativa privacy e delle condizioni presentate e la data di presa visione. Quando la versione cambia in modo sostanziale, l'account la rivede al login successivo.
- **Motivazione:** AC-013.6 chiede la presa visione, ma senza una registrazione non si può dimostrare (art. 5(2), responsabilizzazione), in particolare per gli account tra 14 e 18 anni.
- **Verifica:** test: dopo l'accettazione di un invito, la versione e la data sono registrate. Un cambio di versione riporta l'account alla pagina dell'informativa.
- **Fonte:** GDPR art. 5(2), 13, SR-030, AC-013.6.

#### Registro di sicurezza e allarmi

**SR-057 · Integrità e completezza del registro di sicurezza · M0 · Priorità M**
- **Requisito:**
  - il registro di sicurezza è in sola aggiunta: il ruolo di database dell'applicazione può inserire e leggere, ma non modificare né cancellare. La pulizia per la conservazione (SR-019) la esegue solo un job dedicato;
  - gli orari sono in UTC, presi dal server;
  - oltre agli eventi di SR-020 si registrano: revoca delle sessioni (SR-038), reimpostazione della password, reinvio dell'email di verifica, superamento di un limite di frequenza, riautenticazione fallita, download di un'esportazione, ogni comando della console compreso il bootstrap, e ogni accesso diretto al database del Gestore (annotato a mano, ASM-045);
  - un accesso negato a una risorsa di un'altra famiglia si registra come tale, anche se l'utente riceve "non trovato".
- **Motivazione:** un registro modificabile dall'applicazione è inutile proprio quando serve, cioè dopo una compromissione dell'applicazione. Gli eventi aggiunti coprono le azioni introdotte dalle altre SR.
- **Verifica:** test: `UPDATE` e `DELETE` sulla tabella del registro con il ruolo dell'applicazione → permesso negato. Un test per ogni evento elencato verifica che venga scritto con attore, esito e ID di correlazione.
- **Fonte:** SS §9, SR-020.

**SR-058 · Allarmi di sicurezza al Gestore · M1 · Priorità S**
- **Requisito:** il Gestore riceve una notifica entro 15 minuti (stesso canale di NFR-007) quando:
  - i login falliti superano 50 in 15 minuti su tutto il sistema;
  - un account accumula più di 10 accessi negati verso altre famiglie in un'ora;
  - un limite di frequenza scatta più di 20 volte in un'ora;
  - viene eseguita la cancellazione definitiva di una famiglia;
  - viene eseguito un comando della console.
- **Motivazione:** un registro che nessuno legge non rileva un attacco in corso. Le soglie riguardano gli schemi tipici: credential stuffing, enumerazione degli identificativi, abuso automatico.
- **Verifica:** test che simulano ogni soglia e verificano l'invio della notifica.
- **Fonte:** SS §9, NFR-007, SR-020.

#### Abusi e limiti

**SR-059 · Valori dei limiti di frequenza · M0 (login Google) / M1 (inviti) / M2 (resto) · Priorità M**
- **Requisito:** sostituisce i valori indicativi di ASM-048.

  | Operazione | Limite |
  |---|---|
  | Login fallito | 5 per identità in 15 minuti, poi ritardo progressivo fino a 15 minuti. 20 per IP in 15 minuti |
  | Callback OIDC e avvio del login | 30 per IP in 15 minuti |
  | Link di invito o codici non validi | 10 per IP in 15 minuti. Codici errati: 5 per account in 15 minuti |
  | Registrazione | 5 per IP all'ora |
  | Recupero password | 3 per email all'ora, 10 per IP all'ora |
  | Reinvio dell'email di verifica | 3 per account all'ora |
  | Import CSV | 5 per famiglia all'ora |
  | Esportazione | 3 per account al giorno, 3 per famiglia al giorno |
  | API autenticata | 300 richieste al minuto per sessione, di cui al massimo 60 scritture |

  Al superamento, il server risponde `429` con `Retry-After` e un messaggio generico. I contatori sono condivisi tra le istanze e sopravvivono a un riavvio.

  *CHG-020:* le righe "Registrazione", "Recupero password" e "Reinvio dell'email di verifica", e il limite per identità del "Login fallito", valgono solo quando FR-002 e FR-003 vengono realizzati (backlog dopo M2). Nell'MVP, per il login Google valgono la riga "Callback OIDC e avvio del login" e il limite per IP del "Login fallito".

  *Rinvio del 2026-10-23 (SL-03b, decisione D2 dell'utente, ADR-0006 rev. 6):* per ora è attivo solo l'**avvio del login** (30 per IP in 15 minuti). Sono **rinviati** il limite "Callback OIDC 30 per IP in 15 minuti" e il limite "Login fallito 20 per IP in 15 minuti": ogni callback che fa lavoro richiede un flusso creato dall'avvio, già limitato; un callback senza flusso non scrive nulla; e il contratto del piano vuole che il callback risponda sempre `302`. Si rivedono con SL-12 o quando torna il login con email e password (FR-002, CHG-020).

  *Algoritmo (ADR-0006 rev. 6, decisione D1):* finestra fissa allineata all'orologio del database; a cavallo di due finestre possono passare fino a 2 volte il limite, rischio accettato per l'MVP.
- **Motivazione:** ASM-048 lasciava i valori a questo ruolo. Contatori in memoria di un'istanza che si riavvia (comune sui piani gratuiti) azzerano la protezione.
- **Verifica:** un test per ogni riga **attiva**: il tentativo oltre il limite riceve `429`. Un test di riavvio del servizio con i contatori preservati. Righe rinviate, senza test finché restano tali: "Callback OIDC" (30 per IP), "Login fallito" (5 per identità e 20 per IP), "Registrazione", "Recupero password", "Reinvio dell'email di verifica".
- **Fonte:** SS §4, §10, SR-003, ASM-048.

**SR-060 · Limiti sulle richieste e quote per famiglia · M0 · Priorità M**
- **Requisito:**
  - corpo delle richieste JSON al massimo 64 KB (1 MB solo per l'import CSV), profondità JSON massima 10, array entro i limiti di ASM-034;
  - paginazione obbligatoria sugli elenchi, al massimo 100 elementi per pagina. Intervallo del piano al massimo 62 giorni;
  - le quote per famiglia di ASM-034 si applicano sul server in modo atomico, anche con richieste concorrenti e con l'import.
- **Motivazione:** un account compromesso o malevolo può esaurire database e quote gratuite, rendendo il servizio indisponibile per tutte le famiglie.
- **Verifica:** test: un corpo di 65 KB → `413`. Una richiesta di 63 giorni di piano → rifiutata. Creazioni concorrenti oltre la quota di 2.000 piatti → mai più di 2.000.
- **Fonte:** SS §2, §10, ASM-034, NFR-004.

**SR-061 · Abuso delle email · Primo flusso email realizzato (backlog dopo M2 con FR-002/FR-003, oppure apertura al pubblico con SR-050), CHG-020; era M2 · Priorità M**
- **Requisito:**
  - l'app invia email solo all'interno dei flussi di verifica, recupero, notifica di SR-036 e SR-034, e avviso di SR-050;
  - le email non contengono testo libero scelto da altri utenti, come nomi di famiglie o note, per non poter essere usate per phishing dal dominio dell'app;
  - un tetto giornaliero globale, inferiore alla quota del provider, genera un allarme all'80%;
  - il dominio mittente ha SPF, DKIM e DMARC con politica almeno `quarantine`.
- **Motivazione:** i flussi email sono il modo classico di usare un servizio per bombardare di messaggi un indirizzo, o per inviare phishing con un mittente affidabile. Esaurire la quota gratuita blocca anche il recupero delle password.
- **Verifica:** test sul contenuto dei modelli di email. Controllo dei record DNS con un tool. Test del tetto giornaliero.
- **Fonte:** SS §4, §10, FR-002, FR-003.

**SR-062 · Protezione dai costi imprevisti · M0 · Priorità S**
- **Requisito:** ogni servizio con fatturazione a consumo ha un avviso di spesa e, dove disponibile, un tetto di spesa. Quando si raggiunge una quota gratuita, il comportamento è un degrado documentato, per esempio la sola lettura o un errore `503`, non un addebito senza limite.
- **Motivazione:** su piani gratuiti un attacco di volume diventa un attacco al portafoglio ("denial of wallet").
- **Verifica:** la configurazione di avvisi e tetti è annotata in `docs/09-release.md` con la data di verifica.
- **Fonte:** visione ("Vincoli"), NFR-014.

**SR-063 · Limiti su inviti e codici · M1 (inviti) / M2 (codici) · Priorità M**
- **Requisito:**
  - una famiglia ha al massimo 20 inviti in sospeso e ne genera al massimo 20 al giorno;
  - i codici di creazione attivi sono al massimo 20 su tutto il sistema;
  - generare un nuovo invito collegato a un profilo revoca il precedente (come in AC-037.2).
- **Motivazione:** ogni invito attivo è una porta d'ingresso valida per 7 giorni. Un numero illimitato aumenta la probabilità che un link circoli fuori controllo, e un account Amministratore compromesso potrebbe generarne a migliaia.
- **Verifica:** test: il 21° invito in sospeso viene rifiutato. Il 21° codice attivo viene rifiutato dalla console.
- **Fonte:** SS §1, SR-007, FR-005, FR-008.

#### Esiti delle decisioni del security engineer

| ID | Decisione | Esito (dec. 2026-10-18) | SR / FR |
|---|---|---|---|
| SD-1 | Ruolo massimo assegnabile con un link di invito | **b**: solo Membro o Pianificatore. Amministratore si assegna dopo l'ingresso. Gli account dai 14 anni possono comunque avere qualunque ruolo. | SR-044, FR-008, FR-066 |
| SD-2 | Collegamento di un profilo a un account | **b**: serve la conferma di un Amministratore prima del trasferimento dei dati. | SR-045, FR-014 |
| SD-3 | Riautenticazione per le operazioni critiche | **b**: login negli ultimi 10 minuti per eliminazione della famiglia e dell'account, esportazione della famiglia, nomina e revoca di un Amministratore. | SR-039, FR-016, FR-017, FR-018, FR-066 |
| SD-4 | Conservazione dei dati delle famiglie inattive | **b**: 24 mesi di inattività, poi avviso e cancellazione dopo 30 giorni. Attivo entro l'apertura al pubblico. | SR-050 |
| SD-5 | Profili dei minori di 14 anni | **b**: dichiarazione di responsabilità genitoriale, o di consenso di chi la esercita, registrata con data. | SR-064, FR-013 |
| SD-6 | Valutazione d'impatto | **b + c**, poi aggiornata con CHG-015: la sezione 8 del threat model diventa DPIA v1 per la beta da M1, rivista e firmata dall'utente. Revisione professionale prima dell'apertura al pubblico. | SR-065 |
| SD-7 | IP nel registro di sicurezza | **b**: completo per 90 giorni, poi troncato. | SR-051, SR-019 |

### Proposte del security engineer
Nessuna proposta in sospeso: tutte sono state integrate il 2026-10-18. Le nuove proposte vanno scritte qui.

## User story

Formato dei criteri: **Dato** … **quando** … **allora** …. Ogni storia cita i suoi FR e SR, la priorità e la milestone. Un rifiuto per permessi mancanti corrisponde a `403`. Un rifiuto su una risorsa di un'altra famiglia corrisponde a `404`, cioè "non trovato".

### US-001 · Accedere con Google · FR-001, FR-004, SR-001, SR-005, SR-033, SR-037, SR-049 · Priorità M · M0
Come persona della famiglia voglio accedere con il mio account Google e restare collegato sul mio telefono, così posso consultare e modificare il piano senza dover fare il login ogni volta.

- **AC-001.1** Dato un account Google associato a una famiglia, quando completo il login Google, allora vedo il piano della settimana corrente della mia famiglia.
- **AC-001.2** Dato un login fatto da meno di 90 giorni e un ultimo utilizzo negli ultimi 30 giorni, quando riapro l'app sullo stesso dispositivo, allora sono ancora autenticato.
- **AC-001.3** Dato che non uso l'app da più di 30 giorni, **oppure** che il login risale a più di 90 giorni fa anche se uso l'app ogni giorno, quando la riapro, allora mi viene chiesto di autenticarmi di nuovo.
- **AC-001.4** Dato che sono autenticato, quando faccio logout, allora la sessione è invalidata sul server e una richiesta successiva con il vecchio cookie viene rifiutata.
- **AC-001.5** (errore) Dato un account Google che non appartiene a nessuna famiglia e non ha un invito né un codice, quando completo il login, allora vedo un messaggio che spiega che serve un invito o un codice di creazione, non vedo nessun dato, e non viene creato nessun account persistente (SR-049).
- **AC-001.6** (errore) Dato che annullo il consenso sulla pagina di Google, quando torno all'app, allora vedo un messaggio generico e resto non autenticato.
- **AC-001.7** (errore) Dato un token Google con `email_verified=false`, oppure con `aud` o `nonce` non validi, quando il server lo riceve, allora il login è rifiutato.
- **AC-001.8** Dato un account Google la cui email è cambiata ma il `sub` è lo stesso, quando faccio login, allora ritrovo il mio account e la mia famiglia.
- **AC-001.9** (errore) Dato più di 30 avvii di login dallo stesso IP in 15 minuti, quando ne avvio un altro, allora ricevo `429` con `Retry-After`.

### US-002 · Creare la famiglia iniziale da console · FR-007, SR-012, SR-020, SR-033 · Priorità M · M0
Come Gestore voglio creare la mia famiglia e nominarmi Amministratore con un comando, così posso usare l'app da subito senza il flusso dei codici.

- **AC-002.1** Dato un'email Google valida, quando eseguo il comando di bootstrap con il nome della famiglia e quell'email, allora la famiglia viene creata, il primo login Google con quell'email verificata ne diventa Amministratore e viene legato al `sub`, e l'evento entra nel registro di sicurezza.
- **AC-002.2** (errore) Dato un argomento mancante o un'email non valida, quando eseguo il comando, allora il comando termina con un errore esplicito e non crea nulla.
- **AC-002.3** Dato che il comando ha avuto successo, quando ne leggo l'output, allora non contiene segreti né dati diversi da identificativo e nome della famiglia.
- **AC-002.4** (errore) Dato un bootstrap creato più di 7 giorni fa e mai riscattato, quando faccio login con quell'email, allora non divento Amministratore e ricevo il messaggio di AC-001.5.

### US-003 · Configurare pasti di default e fuso orario · FR-015, FR-036, FR-060 · Priorità M · M0
Come Amministratore o Pianificatore voglio scegliere quali tipi di pasto compaiono ogni giorno nel piano, così vedo solo i pasti che la mia famiglia pianifica davvero.

- **AC-003.1** Dato che seleziono Pranzo e Cena come pasti di default, quando apro una qualunque settimana, allora ogni giorno mostra solo Pranzo e Cena.
- **AC-003.2** Dato che tolgo Pranzo dai pasti di default, quando apro i giorni che hanno già piatti assegnati a pranzo, allora quei pasti restano visibili con i loro piatti e non viene cancellato nulla.
- **AC-003.3** (caso limite) Dato che deseleziono tutti i pasti di default, quando confermo, allora il sistema accetta la scelta e il piano mostra uno stato vuoto che invita ad aggiungere pasti ai singoli giorni (ASM-049).
- **AC-003.4** (autorizzazione) Dato un Membro, quando tenta di modificare i pasti di default, anche chiamando direttamente il server, allora riceve `403` e la configurazione resta invariata.
- **AC-003.5** Dato un Amministratore, quando modifica il nome della famiglia, allora il nuovo nome compare a tutti gli account. (autorizzazione) Dato un Pianificatore, quando tenta la stessa operazione, allora riceve `403`.
- **AC-003.6** Dato una nuova famiglia, quando la apro, allora il fuso orario è `Europe/Rome`. Dato un Amministratore che lo cambia, quando salva, allora "oggi" e l'inizio della settimana si calcolano nel nuovo fuso. (autorizzazione) Dato un Pianificatore, quando tenta di cambiarlo, allora riceve `403`.

### US-004 · Aggiungere un piatto all'archivio · FR-020, FR-021, FR-024, SR-024 · Priorità M · M0
Come Pianificatore voglio salvare un piatto con portate, stato, note, tempo di preparazione e fonti della ricetta, così ricordo cosa funziona per la mia famiglia e dove trovare la ricetta.

- **AC-004.1** Dato il modulo di un nuovo piatto, quando inserisco il nome "Frittata di zucchine", le portate "secondo" e "piatto unico", lo stato "collaudato", la fascia "meno di 30 minuti" e salvo, allora il piatto compare nell'archivio con tutti questi dati.
- **AC-004.2** Dato un piatto, quando aggiungo una fonte di tipo link con un URL `https` valido e una fonte di tipo libro con titolo e pagina, allora entrambe sono salvate, e toccando il link si apre in una nuova scheda.
- **AC-004.3** (errore) Dato il modulo, quando salvo senza nome oppure senza nessuna portata, allora il salvataggio è rifiutato e il campo mancante viene indicato.
- **AC-004.4** (errore) Dato una fonte di tipo link, quando inserisco `javascript:alert(1)` oppure un testo che non è un URL `http` o `https`, allora la fonte è rifiutata con un messaggio di validazione.
- **AC-004.5** (errore) Dato un nome di oltre 120 caratteri, oppure note di oltre 2.000 caratteri, oppure un'undicesima fonte, quando salvo, allora il salvataggio è rifiutato con l'indicazione del limite.
- **AC-004.6** Dato un nome o delle note che contengono `<script>`, quando il piatto viene mostrato, allora il testo appare letteralmente e non viene eseguito.
- **AC-004.7** Dato un archivio vuoto, quando lo apro, allora vedo un messaggio di stato vuoto con il pulsante per aggiungere il primo piatto.

### US-005 · Cambiare lo stato di un piatto · FR-025, FR-061, SR-010 · Priorità M · M0
Come Pianificatore voglio marcare un piatto come "collaudato", o riportarlo a "da provare", così l'archivio riflette cosa abbiamo davvero sperimentato.

- **AC-005.1** Dato un piatto "da provare", quando lo marco "collaudato", allora lo stato cambia e viene registrato un evento di modifica con data, autore e ruolo dell'autore (serve a KPI-5).
- **AC-005.2** Dato un piatto "collaudato", quando lo riporto a "da provare", allora lo stato cambia e viene registrato l'evento.
- **AC-005.3** Dato un piatto "da provare" cucinato, quando non faccio nulla, allora lo stato resta "da provare": nessun cambio automatico.
- **AC-005.4** (autorizzazione) Dato un Membro (M1 in poi), quando tenta di cambiare lo stato di un qualunque piatto, allora riceve `403`.

### US-006 · Cercare e filtrare l'archivio · FR-030 · Priorità M · M0
Come Pianificatore voglio cercare un piatto per nome e filtrare per portata e stato, così lo trovo in pochi secondi.

- **AC-006.1** Dato un piatto "Pasta e ceci", quando cerco "ceci" oppure "PASTA", allora il piatto compare tra i risultati.
- **AC-006.2** Dato un piatto "Purè di patate", quando cerco "pure", allora il piatto compare (ricerca che ignora gli accenti, ASM-047).
- **AC-006.3** Dato che filtro per portata "contorno" e stato "da provare", quando applico il filtro, allora vedo solo i piatti non archiviati che hanno entrambe le caratteristiche.
- **AC-006.4** Dato un piatto archiviato, quando cerco il suo nome senza il filtro "archiviati", allora non compare. Con il filtro attivo, compare con l'etichetta "archiviato".
- **AC-006.5** (vuoto) Dato una ricerca senza risultati, quando la eseguo, allora vedo "nessun piatto trovato" con l'azione "crea piatto con questo nome".

### US-007 · Archiviare, ripristinare o eliminare un piatto · FR-029 · Priorità M · M0
Come Pianificatore voglio togliere dalle scelte i piatti che non voglio più proporre, senza perdere lo storico dei piani passati.

- **AC-007.1** Dato un piatto mai pianificato, quando lo elimino e confermo, allora il piatto è cancellato definitivamente.
- **AC-007.2** Dato un piatto pianificato almeno una volta, quando scelgo "elimina", allora il sistema offre solo "archivia". Dopo la conferma il piatto non compare più nelle scelte del piano, ma resta visibile nei pasti passati.
- **AC-007.3** Dato un piatto archiviato, quando lo ripristino, allora torna tra le scelte con tutti i suoi dati, fonti e gusti.
- **AC-007.4** Dato un piatto archiviato già assegnato a un pasto futuro, quando apro quel pasto, allora vedo il piatto con l'etichetta "archiviato" e posso sostituirlo.
- **AC-007.5** (autorizzazione) Dato un Membro, quando tenta di archiviare un qualunque piatto, allora riceve `403`.
- **AC-007.7** (CHG-005, Q-028) Dato un piatto assegnato una volta a un pasto e poi tolto, così che non compare in nessun pasto, quando scelgo "elimina", allora il sistema offre solo "archivia".
- **AC-007.6** (errore) Dato un piatto mai pianificato, quando un'altra persona lo assegna a un pasto tra la mia apertura e la mia conferma di eliminazione, allora l'eliminazione definitiva è rifiutata e mi viene proposta l'archiviazione.

### US-008 · Pianificare i pasti della settimana · FR-035, FR-036, FR-037, FR-060, SR-008, SR-041 · Priorità M · M0
Come Pianificatore voglio assegnare uno o più piatti dell'archivio a ogni pasto dei giorni che scelgo, così il piano è pronto in pochi minuti.

- **AC-008.1** Dato la vista della settimana corrente, quando la apro, allora vedo i giorni da lunedì a domenica nel fuso della famiglia, con i pasti di default, e il giorno di oggi evidenziato.
- **AC-008.2** Dato la Cena di martedì, quando assegno "Pasta e ceci" come primo e "Frittata di zucchine" come secondo, allora il pasto mostra entrambi i piatti nell'ordine delle portate.
- **AC-008.3** Dato un giorno senza Merenda di default, quando aggiungo la Merenda solo a quel giorno, allora la Merenda compare solo in quel giorno.
- **AC-008.4** Dato un pasto di default in un giorno, quando lo tolgo da quel giorno, allora sparisce solo da quel giorno.
- **AC-008.5** Dato che scelgo un intervallo dal 1° al 10 del mese, quando confermo, allora il piano mostra quei 10 giorni. (errore) Dato un intervallo di oltre 62 giorni, quando confermo, allora la richiesta è rifiutata con l'indicazione del limite.
- **AC-008.6** (errore) Dato un piatto con portate "secondo" e "piatto unico", quando lo assegno come "primo", allora il sistema non lo permette e propone solo le portate del piatto.
- **AC-008.7** (autorizzazione) Dato un account della famiglia A, quando richiede o modifica un pasto della famiglia B indicandone l'identificativo, oppure assegna a un proprio pasto un piatto della famiglia B, allora riceve "non trovato", nessun dato viene esposto o modificato, e l'accesso negato entra nel registro di sicurezza.
- **AC-008.8** (autorizzazione) Dato un Membro (M1 in poi), quando tenta di assegnare un piatto a un pasto, allora riceve `403`.
- **AC-008.9** (errore) Dato un pasto con già 10 voci, quando ne aggiungo un'undicesima, allora l'aggiunta è rifiutata con l'indicazione del limite (ASM-034).

### US-009 · Usare voci libere e pasti speciali · FR-038, FR-039 · Priorità M · M0
Come Pianificatore voglio scrivere al volo "avanzi di ieri" oppure segnare che a cena andiamo al ristorante, così il piano è completo anche quando non si cucina un piatto dell'archivio.

- **AC-009.1** Dato un pasto, quando aggiungo la voce libera "pizza dal forno", allora la voce compare nel pasto, distinta visivamente dai piatti dell'archivio, e il pasto conta come coperto per KPI-1.
- **AC-009.2** Dato una voce libera, quando scelgo "salva in archivio", indico almeno una portata e confermo, allora nasce un nuovo piatto, "da provare" per default con lo stato modificabile prima di confermare, e nel pasto la voce è sostituita dal piatto (ASM-042).
- **AC-009.3** Dato un pasto, quando lo marco "ristorante", allora il pasto conta come pianificato e coperto per KPI-1, e appare con l'etichetta del tipo speciale.
- **AC-009.4** Dato un pasto passato marcato "fuori casa" che contiene un piatto, quando consulto "ultima volta cucinato" di quel piatto, allora quel pasto non viene contato.
- **AC-009.5** (errore) Dato una voce libera vuota o di oltre 200 caratteri, quando salvo, allora il salvataggio è rifiutato.
- **AC-009.6** (autorizzazione) Dato un Membro (M1 in poi), quando tenta di aggiungere una voce libera o di marcare un pasto speciale, allora riceve `403`.

### US-010 · Vedere quando un piatto è stato cucinato mentre scelgo · FR-034, FR-040, FR-060 · Priorità M · M0
Come Pianificatore voglio vedere da quanti giorni non cuciniamo ogni piatto, e filtrare i "da provare", così vario il menù.

- **AC-010.1** Dato un piatto cucinato l'ultima volta 12 giorni fa, quando apro la selezione per un pasto, allora accanto al piatto vedo "cucinato 12 giorni fa".
- **AC-010.2** Dato un piatto mai cucinato, quando apro la selezione, allora vedo "mai cucinato".
- **AC-010.3** Dato un piatto assegnato a un pasto di **oggi** o di un giorno futuro, quando si calcola "ultima volta cucinato", allora quel pasto non viene contato. Dal giorno successivo, se il pasto non è speciale e il piatto non è marcato "non cucinato", il piatto risulta cucinato in quella data.
- **AC-010.4** Dato il filtro "da provare" attivo nella selezione, quando lo applico, allora vedo solo i piatti "da provare" non archiviati.
- **AC-010.5** Dato un piatto marcato "non cucinato" nel suo ultimo pasto, quando consulto la selezione, allora il valore mostrato si riferisce al pasto precedente in cui è stato cucinato, oppure "mai cucinato".
- **AC-010.6** (CHG-002) Dato M0 o M1, quando apro il selettore dei piatti, allora i piatti sono ordinati per nome (A-Z, senza distinzione tra maiuscole e minuscole né accenti), e non c'è nessun comando per cambiare l'ordinamento.

### US-011 · Correggere i pasti passati · FR-041, FR-061, FR-045 · Priorità M · M0 (contenuto) · AC-011.5-6 in M1
Come Pianificatore voglio correggere ciò che è stato davvero mangiato, anche giorni dopo, così lo storico e "cucinato N giorni fa" restano veri.

- **AC-011.1** Dato un pasto di ieri con "Lasagne", quando marco "Lasagne" come "non cucinato", allora "ultima volta cucinato" delle lasagne torna alla data precedente.
- **AC-011.2** Dato un pasto di ieri, quando sostituisco "Lasagne" con "Risotto", allora "Risotto" risulta cucinato ieri e "Lasagne" no.
- **AC-011.3** Dato una correzione di un pasto passato, quando viene salvata, allora genera un evento di modifica con autore, ruolo e data. Da M1 la correzione è visibile nella cronologia.
- **AC-011.4** (autorizzazione) Dato un Membro, quando tenta di modificare **il contenuto** di un pasto passato, allora riceve `403`.
- **AC-011.5** Dato un pasto di 20 giorni fa, quando un Pianificatore lo corregge, allora l'operazione riesce: nessun limite di tempo per le correzioni.
- **AC-011.6** Dato un Membro presente a un pasto di ieri, quando corregge la propria presenza o gli ospiti di quel pasto, allora l'operazione riesce (vedi US-021 e US-022).

### US-012 · Invitare una persona nella famiglia · FR-008, SR-007, SR-043, SR-044, SR-063, SR-020 · Priorità M · M1
Come Amministratore voglio generare un link di invito con un ruolo e mandarlo su WhatsApp, così una persona della famiglia entra senza che io debba conoscere la sua email.

- **AC-012.1** Dato che scelgo il ruolo "Membro" o "Pianificatore", quando genero un invito, allora ottengo un link copiabile e condivisibile con il menu di condivisione del telefono, valido 7 giorni, e l'invito compare tra quelli in sospeso.
- **AC-012.2** Dato un invito in sospeso, quando lo revoco, allora il link smette di funzionare e l'aprirlo mostra il messaggio generico di invito non valido.
- **AC-012.3** Dato un invito, quando sono passati 7 giorni, allora risulta scaduto e non si può più accettare.
- **AC-012.4** (autorizzazione) Dato un Pianificatore o un Membro, quando tenta di generare, elencare o revocare inviti, allora riceve `403`.
- **AC-012.5** Dato che genero e revoco un invito, quando il Gestore consulta il registro di sicurezza, allora trova i due eventi, senza il segreto del link.
- **AC-012.6** (autorizzazione) Dato un Amministratore, quando tenta di generare un invito con ruolo Amministratore, anche chiamando direttamente il server, allora la richiesta è rifiutata (SR-044).
- **AC-012.7** (errore) Dato 20 inviti in sospeso nella famiglia, quando ne genero un altro, allora la richiesta è rifiutata con l'indicazione del limite.

### US-013 · Accettare o rifiutare un invito · FR-009, FR-068, SR-004, SR-007, SR-013, SR-043, SR-056 · Priorità M · M1
Come persona invitata voglio aprire il link, accedere e dichiarare la mia età, così entro nella famiglia con il ruolo previsto.

- **AC-013.1** Dato un link valido, quando lo apro, accedo con Google (nell'MVP l'unico metodo; email e password solo se FR-002 verrà realizzato dopo M2, CHG-020), dichiaro "ho almeno 14 anni", prendo visione dell'informativa e confermo, allora entro nella famiglia con il ruolo dell'invito. Vengono salvati solo "dichiarato ≥14" e la data, versione e data della presa visione, e l'invito è consumato.
- **AC-013.2** (errore) Dato un link valido, quando dichiaro di avere meno di 14 anni, allora l'accettazione è bloccata, vedo un messaggio che spiega che un adulto può gestire per me un profilo senza account, l'invito resta valido e non si conserva nessun dato dell'età.
- **AC-013.3** (errore) Dato un link scaduto, revocato, già usato, rifiutato o inventato, quando lo apro, allora vedo lo stesso messaggio generico "invito non valido o scaduto".
- **AC-013.4** (errore) Dato un account che appartiene già a una famiglia, quando apre un invito di un'altra famiglia, allora l'accettazione è bloccata con un messaggio esplicito (ASM-050).
- **AC-013.5** (errore) Dato più di 10 link non validi aperti in 15 minuti dallo stesso IP, quando ne apro un altro, allora ricevo `429` con `Retry-After` (SR-059).
- **AC-013.6** (errore) Dato che non confermo la presa visione dell'informativa, quando provo a entrare, allora l'ingresso non avviene e l'invito resta valido.
- **AC-013.7** Dato un link valido, quando un'app di messaggistica lo apre per generare l'anteprima (`GET`), allora l'invito resta valido.
- **AC-013.8** Dato un link valido, quando scelgo "rifiuta" e confermo, allora l'invito è consumato e l'Amministratore lo vede come "rifiutato".
- **AC-013.9** (concorrenza) Dato due persone che accettano contemporaneamente lo stesso link, quando le richieste arrivano, allora al massimo una entra e l'altra riceve il messaggio generico.
- **AC-013.10** (SR-073, CHG-013) Dato che una persona entra con un invito, quando un Amministratore apre l'elenco delle persone o l'evento di ingresso, allora vede il nome visualizzato e l'email verificata dell'account. (autorizzazione) Dato un Pianificatore o un Membro, quando apre lo stesso elenco, allora non vede l'email, e il server non la restituisce.

### US-014 · Assegnare i ruoli Membro e Pianificatore · FR-010, SR-009, SR-020 · Priorità M · M1
Come Amministratore voglio decidere chi può pianificare e chi solo consultare, così il piano lo modificano solo le persone giuste.

- **AC-014.1** Dato un account Membro di 15 anni, quando gli assegno il ruolo Pianificatore, allora **dalla sua richiesta successiva** può modificare il piano (Q-012).
- **AC-014.2** Dato un cambio di ruolo, quando viene salvato, allora finisce nel registro di sicurezza con chi lo ha fatto, su chi, e i ruoli prima e dopo.
- **AC-014.3** Dato un Pianificatore declassato a Membro mentre ha la pagina del piano aperta, quando prova a salvare una modifica, allora riceve `403`.
- **AC-014.4** (autorizzazione) Dato un Pianificatore, quando tenta di cambiare un ruolo, anche il proprio, allora riceve `403`.
- **AC-014.5** (autorizzazione) Dato un Amministratore, quando in M1 tenta di assegnare il ruolo Amministratore tramite questa funzione, allora la richiesta è rifiutata: la nomina di un Amministratore passa da FR-066 (M2) o da FR-064.

### US-015 · Non restare mai senza Amministratore · FR-011, SR-011 · Priorità M · **M1**
Come famiglia vogliamo avere sempre almeno un Amministratore, così la famiglia non resta mai senza gestione.

- **AC-015.1** Dato due Amministratori (nominati con FR-066 o con il recupero di FR-064), quando uno dei due esce dalla famiglia, allora l'operazione riesce.
- **AC-015.2** (errore) Dato un solo Amministratore, quando tenta di uscire, eliminare il proprio account o togliersi il ruolo, allora il sistema blocca l'operazione e spiega il vincolo. In M1 il messaggio spiega solo il vincolo, perché nomina ed eliminazione non esistono ancora. Da M2 il messaggio indica anche come nominare un altro Amministratore (FR-066) o eliminare la famiglia (FR-016). *Precisato con CHG-007, osservazione O-01 di `docs/03-ux.md`.*
- **AC-015.3** (concorrenza) Dato due Amministratori che, contemporaneamente, si tolgono il ruolo a vicenda o escono entrambi, quando entrambe le richieste arrivano, allora al massimo una riesce e resta sempre almeno un Amministratore.

### US-016 · Rimuovere una persona o uscire dalla famiglia · FR-012, SR-005, SR-046, SR-047, SR-020 · Priorità M · M1
Come Amministratore voglio togliere dalla famiglia una persona, e come account voglio poter uscire, così l'accesso riflette chi fa davvero parte della famiglia.

- **AC-016.1** Dato un account Membro, quando l'Amministratore lo rimuove e conferma, allora alla sua richiesta successiva l'account non vede più nessun dato della famiglia, e alla prima apertura online la cache dell'app si svuota.
- **AC-016.2** Dato una persona rimossa, quando consulto piano e cronologia, allora le sue presenze passate e le sue modifiche sono attribuite a "ex membro", senza il suo nome. I suoi gusti, la sua settimana tipo e le sue eccezioni future sono cancellati, e i coperti futuri si aggiornano.
- **AC-016.3** Dato un account, quando sceglie "esci dalla famiglia" e conferma, allora l'uscita avviene come in AC-016.1 e AC-016.2.
- **AC-016.4** (autorizzazione) Dato un Pianificatore, quando tenta di rimuovere una persona, allora riceve `403`.
- **AC-016.5** Dato una persona rimossa, quando consulto l'archivio, allora i piatti che aveva creato sono ancora presenti.

### US-017 · Gestire profili senza account · FR-013, FR-063, SR-014, SR-064 · Priorità M · M1
Come Pianificatore voglio aggiungere i bambini come profili, così conto le loro presenze e i loro gusti anche se non usano l'app.

- **AC-017.1** Dato il nome visualizzato "Giulia", quando creo un profilo senza account e confermo la dichiarazione di responsabilità genitoriale, allora Giulia compare tra le persone della famiglia, è presente per default ai pasti da oggi in avanti (ASM-014) e ha tutti i gusti "sconosciuto". La dichiarazione è registrata con data e autore.
- **AC-017.2** (errore) Dato un nome vuoto o di oltre 60 caratteri, oppure la dichiarazione non confermata, quando salvo, allora il salvataggio è rifiutato.
- **AC-017.3** Dato un profilo, quando lo elimino e confermo, allora gusti, settimana tipo ed eccezioni future del profilo sono cancellati, i coperti futuri si aggiornano, e piano e cronologia passati lo indicano come "persona eliminata".
- **AC-017.4** (autorizzazione) Dato un Membro, quando tenta di creare o modificare un profilo, allora riceve `403`.
- **AC-017.5** Dato il modulo del profilo, quando lo apro, allora non ci sono campi per cognome, data di nascita o foto.
- **AC-017.6** Dato un profilo creato oggi, quando apro i pasti di ieri e dei giorni precedenti, allora il profilo non compare tra i presenti né tra gli assenti, e i coperti di quei pasti non cambiano.

### US-018 · Esprimere i gusti sui piatti · FR-027 · Priorità M · M1
Come persona della famiglia voglio dire se un piatto mi piace, mi è indifferente o non mi piace, così chi pianifica ne tiene conto.

- **AC-018.1** Dato un piatto, quando scelgo "non piace", allora il mio gusto su quel piatto è "non piace" ed è visibile a tutti gli account della famiglia.
- **AC-018.2** Dato un mio gusto espresso, quando lo rimuovo, allora torna "sconosciuto".
- **AC-018.3** Dato un Pianificatore, quando imposta "piace" per il profilo senza account "Giulia", allora il gusto viene salvato su Giulia.
- **AC-018.4** (autorizzazione) Dato un Membro, quando tenta di impostare il gusto di un'altra persona o di un profilo, allora riceve `403`.
- **AC-018.5** Dato la scheda di un piatto, quando la apro, allora vedo il gusto di ogni persona della famiglia, con "sconosciuto" dove non è stato espresso.

### US-019 · Proporre un piatto da provare come Membro · FR-028, FR-023, SR-010 · Priorità M · M1
Come Membro voglio salvare l'idea di un piatto visto in un reel, così chi pianifica la trova tra i "da provare".

- **AC-019.1** Dato un Membro, quando crea il piatto "Shakshuka" con una fonte link al reel, allora il piatto è salvato con stato "da provare" e autore il Membro.
- **AC-019.2** (autorizzazione) Dato un Membro, quando invia la creazione di un piatto con stato "collaudato", anche chiamando direttamente il server, allora la richiesta è rifiutata con `403` e nessun piatto viene creato.
- **AC-019.3** Dato un piatto creato dal Membro, ancora "da provare" e mai pianificato, quando il Membro lo modifica o lo elimina, allora l'operazione riesce.
- **AC-019.4** (autorizzazione) Dato un piatto creato da altri, oppure già pianificato, oppure già "collaudato", quando il Membro tenta di modificarlo, archiviarlo o eliminarlo, allora riceve `403`.
- **AC-019.5** (M2) Dato un piatto modificabile dal Membro, quando gli assegna un tag esistente, allora l'operazione riesce. (autorizzazione) Dato lo stesso Membro, quando tenta di creare un tag nuovo, allora riceve `403` (ASM-055).

### US-020 · Impostare la settimana tipo · FR-049, FR-050, FR-063 · Priorità M · M1
Come persona della famiglia voglio indicare una volta sola in quali pasti della settimana di solito sono assente, così i coperti sono giusti senza segnarlo ogni volta.

- **AC-020.1** Dato che segno "assente" a Pranzo da lunedì a venerdì nella mia settimana tipo, quando apro una settimana futura, allora risulto assente a quei pranzi e presente agli altri pasti.
- **AC-020.2** Dato una persona senza settimana tipo, quando apro qualunque pasto da quando è entrata nella famiglia, allora risulta presente.
- **AC-020.3** Dato la settimana tipo, quando la modifico, allora valgono anche le righe dei tipi di pasto non di default (per esempio la Merenda), ma non c'è una riga per "Altro pasto".
- **AC-020.4** Dato un "Altro pasto" aggiunto a un giorno, quando lo apro, allora tutte le persone della famiglia in quel giorno risultano presenti, qualunque sia la loro settimana tipo.
- **AC-020.5** Dato un'eccezione già registrata su un pasto futuro, quando cambio la settimana tipo, allora l'eccezione resta valida e prevale sulla settimana tipo.
- **AC-020.6** (autorizzazione) Dato un Membro, quando tenta di modificare la settimana tipo di un'altra persona, allora riceve `403`. Un Pianificatore invece ci riesce.
- **AC-020.7** Dato che oggi cambio la mia settimana tipo da "presente" ad "assente" per la Cena del lunedì, quando apro la Cena di lunedì scorso, allora risulto ancora presente: il passato non cambia (FR-063). La modifica vale per la Cena di oggi, se oggi è lunedì, e per quelle successive.
- **AC-020.8** (CHG-003, M2) Dato due "Altro pasto" nello stesso giorno ("Aperitivo" e "Dopocena"), quando li apro, allora in entrambi tutte le persone risultano presenti per default. Un'assenza segnata in "Aperitivo" non cambia le presenze di "Dopocena".

### US-021 · Segnare o correggere un'assenza · FR-051, FR-041, FR-061 · Priorità M · M1
Come persona della famiglia voglio segnare che giovedì sera non ci sarò, o correggere a posteriori che ieri non c'ero, così chi cucina sa per quanti preparare e lo storico è vero.

- **AC-021.1** Dato la Cena di giovedì prossimo, in cui risulto presente, quando segno "assente", allora risulto assente solo a quella cena e i coperti scendono di uno.
- **AC-021.2** Dato una mia eccezione, quando la rimuovo, allora torna a valere la settimana tipo in vigore per quel giorno.
- **AC-021.3** Dato un'eccezione inserita da un account con ruolo Membro, quando si calcola KPI-7, allora quella settimana conta come settimana di partecipazione.
- **AC-021.4** ~~RIMOSSO~~ (dec. 2026-10-18, OBJ-01). Vietava al Membro di correggere le proprie presenze passate. Sostituito da AC-021.6 e AC-021.7.
- **AC-021.5** Dato un Pianificatore, quando segna l'assenza del profilo "Giulia" a un pasto passato, allora l'operazione riesce ed entra nella cronologia.
- **AC-021.6** Dato un Membro che ieri risultava presente a cena, quando corregge la propria presenza in "assente", allora l'operazione riesce, i coperti di quel pasto si aggiornano e la correzione entra nella cronologia con autore e ruolo.
- **AC-021.7** (autorizzazione) Dato un Membro, quando tenta di modificare la presenza di un'altra persona, su qualunque pasto, allora riceve `403`.
- **AC-021.8** (errore) Dato un pasto di un giorno precedente al mio ingresso nella famiglia, quando tento di segnarmi presente, allora la richiesta è rifiutata (ASM-058).

### US-022 · Aggiungere ospiti a un pasto · FR-052 · Priorità M · M1
Come persona presente a un pasto voglio indicare che vengono i nonni, così i coperti includono anche loro.

- **AC-022.1** Dato la Cena di sabato, a cui risulto presente, quando imposto 2 ospiti con la nota "nonni", allora il pasto mostra "2 ospiti: nonni" e i coperti aumentano di 2.
- **AC-022.2** (errore) Dato un numero di ospiti negativo, non intero o maggiore di 50, oppure una nota di oltre 200 caratteri, quando salvo, allora il salvataggio è rifiutato.
- **AC-022.3** (autorizzazione) Dato un Membro assente a quel pasto, quando tenta di modificare gli ospiti, allora riceve `403`.
- **AC-022.4** Dato un pasto con ospiti, quando si calcolano gli avvisi "non piace" (M2), allora gli ospiti non vengono considerati.
- **AC-022.5** Dato un Membro presente alla cena di ieri, quando corregge il numero di ospiti di quel pasto, allora l'operazione riesce ed entra nella cronologia.

### US-023 · Vedere coperti e presenti · FR-053 · Priorità M · M1
Come Pianificatore voglio vedere per ogni pasto quante persone ci saranno e chi, così cucino la quantità giusta.

- **AC-023.1** Dato 4 persone di cui 1 assente e 2 ospiti, quando apro il pasto, allora vedo "5 coperti", i nomi dei 3 presenti, il nome dell'assente e "2 ospiti".
- **AC-023.2** Dato una famiglia con un'unica persona (il Gestore in M0), quando apro un pasto, allora i coperti sono 1 più gli eventuali ospiti.
- **AC-023.3** Dato un pasto "saltato", "fuori casa" o "ristorante", quando lo apro, allora vedo presenti e ospiti, ma non i coperti come quantità da cucinare (ASM-052).
- **AC-023.4** (autorizzazione) Dato un account di un'altra famiglia, quando richiede i presenti di un pasto di questa famiglia, allora riceve "non trovato".

### US-024 · Consultare il piano da telefono · FR-047, FR-062, NFR-001, NFR-008, NFR-009 · Priorità M · M1
Come Membro voglio vedere sul telefono cosa si mangia nei prossimi giorni e chi c'è, così so cosa aspettarmi senza chiedere.

- **AC-024.1** Dato un Membro autenticato, quando apre l'app, allora vede la settimana corrente con piatti, voci libere, pasti speciali, presenti e coperti, senza comandi per modificare il contenuto dei pasti.
- **AC-024.2** Dato un piatto del piano, quando lo tocca, allora vede le fonti della ricetta e i gusti.
- **AC-024.3** Dato uno schermo largo 360 px, quando apre la vista settimana, allora non c'è scorrimento orizzontale della pagina.
- **AC-024.4** Dato una settimana senza piatti, quando la apre, allora vede uno stato vuoto "piano non ancora pronto" (NFR-013).
- **AC-024.5** Dato che un account apre il piano più volte nella stessa settimana, quando si consulta il dato delle visite settimanali, allora per quell'account e quella settimana esiste un solo dato "visitato", senza pagine viste (FR-062a).
- **AC-024.6** (CHG-004) Dato che un account apre il piano, quando si consulta il dato dell'ultima visita, allora per quell'account esiste un solo valore, uguale all'ora di questa apertura, che sostituisce il precedente. Non esiste uno storico delle visite (FR-062b).
- **AC-024.7** (CHG-004, autorizzazione) Dato un altro account della famiglia, quando tenta di leggere l'ultima visita di questo account tramite il server, allora non esiste un'operazione che la restituisca.

### US-025 · Spostare e scambiare piatti e pasti · FR-042 · Priorità M · M1
Come Pianificatore voglio spostare la cena di martedì a mercoledì, o scambiare due piatti, così adatto il piano agli imprevisti in un attimo.

- **AC-025.1** Dato la Cena di martedì con 2 piatti, quando la sposto alla Cena di mercoledì, che è vuota, allora piatti, voci libere e stato speciale passano a mercoledì e martedì resta vuoto. Presenze e ospiti restano legati al giorno (ASM-053).
- **AC-025.2** Dato due pasti pieni, quando li scambio, allora i contenuti si invertono.
- **AC-025.3** Dato un singolo piatto, quando lo sposto su un altro pasto, allora sparisce dal pasto di origine e compare in quello di destinazione con la stessa portata.
- **AC-025.4** (caso limite) Dato una destinazione non vuota per lo spostamento di un intero pasto, quando confermo, allora il sistema chiede "sostituisci, unisci o annulla".
- **AC-025.5** (autorizzazione) Dato un Membro, quando tenta uno spostamento, allora riceve `403`.

### US-026 · Copiare un giorno o una settimana · FR-043 · Priorità M · M1
Come Pianificatore voglio partire da una settimana passata che è andata bene, così compongo il nuovo piano in pochi minuti.

- **AC-026.1** Dato la settimana scorsa pianificata, quando la copio sulla prossima, che è vuota, allora ogni pasto viene copiato nel giorno corrispondente con piatti, voci libere e stato speciale, ma senza presenze né ospiti.
- **AC-026.2** (caso limite) Dato una destinazione con alcuni pasti già pieni, quando copio, allora il sistema chiede "sostituisci, aggiungi o annulla" e applica la scelta a tutti i pasti coinvolti.
- **AC-026.3** Dato un pasto di origine con un piatto ora archiviato, quando copio, allora quel piatto non viene copiato e un riepilogo lo segnala.
- **AC-026.4** Dato un giorno di origine con una Merenda non di default, quando lo copio, allora la Merenda viene aggiunta anche al giorno di destinazione.
- **AC-026.5** (autorizzazione) Dato un Membro, quando tenta una copia, allora riceve `403`.

### US-027 · Non perdere modifiche fatte in contemporanea · FR-044 · Priorità M · M1
Come Pianificatore voglio essere avvisato se qualcuno ha cambiato lo stesso pasto mentre lo modificavo, così non cancelliamo il lavoro l'uno dell'altro senza accorgercene.

- **AC-027.1** Dato che A e B aprono il contenuto della stessa Cena e A salva per primo, quando B salva, allora B vede il messaggio "pasto modificato da A alle <ora>" con il nuovo contenuto e la scelta tra "ricarica" e "sovrascrivi".
- **AC-027.2** Dato che B sceglie "ricarica", quando la vista si aggiorna, allora le modifiche non salvate di B sono scartate e vede la versione di A.
- **AC-027.3** Dato che B sceglie "sovrascrivi", quando conferma, allora viene salvata la versione di B e la cronologia registra entrambe le modifiche.
- **AC-027.4** Dato modifiche contemporanee su pasti diversi, quando entrambe vengono salvate, allora non c'è nessun conflitto.
- **AC-027.5** Dato due modifiche contemporanee della stessa unità (la presenza della stessa persona allo stesso pasto, gli ospiti dello stesso pasto, la stessa scheda di un piatto o la stessa settimana tipo), quando la seconda viene salvata, allora il comportamento è lo stesso di AC-027.1.
- **AC-027.6** Dato che A modifica il contenuto della Cena di martedì e, nello stesso momento, B segna la propria assenza a quella Cena, quando entrambe vengono salvate, allora nessuna delle due va in conflitto e il pasto mostra sia il nuovo contenuto sia la nuova presenza.
- **AC-027.7** Dato che due persone segnano contemporaneamente la propria presenza allo stesso pasto, quando entrambe salvano, allora non c'è conflitto, perché ogni persona è un'unità a sé.

### US-028 · Vedere chi ha cambiato cosa · FR-045, FR-046, SR-022, SR-047 · Priorità M · M1
Come persona della famiglia voglio vedere chi ha cambiato il piano o le presenze e quando, così capisco le modifiche senza chiedere in giro.

- **AC-028.1** Dato una modifica a un pasto, quando apro la cronologia di quel giorno, allora vedo autore, ruolo dell'autore in quel momento, data e ora, e la descrizione della modifica (per esempio "Cena: aggiunto Risotto").
- **AC-028.2** (Should, FR-046) Dato un pasto modificato da un altro dopo la mia ultima visita, quando apro il piano, allora il pasto mostra "modificato da <nome> il <data e ora>".
- **AC-028.7** (Should, FR-046, CHG-004) Dato che ho visto il piano sul telefono dopo l'ultima modifica di un altro, quando lo apro dal computer, allora l'indicatore per quel pasto non compare, perché l'ultima visita è conservata sul server. Dato invece che la modifica l'ho fatta io, quando apro il piano, allora l'indicatore non compare mai.
- **AC-028.3** (autorizzazione) Dato un account di un'altra famiglia, quando richiede la cronologia di questa famiglia, allora riceve "non trovato".
- **AC-028.4** (autorizzazione) Dato la cronologia, quando un utente qualsiasi tenta di modificarla o cancellarla, allora l'operazione non esiste nell'interfaccia e il server la rifiuta.
- **AC-028.5** Dato eventi registrati in M0, prima che esistesse la cronologia visibile, quando apro la cronologia in M1, allora vedo anche quegli eventi.
- **AC-028.6** Dato un autore che in seguito ha cambiato ruolo, quando apro una sua modifica passata, allora vedo il ruolo che aveva al momento della modifica.

### US-029 · Accedere con email e password · FR-002, FR-003, SR-002, SR-004, SR-006, SR-034, SR-035, SR-036, SR-059 · Priorità W (rinviata, CHG-020) · Backlog dopo M2
> *Rinviata con CHG-020 (decisione dell'utente del 2026-10-19, gate G4): tutte le famiglie tester hanno un account Google. Era Priorità M, M2. La storia e i criteri restano invariati come riferimento per quando verrà ripresa; non entrano nelle slice di M0-M2.*

Come persona invitata senza account Google voglio creare un account con email e password, così posso entrare nella famiglia.

- **AC-029.1** Dato un invito valido, quando scelgo email e password, inserisco una password di 12-128 caratteri non presente tra le password compromesse e verifico l'email con il link ricevuto, allora l'account si attiva e accetto l'invito.
- **AC-029.2** (errore) Dato una password di meno di 12 o più di 128 caratteri, oppure compromessa, quando la invio, allora è rifiutata con il motivo.
- **AC-029.3** (errore) Dato un account non verificato, quando tenta di accedere ai dati, allora viene rimandato alla verifica. Dopo 7 giorni senza verifica, l'account viene cancellato.
- **AC-029.4** (errore) Dato credenziali errate, quando faccio login, allora vedo "credenziali non valide", lo stesso messaggio, con tempi indistinguibili, sia che l'email esista sia che non esista.
- **AC-029.5** Dato che chiedo il recupero della password, quando inserisco un'email, esistente o no, allora vedo lo stesso messaggio di conferma. Se l'email esiste, ricevo un link monouso valido 1 ora. Dopo il cambio password tutte le mie sessioni sono invalidate e ricevo un'email di notifica.
- **AC-029.6** (errore) Dato 5 tentativi di login falliti in 15 minuti sulla stessa email, quando tento ancora, allora ricevo `429` con `Retry-After` e un ritardo progressivo, ma l'account non viene bloccato in modo permanente.
- **AC-029.7** (autorizzazione) Dato una richiesta di registrazione con email e password senza un invito o un codice validi, quando arriva al server, allora è rifiutata: non esiste una registrazione aperta.
- **AC-029.8** Dato un'email già usata da un account Google, quando un'altra persona prova a registrarla con una password in un flusso di invito, allora riceve la stessa risposta di una registrazione nuova, nessun accesso all'account esistente viene concesso, e all'indirizzo arriva un'email informativa.

### US-030 · Ricevere la proposta di promuovere un piatto provato · FR-026 · Priorità M · M2
Come Pianificatore voglio che l'app mi chieda se un piatto appena provato diventa "collaudato", così l'archivio si aggiorna senza che debba ricordarmelo.

- **AC-030.1** Dato un piatto "da provare" che risulta cucinato per la prima volta (pasto passato, non speciale, non marcato "non cucinato"), quando un Pianificatore o un Amministratore apre il piano o l'archivio, allora vede la proposta "promuovere a collaudato?".
- **AC-030.2** Dato che accetto la proposta, quando confermo, allora il piatto diventa "collaudato" e si registra l'evento.
- **AC-030.3** Dato che ignoro la proposta, quando riapro l'app, allora la proposta per quel piatto non viene più mostrata finché il piatto non viene cucinato di nuovo.
- **AC-030.4** (autorizzazione) Dato un Membro, quando apre l'app, allora non vede la proposta, e se tenta di accettarla chiamando il server riceve `403`.

### US-031 · Essere avvisato se un piatto non piace a un presente · FR-048 · Priorità M · M2
Come Pianificatore voglio sapere se a uno dei presenti un piatto non piace, così posso proporre quel piatto quando quella persona non c'è.

- **AC-031.1** Dato che a Luca "Fegato alla veneziana" non piace e Luca è presente alla Cena di martedì, quando scelgo quel piatto per quella cena, allora vedo l'avviso "non piace a: Luca" e posso comunque assegnarlo.
- **AC-031.2** Dato che Luca è assente alla Cena di mercoledì, quando scelgo lo stesso piatto per quella cena, allora non compare nessun avviso.
- **AC-031.3** Dato che il gusto di Luca è "neutro" o "sconosciuto", quando scelgo il piatto, allora non compare nessun avviso.
- **AC-031.4** Dato un piatto già assegnato e un cambio di presenza che rende Luca presente, quando apro il piano, allora il pasto mostra l'avviso.
- **AC-031.5** Dato un profilo senza account a cui il piatto non piace, quando è presente, allora l'avviso lo include.

### US-032 · Usare tag e tempi di preparazione · FR-023, FR-031 · Priorità M · M2
Come Pianificatore voglio etichettare i piatti (veloce, estivo…) e filtrare per tempo di preparazione, oppure ordinarli per "non cucinato da più tempo", così trovo idee adatte al giorno.

- **AC-032.1** Dato che scrivo un tag nuovo "estivo" su un piatto, quando salvo, allora il tag viene creato per la famiglia e assegnato al piatto.
- **AC-032.2** Dato il filtro tag "veloce" e la fascia "meno di 30 minuti", quando lo applico, allora vedo solo i piatti che hanno entrambe le caratteristiche.
- **AC-032.3** Dato l'ordinamento "non cucinato da più tempo", quando lo applico, allora vengono prima i piatti mai cucinati, poi gli altri dal meno recente al più recente.
- **AC-032.4** Dato un tag rinominato in "rapido", quando apro i piatti che lo avevano, allora mostrano "rapido".
- **AC-032.5** (errore) Dato un tag vuoto oppure di oltre 30 caratteri, oppure un ventunesimo tag sullo stesso piatto, quando salvo, allora il salvataggio è rifiutato.
- **AC-032.6** (autorizzazione) Dato un Membro, quando tenta di creare, rinominare o eliminare tag della famiglia, allora riceve `403`.

### US-033 · Aggiungere portate personalizzate · FR-022 · Priorità S · M2
Come Pianificatore voglio aggiungere una portata come "aperitivo", così l'archivio rispecchia le nostre abitudini.

- **AC-033.1** Dato la portata nuova "aperitivo", quando la creo, allora è disponibile per i piatti della mia famiglia e non per le altre famiglie.
- **AC-033.2** (errore) Dato una portata con lo stesso nome di una esistente, senza distinzione tra maiuscole e minuscole, quando la creo, allora la creazione è rifiutata. Valgono le personalizzate della famiglia e i nomi riservati delle portate base in ogni lingua supportata, elencati nella configurazione del server (per esempio "Primo", "primo", e in futuro anche le traduzioni). *Precisato con CHG-005, Q-030.*
- **AC-033.3** (errore) Dato una portata personalizzata usata da almeno un piatto o da un pasto, quando tento di eliminarla, allora l'eliminazione è rifiutata con il numero di utilizzi.
- **AC-033.4** Dato una portata della lista base, quando tento di rinominarla o eliminarla, allora l'operazione non è disponibile.
- **AC-033.5** (autorizzazione) Dato un Membro, quando tenta di creare una portata, allora riceve `403`.

### US-034 · Essere avvisato di piatti simili · FR-032 · Priorità S · M2
Come Pianificatore voglio vedere i piatti con nome simile mentre ne creo uno nuovo, così evito doppioni involontari.

- **AC-034.1** Dato un piatto esistente "Pasta e ceci", quando digito "pasta ceci" nel nome di un nuovo piatto, allora vedo "piatti simili: Pasta e ceci" con un collegamento al piatto.
- **AC-034.2** Dato l'avviso, quando salvo comunque, allora il nuovo piatto viene creato.
- **AC-034.3** Dato un piatto archiviato con nome simile, quando digito, allora compare nell'avviso con l'etichetta "archiviato" e, per Pianificatori e Amministratori, la possibilità di ripristinarlo.

### US-035 · Importare piatti da CSV · FR-033, SR-025, NFR-003 · Priorità C · M2
Come Pianificatore voglio caricare in una volta la lista dei piatti che ho già su carta o su un foglio di calcolo, così non li inserisco uno per uno.

- **AC-035.1** Dato un file CSV valido secondo ASM-040 con 50 righe, quando lo carico, allora vedo un'anteprima con il conteggio delle righe valide, di quelle con errori (con numero di riga e motivo) e dei duplicati.
- **AC-035.2** Dato l'anteprima, quando confermo, allora vengono creati solo i piatti delle righe valide. I duplicati vengono saltati, a meno che non scelga "importa comunque". Al termine vedo un riepilogo.
- **AC-035.3** (errore) Dato un file oltre 1 MB, oltre 1.000 righe, non UTF-8 o senza la riga di intestazione attesa, quando lo carico, allora viene rifiutato per intero con il motivo.
- **AC-035.4** (errore) Dato una riga con una portata inesistente, uno stato non valido o un URL non `http` o `https`, quando viene validata, allora è segnata come errore e non viene importata.
- **AC-035.5** Dato una cella che inizia con `=`, quando viene importata, allora è salvata come testo e non viene mai interpretata come formula.
- **AC-035.6** (autorizzazione) Dato un Membro, quando tenta l'import, allora riceve `403`.
- **AC-035.7** (errore) Dato un import che porterebbe l'archivio oltre 2.000 piatti, quando confermo, allora vengono importate solo le righe entro la quota, e il riepilogo indica quelle escluse.

### US-036 · Creare una famiglia con un codice · FR-005, FR-006, FR-068, SR-007, SR-043, SR-063, SR-020 · Priorità M · M2
Come Gestore voglio dare a un amico un codice per creare la sua famiglia, e come amico tester voglio usarlo, così entriamo nella fase di test a registrazione chiusa.

- **AC-036.1** Dato il comando di emissione, quando lo eseguo, allora ottengo un codice monouso valido 30 giorni (ASM-038). L'evento entra nel registro di sicurezza senza il codice in chiaro.
- **AC-036.2** Dato un utente autenticato che non appartiene a nessuna famiglia, quando inserisce un codice valido e il nome della famiglia, dichiara di avere almeno 14 anni, prende visione dell'informativa e conferma, allora la famiglia viene creata, l'utente ne è Amministratore e il codice è consumato.
- **AC-036.3** (errore) Dato un codice usato, revocato, scaduto o inventato, quando viene inserito, allora l'utente vede un messaggio generico e non nasce nessuna famiglia.
- **AC-036.4** Dato il comando di elenco, quando lo eseguo, allora vedo i codici con stato e date, ma nessun contenuto delle famiglie create.
- **AC-036.5** (autorizzazione) Dato un qualunque account dell'app, Amministratori compresi, quando tenta di emettere un codice tramite l'interfaccia o il server, allora non esiste nessuna operazione disponibile.
- **AC-036.6** (errore) Dato più di 5 codici errati in 15 minuti dallo stesso account, o più di 10 dallo stesso IP, quando ne inserisce un altro, allora riceve `429` con `Retry-After`.
- **AC-036.7** (autorizzazione) Dato un account che appartiene già a una famiglia, quando inserisce un codice valido, allora la creazione è rifiutata e il codice resta valido (ASM-050).
- **AC-036.8** (errore) Dato 20 codici attivi, quando il Gestore ne emette un altro, allora il comando lo rifiuta.

### US-037 · Collegare un profilo a un account · FR-014, FR-008, FR-009, SR-045, SR-063 · Priorità M · M2
Come Amministratore voglio invitare mio figlio, che ha compiuto 14 anni, collegando l'invito al suo profilo, così conserva i suoi gusti e lo storico delle presenze.

- **AC-037.1** Dato il profilo "Marco jr", quando genero un invito collegato a quel profilo, lui lo accetta dichiarando di avere almeno 14 anni, e un Amministratore conferma il collegamento vedendo nome visualizzato ed email dell'account, allora l'account eredita gusti, settimana tipo, eccezioni e storico del profilo, e il profilo non esiste più come persona separata.
- **AC-037.2** Dato un profilo che ha già un invito collegato in sospeso, quando ne genero un altro, allora il primo viene revocato automaticamente.
- **AC-037.3** (errore) Dato che chi accetta dichiara di avere meno di 14 anni, quando conferma, allora l'accettazione è bloccata e il profilo resta invariato.
- **AC-037.4** (autorizzazione) Dato un Pianificatore, quando tenta di generare un invito collegato a un profilo o di confermare un collegamento, allora riceve `403`.
- **AC-037.5** Dato un invito collegato accettato ma non ancora confermato, quando l'account apre l'app, allora è nella famiglia con il ruolo dell'invito, ma non vede gusti né storico del profilo come propri, e il profilo resta una persona separata.
- **AC-037.6** Dato che l'Amministratore rifiuta il collegamento, quando conferma il rifiuto, allora il profilo resta invariato e all'Amministratore viene proposto di rimuovere l'account.
- **AC-037.7** (errore) Dato un profilo eliminato dopo la generazione dell'invito collegato, quando qualcuno apre il link, allora riceve il messaggio generico "invito non valido o scaduto".
- **AC-037.8** (errore) Dato un account che appartiene già a una famiglia, quando apre un invito collegato a un profilo, allora l'accettazione è bloccata (ASM-050) e il profilo resta invariato.

### US-038 · Eliminare la famiglia con periodo di ripensamento · FR-016, SR-018, SR-039, SR-020 · Priorità M · M2
Come Amministratore voglio eliminare definitivamente la famiglia e i suoi dati, con 7 giorni per ripensarci, così esercito il diritto alla cancellazione senza rischiare errori irreparabili.

- **AC-038.1** Dato che mi sono autenticato negli ultimi 10 minuti, quando richiedo l'eliminazione e confermo scrivendo il nome della famiglia, allora la famiglia entra in sola lettura per tutti, con un avviso che indica la data di cancellazione.
- **AC-038.2** Dato il periodo di ripensamento in corso, quando un Amministratore riautenticato annulla, allora la famiglia torna pienamente utilizzabile.
- **AC-038.3** Dato che sono passati 7 giorni senza annullamento, quando scatta la cancellazione, allora tutti i dati della famiglia sono eliminati in modo definitivo e gli account che appartenevano solo a quella famiglia vedono la schermata "nessuna famiglia".
- **AC-038.4** (autorizzazione) Dato un Pianificatore o un Membro, quando tenta di richiedere o annullare l'eliminazione, allora riceve `403`.
- **AC-038.5** Dato richiesta, annullamento ed esecuzione, quando consulto il registro di sicurezza, allora trovo tutti e tre gli eventi.
- **AC-038.6** (errore) Dato un'autenticazione di più di 10 minuti fa, quando richiedo o annullo l'eliminazione, allora ricevo "riautenticazione richiesta" e non succede nulla.
- **AC-038.7** Dato il periodo di ripensamento in corso, quando un Pianificatore tenta di modificare un pasto, allora la richiesta è rifiutata con l'indicazione della data di cancellazione. Quando invece un Membro esce dalla famiglia o chiede l'esportazione dei propri dati, l'operazione riesce.

### US-039 · Eliminare il mio account · FR-017, SR-017, SR-039, SR-047 · Priorità M · M2
Come persona con account voglio cancellare il mio account in autonomia, così i miei dati non restano nel sistema.

- **AC-039.1** Dato che mi sono autenticato negli ultimi 10 minuti, quando confermo l'eliminazione, allora le mie sessioni sono invalidate, i miei dati personali sono cancellati, e le mie modifiche e presenze passate risultano di "utente eliminato".
- **AC-039.2** (errore) Dato che sono l'ultimo Amministratore, quando chiedo l'eliminazione, allora è bloccata come in AC-015.2.
- **AC-039.3** Dato un account eliminato, quando qualcuno riapre una vecchia sessione, allora l'accesso è negato.
- **AC-039.4** (errore) Dato un'autenticazione di più di 10 minuti fa, quando chiedo l'eliminazione, allora ricevo "riautenticazione richiesta".

### US-040 · Esportare i dati in self-service · FR-018, FR-019, SR-016, SR-039 · Priorità M per l'apertura al pubblico · Apertura
Come Amministratore voglio esportare tutti i dati della famiglia, e come account i miei dati, in JSON e CSV, così ho una copia portabile.

- **AC-040.1** Dato un Amministratore riautenticato, quando richiede l'esportazione della famiglia, allora scarica un archivio con un file JSON completo e file CSV per piatti, fonti, tag, gusti, persone, piano, presenze, ospiti e cronologia.
- **AC-040.2** Dato un account qualunque, quando richiede l'esportazione dei propri dati, allora ottiene i suoi dati di account, i suoi gusti, la sua settimana tipo, le sue eccezioni e le sue modifiche, senza i dati personali degli altri.
- **AC-040.3** Dato un piatto il cui nome inizia con `=`, quando esporto in CSV, allora la cella è neutralizzata.
- **AC-040.4** (autorizzazione) Dato un Pianificatore o un Membro, quando tenta l'esportazione della famiglia, allora riceve `403`.
- **AC-040.5** Dato un'esportazione generata, quando sono passate 24 ore, allora il file non è più scaricabile né presente sul server.

### US-041 · Consultare il piano senza connessione · FR-054, SR-026, SR-046, NFR-010 · Priorità S · M2
Come persona della famiglia voglio vedere il piano anche al supermercato senza rete, così so cosa serve.

- **AC-041.1** Dato che ho aperto il piano online almeno una volta, quando perdo la connessione e riapro l'app installata, allora vedo l'ultimo piano caricato con "dati aggiornati al <data e ora>".
- **AC-041.2** Dato lo stato offline, quando tento di modificare qualcosa, allora i comandi di modifica sono disabilitati e spiegano il motivo.
- **AC-041.3** Dato che faccio logout, oppure che sullo stesso dispositivo entra un altro account, quando riapro l'app offline, allora non viene mostrato nessun dato della famiglia precedente.
- **AC-041.4** Dato che torno online, quando riapro l'app, allora i dati si aggiornano e l'indicazione offline sparisce.
- **AC-041.5** (SR-071, CHG-011) Dato dati offline caricati più di 7 giorni fa, quando apro l'app senza connessione, allora i dati non vengono mostrati e vengono cancellati, e un messaggio spiega che servono la connessione e un nuovo caricamento.

### US-042 · Recuperare l'Amministratore tramite il Gestore · FR-064, SR-066, SR-020 · Priorità M · M1
Come persona di una famiglia rimasta senza un Amministratore raggiungibile (per esempio per un account Google perso) voglio chiedere al Gestore di nominare Amministratore un account della famiglia, così la famiglia torna gestibile.

*Criteri riscritti con CHG-009 (recupero semplice, decisione dell'utente del 2026-10-18).*

- **AC-042.1** (riscritto con CHG-016) Dato una richiesta arrivata al Gestore dall'email dell'account di un membro, quando il Gestore esegue il comando e inserisce quell'email al prompt interattivo, che la trasforma in hash localmente, allora la famiglia viene ricavata dall'unica persona attiva dell'account, l'account ne diventa Amministratore e le sue sessioni sono invalidate. Tutta la famiglia vede nell'app l'avviso "<nome> è diventato Amministratore tramite il supporto". L'evento compare nel registro di sicurezza e nella cronologia.
- **AC-042.2** (errore) Dato un'email che non corrisponde a nessun account, oppure un account senza una persona attiva in una famiglia, quando il Gestore esegue il comando, allora il comando fallisce con un esito generico ("nessuna corrispondenza"), senza modifiche e senza mostrare dati.
- **AC-042.3** ~~RIMOSSO~~ (CHG-016): rifiutava il comando se la famiglia aveva ancora un Amministratore utilizzabile. Sostituito da AC-042.7.
- **AC-042.7** (CHG-016) Dato una famiglia che ha già un Amministratore, quando il Gestore esegue il comando per un altro membro, allora il comando riesce, quel membro diventa un Amministratore in più, e l'avviso compare a tutta la famiglia.
- **AC-042.8** (CHG-016) Dato il comando, quando lo si esegue passando un'email o un identificativo di famiglia come argomento sulla riga di comando, allora il comando rifiuta l'argomento e chiede l'email solo al prompt interattivo. Dato un comando riuscito, quando si cercano nella cronologia della shell e nei log, allora l'email in chiaro non compare.
- **AC-042.4** Dato il comando eseguito, quando se ne legge l'output, allora contiene solo l'esito, con eventuali identificativi, senza nomi, email di altri, elenco dei membri né contenuti.
- **AC-042.5** (autorizzazione) Dato un qualunque account dell'app, quando cerca di ottenere il ruolo Amministratore con un'operazione equivalente tramite il server, allora l'operazione non esiste.
- **AC-042.6** Dato l'avviso di AC-042.1, quando un membro della famiglia apre l'app nei 30 giorni successivi, allora vede l'avviso finché non lo chiude. L'avviso resta comunque nella cronologia.

### US-043 · Nominare o revocare un Amministratore · FR-066, FR-011, SR-039, SR-044 · Priorità M · M2
Come Amministratore voglio nominare un secondo Amministratore, così la famiglia non dipende da una sola persona.

- **AC-043.1** Dato un Amministratore autenticato negli ultimi 10 minuti, quando nomina Amministratore un Pianificatore, allora dalla richiesta successiva quell'account ha i permessi di Amministratore, e l'evento entra nel registro di sicurezza e nella cronologia.
- **AC-043.2** (errore) Dato un'autenticazione di più di 10 minuti fa, quando tenta la nomina o la revoca, allora riceve "riautenticazione richiesta" e nulla cambia.
- **AC-043.3** (errore) Dato un solo Amministratore, quando tenta di revocare il ruolo a se stesso, allora l'operazione è bloccata (FR-011).
- **AC-043.4** (autorizzazione) Dato un Pianificatore, quando tenta di nominare un Amministratore, allora riceve `403`.
- **AC-043.5** Dato due Amministratori, quando uno revoca il ruolo all'altro, allora l'altro diventa Pianificatore (ASM-062).
- **AC-043.6** (SR-068, CHG-008) Dato il telefono sbloccato di un Amministratore, quando un'altra persona completa la riautenticazione con un account Google diverso, allora la riautenticazione è rifiutata, l'operazione critica non avviene e si registra l'evento `reauth.mismatch`. Vale anche per un token senza `auth_time`, o con un `auth_time` precedente all'avvio del flusso. Il criterio si applica a tutte le operazioni di SR-039.

### US-044 · Ottenere un'esportazione durante la beta · FR-065, SR-016, SR-067 · Priorità M · M1
Come account voglio ricevere una copia dei miei dati, o di quelli della famiglia se sono Amministratore, anche prima che esista l'esportazione self-service, così esercito i miei diritti di accesso e portabilità.

- **AC-044.1** Dato la richiesta di un account arrivata al contatto privacy, quando il Gestore avvia l'esportazione con l'identificativo dell'account, allora nell'app di quell'account compare, entro un mese dalla richiesta, un file JSON e CSV con i suoi dati, scaricabile per 24 ore.
- **AC-044.2** Dato un'esportazione della famiglia richiesta da un Amministratore, quando il file è pronto, allora è scaricabile solo da quell'Amministratore.
- **AC-044.3** (autorizzazione) Dato un altro account della famiglia, quando tenta di scaricare quel file, allora riceve "non trovato".
- **AC-044.4** (autorizzazione) Dato un'esportazione della famiglia avviata per un account che non è Amministratore, quando il job parte, allora viene rifiutato.
- **AC-044.5** Dato il comando di esportazione, quando se ne legge l'output, allora contiene solo l'identificativo del job e il suo stato. Il Gestore non riceve il file.
- **AC-044.6** (SR-072, autorizzazione) Dato un'esportazione della famiglia pronta, quando il richiedente perde il ruolo di Amministratore, esce o viene rimosso, allora il file viene cancellato, e un tentativo di download riceve "non trovato".
- **AC-044.7** (SR-072) Dato un'esportazione della famiglia, quando la si apre, allora contiene i contenuti della famiglia e i nomi visualizzati, ma non email, ultima visita, ordinamento preferito, sessioni o IP degli altri account.
- **AC-044.8** (SR-072, M2) Dato un'autenticazione di più di 10 minuti fa, quando l'Amministratore scarica un'esportazione della famiglia, allora riceve "riautenticazione richiesta".

### US-045 · Modificare il mio nome visualizzato · FR-067, SR-054 · Priorità M · M1
Come account voglio cambiare il nome con cui la famiglia mi vede, così è corretto e rispecchia come mi chiamano in casa.

- **AC-045.1** Dato il mio nome "Marco Rossi", quando lo cambio in "Papà", allora tutti gli account della famiglia vedono "Papà" nel piano e nella cronologia, anche per le modifiche passate.
- **AC-045.2** Dato un nuovo login Google, quando entro, allora il nome resta "Papà".
- **AC-045.3** (errore) Dato un nome vuoto o di oltre 60 caratteri, quando salvo, allora il salvataggio è rifiutato.
- **AC-045.4** (autorizzazione) Dato un Amministratore, quando tenta di cambiare il nome di un altro account, allora riceve `403` (ASM-054).

### US-046 · Prendere visione dell'informativa · FR-068, SR-030, SR-056 · Priorità M · M1
Come persona che entra nell'app voglio leggere in parole semplici come vengono usati i miei dati, così so cosa accetto.

- **AC-046.1** Dato l'accettazione di un invito o la creazione di una famiglia, quando arrivo al passo dell'informativa, allora vedo il testo breve e la sintesi delle condizioni, e posso proseguire solo confermando la presa visione.
- **AC-046.2** Dato la presa visione, quando viene salvata, allora si registrano versione e data.
- **AC-046.3** Dato una nuova versione sostanziale dell'informativa, quando un account fa il login successivo, allora deve prenderne visione prima di accedere ai dati.
- **AC-046.4** (errore) Dato che chiudo l'informativa senza confermare, quando torno all'app, allora non accedo ai dati della famiglia.

### US-047 · Gestire le mie sessioni · FR-069, SR-038 · Priorità S · M1
Come account voglio vedere dove sono collegato e uscire dagli altri dispositivi, così, se perdo il telefono, nessuno vede i dati della mia famiglia.

- **AC-047.1** Dato tre sessioni attive, quando apro l'elenco, allora vedo tipo di dispositivo e browser e la data approssimativa dell'ultimo uso, senza l'IP completo.
- **AC-047.2** Dato che scelgo "esci da tutti gli altri dispositivi", quando confermo, allora le altre sessioni sono rifiutate dalla richiesta successiva e quella corrente resta valida.
- **AC-047.3** (autorizzazione) Dato un account, quando tenta di revocare la sessione di un altro account, allora riceve "non trovato".
- **AC-047.4** (SR-070, CHG-010) Dato un account con 20 sessioni attive, quando fa un nuovo login, allora la sessione usata meno di recente viene revocata e la nuova è valida. *Questo criterio vale da M0, anche se l'elenco delle sessioni (Should) arriva in M1.*

### US-048 · Mantenere vero il passato · FR-063, FR-061 · Priorità M · M1
Come Pianificatore voglio che i pasti passati mantengano le presenze che avevano, così lo storico dei coperti non cambia quando cambiano le abitudini o le persone.

- **AC-048.1** Dato una persona entrata nella famiglia il 10 del mese, quando apro i pasti dal 9 in giù, allora quella persona non compare. Dal 10 in poi compare secondo la sua settimana tipo (ASM-058).
- **AC-048.2** Dato una modifica alla settimana tipo fatta oggi, quando apro i pasti di ieri, allora le presenze sono quelle che erano prima della modifica.
- **AC-048.3** Dato una persona uscita dalla famiglia, quando apro i pasti passati a cui era presente, allora risulta "ex membro" presente e i coperti di quei pasti non cambiano.
- **AC-048.4** Dato una correzione esplicita su un pasto passato (FR-041), quando la salvo, allora la presenza cambia solo per quel pasto, e la correzione entra nella cronologia.

### US-049 · Registrare gli eventi di modifica da subito · FR-061, SR-047 · Priorità M · M0
Come Gestore voglio che ogni modifica a piano, presenze e stato dei piatti sia registrata da M0, così posso misurare i KPI e avere lo storico completo quando arriverà la cronologia visibile.

- **AC-049.1** Dato un'assegnazione di un piatto a un pasto, quando viene salvata, allora esiste un evento con data e ora UTC, identificativo dell'autore, ruolo dell'autore in quel momento, pasto, e valori prima e dopo.
- **AC-049.2** Dato un evento, quando si ispeziona il database, allora non contiene il nome né l'email dell'autore, ma solo il suo identificativo.
- **AC-049.3** (autorizzazione) Dato un qualunque account, quando tenta di creare, modificare o cancellare un evento direttamente tramite il server, allora l'operazione non esiste.
- **AC-049.4** Dato un'operazione che fallisce, per esempio per un conflitto o un permesso negato, quando termina, allora non resta nessun evento di modifica per quell'operazione.
- **AC-049.5** (SR-070, CHG-010) Dato un account che ha già fatto 60 scritture nell'ultimo minuto, sommando tutte le sue sessioni, quando ne fa un'altra, allora riceve `429` con `Retry-After`. Dato una famiglia con 5.000 scritture tracciate nella giornata, quando arriva un'altra scrittura, allora riceve `429` e il Gestore riceve un allarme.

### US-050 · Dare una priorità ai piatti · FR-070, SR-010 · Priorità S · M2 · CHG-001
Come Pianificatore voglio dare a ogni piatto un punteggio da 1 a 10, così vedo per primi i piatti che la famiglia vuole proporre più spesso.

- **AC-050.1** Dato un piatto nuovo, quando lo salvo senza indicare la priorità, allora il punteggio è 5.
- **AC-050.2** Dato un piatto, quando imposto la priorità a 9, allora il punteggio è 9 per tutta la famiglia ed è visibile nella scheda, nel selettore e nell'archivio.
- **AC-050.3** (errore) Dato un valore 0, 11, decimale o non numerico, quando salvo, allora il salvataggio è rifiutato con il messaggio del limite 1-10.
- **AC-050.4** (autorizzazione) Dato un Membro, anche sui piatti "da provare" che ha creato, quando tenta di impostare la priorità, anche chiamando direttamente il server, allora riceve `403`, e un piatto che crea ha priorità 5 (ASM-067).
- **AC-050.5** Dato un cambio di priorità, quando viene salvato, allora si applica la concorrenza ottimistica della scheda del piatto (FR-044 d).

### US-051 · Scegliere come ordinare i piatti · FR-071, FR-040, FR-031 · Priorità S · M2 · CHG-002
Come persona della famiglia voglio scegliere come sono ordinati i piatti nel selettore e nell'archivio, e ritrovare la stessa scelta su tutti i miei dispositivi.

- **AC-051.1** Dato l'ordinamento "priorità", quando apro il selettore, allora i piatti sono ordinati dal punteggio più alto al più basso, e a parità di punteggio per nome.
- **AC-051.2** Dato l'ordinamento "non cucinato da più tempo", quando apro il selettore o l'archivio, allora vengono prima i mai cucinati, poi gli altri dal meno recente, e a parità per nome.
- **AC-051.3** Dato che scelgo "priorità" sul telefono, quando apro l'app dal computer con lo stesso account, allora l'ordinamento è "priorità".
- **AC-051.4** Dato un account che non ha mai scelto un ordinamento, quando apre il selettore, allora l'ordinamento è "nome".
- **AC-051.5** (autorizzazione) Dato un account, quando tenta di modificare l'ordinamento preferito di un altro account, allora l'operazione non esiste ("non trovato").
- **AC-051.6** (errore) Dato un valore di ordinamento diverso da nome, priorità o non cucinato da più tempo, quando arriva al server, allora è rifiutato con `422`.

### US-052 · Aggiungere più pasti extra con un nome · FR-072, FR-036, FR-050 · Priorità S (interfaccia) · M2 · CHG-003
Come Pianificatore voglio aggiungere a un giorno sia "Aperitivo" sia "Dopocena", così il piano rappresenta davvero quello che mangiamo.

- **AC-052.1** Dato sabato senza pasti extra, quando aggiungo un "Altro pasto" e lo chiamo "Aperitivo", e poi un altro chiamato "Dopocena", allora sabato mostra due pasti distinti con i loro nomi, ognuno con contenuto, presenze e ospiti propri.
- **AC-052.2** Dato che aggiungo un "Altro pasto" senza scrivere un nome, quando confermo, allora il pasto si chiama "Altro pasto".
- **AC-052.3** Dato un "Altro pasto" chiamato "Aperitivo", quando lo rinomino in "Merenda lunga", allora il nuovo nome compare nel piano e nella cronologia, e il contenuto resta invariato.
- **AC-052.4** (errore) Dato un nome vuoto o di oltre 40 caratteri, oppure un sesto "Altro pasto" nello stesso giorno, quando salvo, allora l'operazione è rifiutata con l'indicazione del limite (ASM-068).
- **AC-052.5** Dato un giorno con due "Altro pasto", quando copio quel giorno su un altro (FR-043), allora la destinazione riceve due "Altro pasto" con gli stessi nomi e contenuti.
- **AC-052.6** (autorizzazione) Dato un Membro, quando tenta di aggiungere, rinominare o togliere un "Altro pasto", allora riceve `403`.
- **AC-052.7** (M0-M1, modello dati) Dato i dati salvati in M0 o M1 con un "Altro pasto" per giorno e nome predefinito, quando si rilascia M2, allora quei pasti compaiono come "Altro pasto" senza nessuna migrazione dei dati. Da verificare con un test di schema nella prima slice: lo schema accetta due "Altro pasto" nello stesso giorno.
- **AC-052.8** (riscritto con CHG-017) Dato un giorno con 5 "Altro pasto" attivi, quando ne tolgo uno e poi ne aggiungo un altro, allora l'aggiunta riesce, perché i pasti attivi sono di nuovo 5. Dato invece 5 "Altro pasto" attivi, quando tento di aggiungerne un sesto, allora l'aggiunta è rifiutata con un messaggio che spiega il limite. Dato un "Altro pasto" tolto, quando viene aggiunto di nuovo, allora si riusa quello esistente e la sua cronologia resta collegata. Il pasto riparte però con **tutte le persone presenti**: le eccezioni di presenza precedenti sono cancellate (FR-050).

## Tracciabilità FR → US → AC

| FR | US | AC | Milestone |
|---|---|---|---|
| FR-001 | US-001 | AC-001.1, .5-.9 | M0 |
| FR-002 | US-029 | AC-029.1-.4, .6-.8 | Backlog dopo M2 (CHG-020) |
| FR-003 | US-029 | AC-029.5 | Backlog dopo M2 (CHG-020) |
| FR-004 | US-001 | AC-001.2-.4 | M0 |
| FR-005 | US-036 | AC-036.1, .4, .5, .8 | M2 |
| FR-006 | US-036 | AC-036.2, .3, .6, .7 | M2 |
| FR-007 | US-002 | AC-002.1-.4 | M0 |
| FR-008 | US-012, US-037 | AC-012.1-.7, AC-037.2, .4, .7 | M1 / M2 |
| FR-009 | US-013, US-037 | AC-013.1-.9, AC-037.3, .8 | M1 / M2 |
| FR-010 | US-014 | AC-014.1-.5 | M1 |
| FR-011 | US-015, US-039, US-043 | AC-015.1-.3, AC-039.2, AC-043.3 | M1 |
| FR-012 | US-016, US-048 | AC-016.1-.5, AC-048.3 | M1 |
| FR-013 | US-017 | AC-017.1-.6 | M1 |
| FR-014 | US-037 | AC-037.1, .5-.8 | M2 |
| FR-015 | US-003 | AC-003.1-.5 | M0 |
| FR-016 | US-038 | AC-038.1-.7 | M2 |
| FR-017 | US-039 | AC-039.1-.4 | M2 |
| FR-018 | US-040 | AC-040.1, .3-.5 | Apertura |
| FR-019 | US-040 | AC-040.2, .5 | Apertura |
| FR-020 | US-004 | AC-004.1, .3, .5-.7 | M0 |
| FR-021 | US-004, US-033 | AC-004.1, AC-033.4 | M0 |
| FR-022 | US-033 | AC-033.1-.5 | M2 |
| FR-023 | US-032, US-019 | AC-032.1, .4-.6, AC-019.5 | M2 |
| FR-024 | US-004 | AC-004.2, .4, .5 | M0 |
| FR-025 | US-005 | AC-005.1-.4 | M0 |
| FR-026 | US-030 | AC-030.1-.4 | M2 |
| FR-027 | US-018 | AC-018.1-.5 | M1 |
| FR-028 | US-019 | AC-019.1-.4 | M1 |
| FR-029 | US-007 | AC-007.1-.6 | M0 |
| FR-030 | US-006 | AC-006.1-.5 | M0 |
| FR-031 | US-032 | AC-032.2, .3 | M2 |
| FR-032 | US-034 | AC-034.1-.3 | M2 |
| FR-033 | US-035 | AC-035.1-.7 | M2 |
| FR-034 | US-010, US-011 | AC-010.1-.3, .5, AC-011.1-.2 | M0 |
| FR-035 | US-008 | AC-008.1, .5, .7 | M0 |
| FR-036 | US-003, US-008 | AC-003.1-.3, AC-008.3-.4 | M0 |
| FR-037 | US-008 | AC-008.2, .6, .8, .9 | M0 |
| FR-038 | US-009 | AC-009.1, .2, .5, .6 | M0 |
| FR-039 | US-009 | AC-009.3, .4, .6 | M0 |
| FR-040 | US-010 | AC-010.1, .2, .4 | M0 |
| FR-041 | US-011, US-021, US-022 | AC-011.1-.6, AC-021.6, AC-022.5 | M0 / M1 |
| FR-042 | US-025 | AC-025.1-.5 | M1 |
| FR-043 | US-026 | AC-026.1-.5 | M1 |
| FR-044 | US-027 | AC-027.1-.7 | M1 |
| FR-045 | US-028 | AC-028.1, .3-.6 | M1 |
| FR-046 | US-028 | AC-028.2 | M1 |
| FR-047 | US-024 | AC-024.1-.4 | M1 |
| FR-048 | US-031 | AC-031.1-.5, AC-022.4 | M2 |
| FR-049 | US-020 | AC-020.1-.3, .5, .6 | M1 |
| FR-050 | US-020 | AC-020.4 | M1 |
| FR-051 | US-021 | AC-021.1-.3, .5-.8 | M1 |
| FR-052 | US-022 | AC-022.1-.3, .5 | M1 |
| FR-053 | US-023 | AC-023.1-.4 | M1 |
| FR-054 | US-041 | AC-041.1-.5 | M2 |
| FR-055 | (NFR-011, verificato in CI) | n/a | M0 |
| FR-056 … FR-059 | Won't: nessuna storia | n/a | dopo l'MVP |
| FR-060 | US-003, US-008, US-010 | AC-003.6, AC-008.1, AC-010.3 | M0 |
| FR-061 | US-049, US-005, US-011 | AC-049.1-.4, AC-005.1, AC-011.3 | M0 |
| FR-062 | US-024 | AC-024.5 | M1 |
| FR-063 | US-048, US-020, US-017 | AC-048.1-.4, AC-020.7, AC-017.6, AC-021.8 | M1 |
| FR-064 | US-042 | AC-042.1, .2, .4-.8 (AC-042.3 rimosso) | M1 |
| FR-065 | US-044 | AC-044.1-.8 | M1 (AC-044.8 da M2) |
| FR-066 | US-043 | AC-043.1-.5 | M2 |
| FR-067 | US-045 | AC-045.1-.4 | M1 |
| FR-068 | US-046, US-013, US-036 | AC-046.1-.4, AC-013.1, .6, AC-036.2 | M1 |
| FR-069 | US-047 | AC-047.1-.3 | M1 |
| FR-070 | US-050 | AC-050.1-.5 | M2 |
| FR-071 | US-051, US-010 | AC-051.1-.6, AC-010.6 | M2 (M0: solo nome) |
| FR-072 | US-052, US-020 | AC-052.1-.8, AC-020.8 | M0 (modello), M2 (interfaccia) |
| FR-062 (b), FR-046 | US-024, US-028 | AC-024.6, .7, AC-028.7 | M1 |
| FR-029 (CHG-005) | US-007 | AC-007.7 | M0 |
| NFR-017 | (verifica operativa nella prima slice e allarme) | n/a | M0 |

**SR del threat model con criteri dedicati:** SR-068 → AC-043.6. SR-070 → AC-047.4, AC-049.5. SR-071 → AC-041.5. SR-072 → AC-044.6-.8. SR-073 → AC-013.10. SR-066 → AC-042.1, .2, .4-.8. SR-074, SR-075 e SR-076 si verificano con le checklist e i controlli di pipeline del threat model (§10, §11) e di `docs/09-release.md`.

Le SR trasversali senza una storia dedicata (per esempio SR-008, SR-009, SR-015, SR-019, SR-021, SR-023, SR-027, SR-028, SR-029, SR-031, SR-040, SR-042, SR-048, SR-051 … SR-053, SR-057 … SR-062, SR-065) si verificano con i test e le checklist indicati nel loro dettaglio, con `docs/08-test-strategy.md` e con il threat model.

## Ipotesi

Le ipotesi ASM-001 … ASM-025 sono nella visione. "Confermata" significa approvata dall'utente il 2026-10-18, durante l'elicitazione o al gate G2. Dopo G2 tutte le ipotesi di questa tabella sono confermate, salvo quelle rimosse o superate.

| ID | Ipotesi | Impatto se falsa | Stato |
|---|---|---|---|
| ASM-026 | "Piatto principale" (KPI-4) è un'assegnazione con portata primo, secondo o piatto unico nel pasto. Conta la portata scelta nel pasto. | Cambia la misura di KPI-4. | Confermata |
| ASM-027 | Distribuzione nelle milestone: <br>- **M0:** tempo di preparazione, fonti multiple, voci libere, pasti speciali, correzione dei pasti passati, archiviazione, eventi di modifica; <br>- **M1:** spostare e copiare, conflitti, cronologia, indicatore delle modifiche, invariante sugli Amministratori, recupero, esportazione tramite Gestore; <br>- **M2:** tag, portate personalizzate (S), filtri e ordinamento avanzati, avviso nomi simili (S), import CSV (C), eliminazione dell'account, PWA offline (S), più Amministratori. <br>L'esportazione self-service passa all'apertura al pubblico. | Cambia solo l'ordine dei rilasci. | Confermata ("Solo priorità, M0 com'è") |
| ASM-028 | Il ruolo di chi viene invitato lo sceglie l'Amministratore alla creazione dell'invito, tra Membro e Pianificatore (SD-1). Si può cambiare dopo l'ingresso. | Serve un passaggio di assegnazione del ruolo dopo l'ingresso. | Confermata |
| ASM-029 | Un Membro può modificare ed eliminare solo i piatti che ha creato lui, finché sono "da provare" e mai pianificati. | Cambia la matrice e SR-010. | Confermata (G2, 2026-10-18) |
| ASM-030 | Tutti gli account della famiglia vedono i gusti di tutte le persone. | Visibilità ristretta. | Confermata |
| ASM-031 | ~~RIMOSSA~~ (dec. 2026-10-18, OBJ-01). Diceva che un Membro non modifica le proprie presenze passate. Ora i pasti passati sono sempre modificabili nei limiti del ruolo (FR-041, FR-051). | n/a | Rimossa |
| ASM-032 | La settimana tipo non contiene "Altro pasto": a **ogni** "Altro pasto" (CHG-003) tutti sono presenti per default. | Serve una riga "Altro pasto" nella settimana tipo. | Confermata (elic. 2026-10-18) |
| ASM-033 | Quando una persona esce o viene rimossa, si cancellano i suoi gusti, la sua settimana tipo e le sue eccezioni future. Le presenze passate restano, pseudonimizzate come "ex membro". I piatti che ha creato restano alla famiglia. | Cambia il diritto alla cancellazione o l'integrità dello storico. | Confermata |
| ASM-034 | Limiti: <br>- per famiglia: ≤ 2.000 piatti, ≤ 20 persone, ≤ 50 portate personalizzate, ≤ 200 tag; <br>- per piatto: nome 1-120 caratteri, note ≤ 2.000, ≤ 10 fonti con riferimento ≤ 500 e nota ≤ 500, ≤ 20 tag di 1-30 caratteri; <br>- per pasto: ≤ 10 voci (piatti più voci libere), voce libera 1-200 caratteri, ospiti 0-50 con nota ≤ 200; <br>- nome visualizzato 1-60 caratteri; <br>- intervallo di consultazione del piano ≤ 62 giorni per vista. | Cambiano la validazione e il dimensionamento. | Confermata (G2, 2026-10-18) |
| ASM-035 | Picco di 25 utenti concorrenti, il 10% dei 250 account. | Ridimensionare NFR-002. | Confermata (G2, 2026-10-18) |
| ASM-036 | RTO ≤ 24 ore e prova di ripristino ogni 3 mesi. | Cambiano il runbook e i costi. | Confermata (G2, 2026-10-18) |
| ASM-037 | Il registro di sicurezza si conserva 12 mesi, con l'IP completo per 90 giorni (SD-7). | Cambiano SR-019 e lo spazio richiesto. | Confermata (IP: SD-7; 12 mesi: G2, 2026-10-18) |
| ASM-038 | Un codice di creazione scade dopo 30 giorni se non viene usato. | Cambia il rischio di codici dormienti. | Confermata (G2, 2026-10-18) |
| ASM-039 | Sessione con scadenza mobile di 30 giorni e durata massima assoluta di 90 giorni. | Una sessione rubata resterebbe valida a lungo. | Confermata da SR-037 |
| ASM-040 | Formato del CSV: <br>- UTF-8 con riga di intestazione, separatore `;` oppure `,` riconosciuto automaticamente; <br>- colonne `nome` (obbligatoria), `portate` (obbligatoria, più valori separati da `\|`), `stato` (`da provare` o `collaudato`, default `da provare`), `tempo` (`<30`, `30-60`, `>60`, opzionale), `tag` (separati da `\|`, creati se non esistono), `note`, `fonte_tipo`, `fonte_riferimento`, `fonte_nota` (una fonte per riga), `priorita` (1-10, opzionale, default 5, aggiunta con CHG-001); <br>- duplicato = nome uguale a quello di un piatto esistente, ignorando maiuscole, minuscole e spazi agli estremi; <br>- i duplicati si saltano per default; <br>- importazione parziale: solo le righe valide, dopo l'anteprima. | Cambia l'implementazione dell'import (C). | Confermata (G2, 2026-10-18) |
| ASM-041 | La copia di un giorno o di una settimana copia piatti, voci libere, stato speciale e pasti non di default, compresi tutti gli "Altro pasto" con i loro nomi (CHG-003), ma non presenze né ospiti. Se la destinazione non è vuota si chiede "sostituisci, aggiungi o annulla". I piatti archiviati si saltano. | Cambia FR-043. | Confermata (G2, 2026-10-18) |
| ASM-042 | Salvare in archivio una voce libera crea un piatto, "da provare" per default, e lo collega al pasto. Se il pasto è passato e non speciale, il piatto risulta cucinato in quella data. | Cambiano "ultima volta cucinato" e KPI-5. | Confermata (G2, 2026-10-18) |
| ASM-043 | La cache offline contiene la vista del piano caricata più di recente, con i nomi dei piatti e le loro fonti, ma non l'archivio completo. Il contenuto resta questo anche dopo CHG-011, compresi presenti, assenti e note degli ospiti. Si aggiunge solo la scadenza di 7 giorni (SR-071). | Cambiano lo spazio e il perimetro di SR-026. | Confermata (G2), integrata con CHG-011 |
| ASM-044 | La cronologia modifiche è visibile a tutti gli account della famiglia. | Visibilità ristretta. | Confermata |
| ASM-045 | L'accesso diretto del Gestore al database avviene solo per incidenti o manutenzione e viene annotato nel registro di sicurezza. Per la console il vincolo è anche tecnico (SR-040), per l'accesso diretto all'infrastruttura resta procedurale. | Servirebbe la cifratura applicativa dei campi. | Confermata (G2, 2026-10-18) |
| ASM-046 | Le esportazioni si generano su richiesta e restano scaricabili per 24 ore. | Cambia SR-016. | Confermata (G2, 2026-10-18) |
| ASM-047 | La ricerca per nome è parziale, ignora maiuscole, minuscole e accenti, e non è fuzzy. Le somiglianze di FR-032 usano un criterio più tollerante, definito dall'architetto. | Cambia l'implementazione della ricerca. | Confermata (G2, 2026-10-18) |
| ASM-048 | ~~SUPERATA~~ da SR-059 (valori definitivi dei limiti di frequenza). | n/a | Superata |
| ASM-049 | Una famiglia può avere zero pasti di default. In quel caso il piano è vuoto finché non si aggiungono pasti ai singoli giorni. | Serve almeno un pasto di default obbligatorio. | Confermata (G2, 2026-10-18) |
| ASM-050 | Nell'MVP un account che appartiene già a una famiglia non può accettare l'invito di un'altra né creare un'altra famiglia, perché l'interfaccia ne gestisce una sola (ASM-002). | Serve la scelta della famiglia attiva già nell'MVP. | Confermata (G2, 2026-10-18) |
| ASM-051 | ~~SUPERATA~~ dalla definizione di KPI-7 "Partecipazione" scelta dall'utente (vedi "Misurazione dei KPI"). | n/a | Superata |
| ASM-052 | Per un pasto "saltato", "fuori casa" o "ristorante" si mostrano presenti e ospiti, ma non i coperti come quantità da cucinare. | Cambia FR-053. | Confermata (G2, 2026-10-18) |
| ASM-053 | Spostando un pasto si spostano i contenuti (piatti, voci libere, stato speciale), mentre presenze e ospiti restano legati al giorno e al tipo di pasto. | Cambia FR-042. | Confermata (G2, 2026-10-18) |
| ASM-054 | Il nome visualizzato di un account lo modifica solo l'account stesso (rettifica). Amministratore e Pianificatore modificano solo i nomi dei profili senza account. | Un Amministratore potrebbe rinominare gli altri account, con un rischio di confusione e di abuso. | Confermata (G2, 2026-10-18) |
| ASM-055 | Un Membro può assegnare tag **esistenti** ai piatti che può modificare (ASM-029), ma non può creare, rinominare o eliminare tag. | Cambia la matrice: o nessun tag per i Membri, o la creazione libera di tag. | Confermata (G2, 2026-10-18) |
| ASM-056 | Le correzioni di presenze e ospiti su pasti passati non hanno limiti di tempo. | Servirebbe una finestra di correzione. | Confermata (dec. 2026-10-18, OBJ-01) |
| ASM-057 | ~~SUPERATA~~ (CHG-009, decisione dell'utente del 2026-10-18). Testo precedente: una richiesta di recupero dell'Amministratore è "verificata" quando (a) arriva al contatto privacy dall'email di un account che appartiene alla famiglia, (b) è confermata su un secondo canale, (c) un Amministratore ancora raggiungibile viene informato e non si oppone entro 72 ore. Il threat model ha mostrato che (b) e (c) non sono verificabili dal Gestore senza vedere dati delle famiglie (THR-050). L'utente ha scelto il recupero semplice di FR-064, SR-066 e ASM-071. | n/a | Superata |
| ASM-058 | Una persona conta in tutti i pasti del giorno in cui entra nella famiglia, compresi quelli già trascorsi in quella giornata, e in quelli successivi. Per un profilo senza account vale il giorno di creazione. | Cambia il calcolo dei coperti del giorno di ingresso. | Confermata (G2, 2026-10-18) |
| ASM-059 | Cambiare il fuso orario della famiglia non ricalcola i giorni dei pasti già registrati, né gli eventi passati. | Servirebbe una migrazione dei dati al cambio di fuso. | Confermata (G2, 2026-10-18) |
| ASM-060 | La visita settimanale (FR-062a) è un solo dato sì/no per account e per settimana, conservato come i dati del piano e incluso nell'esportazione. **Modificata da CHG-004:** in più esiste, per ogni account, un solo valore di ultima visita (data e ora) sul server (FR-062b). Si conserva finché esiste l'account, è inclusa nell'esportazione dei dati dell'account e citata nell'informativa. KPI-7 resta calcolato sulle visite settimanali. | Cambia la minimizzazione e il calcolo di KPI-7. | Confermata (G2), modificata dall'utente con CHG-004 (2026-10-18) |
| ASM-063 | Lunghezze non fissate da ASM-034: nome della famiglia 1-60 caratteri, nome di una portata personalizzata 1-40 (proposta di `docs/05-data.md`). Pasti di default alla creazione di una famiglia: Pranzo e Cena, modificabili. | Cambiano validazione e valori iniziali. | Confermata (utente, 2026-10-18, CHG-005) |
| ASM-064 | L'account di bootstrap (Gestore, M0) non ha una dichiarazione di età né una presa visione quando viene creato. Da M1 gliele chiede la sessione al login successivo, con lo stesso meccanismo di SR-056. | L'account del Gestore resterebbe senza dichiarazione. | Confermata (utente, 2026-10-18, CHG-005) |
| ASM-065 | Le presenze congelate (FR-063) si scrivono anche per i pasti speciali, perché ASM-052 mostra comunque presenti e ospiti. | Lo storico dei pasti speciali cambierebbe con la settimana tipo. | Confermata (utente, 2026-10-18, CHG-005) |
| ASM-066 | Collegamento di un profilo (M2): alla conferma, la persona del profilo riceve l'account e il ruolo. La persona temporanea creata all'accettazione viene chiusa come fusa nel profilo, e le sue presenze congelate tra accettazione e conferma si cancellano per eliminare il doppio conteggio. Il dettaglio va definito nella slice di M2 con il tech-lead. | Doppio conteggio dei coperti o perdita dello storico. | Confermata come approccio (utente, 2026-10-18, CHG-005) |
| ASM-067 | Il punteggio priorità (FR-070) è una decisione di pianificazione: lo modificano solo Pianificatori e Amministratori, anche sui piatti "da provare" creati da un Membro, che partono da 5. Coerente con FR-025 (anche lo stato lo cambiano solo loro). | Un Membro potrebbe dare priorità alle proprie idee. Cambierebbe la matrice. | Confermata (G3, 2026-10-19) |
| ASM-068 | Limiti di "Altro pasto" (FR-072). Unisce la proposta del product-analyst e quella del data-architect, che in `docs/05-data.md` era ASM-067: <br>- al massimo 5 "Altro pasto" **attivi** per giorno (CHG-017). Un pasto tolto non conta più; <br>- nome di 1-40 caratteri, senza obbligo di nomi diversi; <br>- un pasto tolto e poi aggiunto di nuovo **riusa** quello esistente, con il suo storico (CHG-017, decisione dell'utente del 2026-10-19). Sostituisce la proposta di non riusare le posizioni; <br>- il nome è contenuto dell'utente e non si traduce (ASM-025). Il nome predefinito "Altro pasto" viene dalla lingua dell'interfaccia al momento della creazione. <br>Lunghezza: la UX usava 1-60. Si adotta 1-40 del data-architect, perché nessun requisito chiede di più e il nome compare in righe compatte su schermi da 360 px (NFR-009). | Cambiano validazione, quote (SR-060) e messaggi della UX. | Confermata (G3, 2026-10-19), con la modifica di CHG-017 |
| ASM-069 | Punteggio priorità (FR-070), proposta del data-architect (in `docs/05-data.md` era ASM-068): intero 1-10, default 5. Fa parte dell'unità di concorrenza "scheda del piatto" (FR-044 d). Nell'ordinamento per priorità (FR-071) va dal più alto al più basso, a parità per nome. | Cambiano concorrenza e ordinamento. | Confermata (G3, 2026-10-19) |
| ASM-070 | Ultima visita (FR-062b), proposta del data-architect (in `docs/05-data.md` era ASM-069): si aggiorna quando si apre il piano, al massimo una volta al minuto per account. L'API restituisce il valore **precedente**, che il client usa per l'indicatore di FR-046. | Con aggiornamenti più frequenti crescono le scritture. Senza il valore precedente l'indicatore sparirebbe subito. | Confermata (G3, 2026-10-19) |
| ASM-071 | ~~SUPERATA~~ (CHG-016, decisione dell'utente del 2026-10-19). Definiva un "Amministratore utilizzabile" (accesso negli ultimi 14 giorni) come condizione per il recupero. L'utente ha eliminato la condizione: il Gestore aggiunge l'Amministratore su richiesta (FR-064). | n/a | Superata |
| ASM-061 | Durante il periodo di ripensamento la famiglia è in sola lettura, salvo le azioni elencate nella matrice dedicata. | Cambia FR-016. | Confermata (G2, 2026-10-18) |
| ASM-062 | Revocare il ruolo a un Amministratore lo fa diventare Pianificatore. L'Amministratore può poi cambiarlo in Membro con FR-010. | Cambia FR-066. | Confermata (G2, 2026-10-18) |

## Domande aperte

Nessuna domanda è bloccante per il gate G2. Q-017 resta una precondizione di M1.

| ID | Domanda | Bloccante? | Impatto | Stato / risposta |
|---|---|---|---|---|
| Q-001 | Orizzonte dell'apertura al pubblico. | No | Dimensionamento oltre l'anno uno. | Parzialmente chiusa: l'anno uno arriva fino a circa 50 famiglie e 250 account (NFR-004). L'orizzonte dell'apertura al pubblico resta aperto. |
| Q-009 | Dettagli delle presenze. | No | n/a | **Chiusa** (2026-10-18). Vedi FR-049 … FR-053, FR-063. |
| Q-010 | Modifiche contemporanee. | No | n/a | **Chiusa** (2026-10-18). Vedi FR-044 con le unità di modifica e US-027. |
| Q-012 | Un account tra 14 e 18 anni può avere ruoli diversi da Membro? | No | n/a | **Chiusa** (2026-10-18): qualunque ruolo. Con un invito si arriva al massimo a Pianificatore, come per tutti (SD-1). |
| Q-014 | I contenuti degli utenti andranno mai tradotti? | No | Modello dei contenuti per la condivisione pubblica. | Aperta. Default: no (ASM-025). |
| Q-015 | Il campo note e la nota degli ospiti potrebbero contenere dati sanitari: basta l'avviso nell'interfaccia (SR-032)? | No | Classificazione dei dati e rischio art. 9. | Aperta. Default: solo l'avviso. Da rivedere nella valutazione dei rischi (SR-065). |
| Q-016 | Come si calcolano i KPI senza che il Gestore veda i dati delle famiglie tester? | No | Misurazione del successo. | Aperta. Default: solo sulla famiglia del Gestore, tramite la sua esportazione (FR-065), più statistiche aggregate (SR-055). |
| Q-017 | Informativa privacy breve e adatta ai minori. | **No per G2.** Precondizione di M1. | Conformità GDPR. | **Decisa** (2026-10-18): la scrive l'utente partendo da un modello, è mostrata all'accettazione dell'invito e serve prima di M1 (SR-030, FR-068). Resta da fare: scriverla. |
| Q-018 | Cosa si fa se si scopre che un account ha meno di 14 anni? | No | Procedura e informativa. | Aperta. Default: l'Amministratore lo rimuove (FR-012) e, se serve, crea un profilo senza account al suo posto. |
| Q-019 | Storico delle presenze di chi esce. | No | n/a | **Chiusa** (2026-10-18): presenze passate conservate e pseudonimizzate (ASM-033, FR-012). |
| Q-020 | Il Pianificatore deve poter gestire i profili dei minori, o solo l'Amministratore? | No | Responsabilità sui dati dei minori. | Aperta. Default: entrambi, con la dichiarazione di responsabilità genitoriale di SR-064. |
| Q-021 | Serve nell'MVP la modifica dell'email di un account con email e password (con riautenticazione, verifica del nuovo indirizzo e avviso al vecchio)? | No | Recupero dell'accesso per chi cambia email. | **Rinviata** (G2, 2026-10-18): non nell'MVP, da decidere prima dell'apertura al pubblico. Nella beta chiusa gli account con password sono pochi, e un cambio di email si gestisce rimuovendo l'account e invitandolo di nuovo, al costo di perdere i gusti, oppure passando a Google. Va rivalutata prima dell'apertura al pubblico. *CHG-020: con FR-002 rinviato dopo M2, nell'MVP non esistono account con password; la domanda si riapre solo insieme a FR-002 (Q-031).* |
| Q-022 | Valori da confermare per ASM-029, ASM-034 … ASM-036, ASM-038, ASM-040 … ASM-043, ASM-045 … ASM-047, ASM-049, ASM-050, ASM-052 … ASM-055, ASM-057 … ASM-062. | No | Dettaglio di comportamento e di validazione. | **Chiusa** (G2, 2026-10-18): tutte confermate come scritte. ASM-037 è confermata con 12 mesi. ASM-057 era stata confermata con la verifica forte (email da un account della famiglia, conferma su un secondo canale, avviso di 72 ore agli Amministratori raggiungibili), ma è poi superata da CHG-009 (recupero semplice). |

### Domande registrate dopo G2

Durante la fase di design P3, ux-designer e data-architect hanno usato in parallelo gli stessi identificativi Q-023 … Q-026 in `docs/03-ux.md` e `docs/05-data.md`, per domande diverse. Questa tabella assegna identificativi unici e registra le risposte dell'utente. I due documenti vanno rinumerati secondo la colonna "Origine".

| ID | Origine | Domanda | Bloccante? | Stato / risposta |
|---|---|---|---|---|
| Q-023 | `03-ux.md` Q-023 | Il selettore dei piatti in M0 deve ordinare per "non cucinato da più tempo"? | No | **Chiusa** (utente, 2026-10-18): in M0 il selettore ordina **per nome**. L'ordinamento per priorità e l'ordinamento preferito arrivano in M2 (FR-040, FR-070, FR-071). FR-031 resta M2. |
| Q-024 | `03-ux.md` Q-024 | "Altro pasto" può avere un nome personalizzato? | No | **Chiusa** (utente, 2026-10-18): sì, più "Altro pasto" nello stesso giorno, ognuno con un nome libero ("Altro pasto" per default). Interfaccia in M2, modello dati da M0 (FR-072). Supera l'osservazione O-05 di `03-ux.md`. |
| Q-025 | `03-ux.md` Q-025 | Dove si conserva l'ultima visita per FR-046? | No | **Chiusa** (utente, 2026-10-18): **sul server**, un solo valore per account (FR-062b, SR-014, ASM-060). |
| Q-026 | `03-ux.md` Q-026 | Indicazione "già nel piano: gio 22" nel selettore? | No | **Chiusa** (utente, 2026-10-18): **non ora**. Si rivaluta in M1 se compaiono ripetizioni (KPI-4). Nessun FR aggiunto. |
| Q-027 | `05-data.md` Q-023 | Budget di spazio di archiviazione. | No | **Chiusa** (utente, 2026-10-18): `change_event` compatto da M0, misura delle dimensioni reali nella prima slice, allarme al 70% della quota, Supabase Pro solo se necessario (NFR-017). |
| Q-028 | `05-data.md` Q-024 | Significato di "piatto pianificato almeno una volta". | No | **Chiusa** (utente, 2026-10-18): dato letterale e permanente. Un piatto pianificato anche una sola volta si può solo archiviare (FR-029, AC-007.7). |
| Q-029 | `05-data.md` Q-025 | FR-046: dove si conserva l'ultima visita. | No | **Chiusa**: è la stessa domanda di Q-025, con la stessa risposta (sul server). |
| Q-030 | `05-data.md` Q-026 | AC-033.2: confronto con i nomi delle portate base. | No | **Chiusa** (utente, 2026-10-18): i nomi delle portate base sono **riservati, per ogni lingua**, nella configurazione del server. Una portata personalizzata non può usarli (AC-033.2). |
| Q-031 | CHG-020 (product-analyst) | Quando si riprende il login con email e password (FR-002, FR-003, US-029)? È una condizione di ingresso dell'apertura al pubblico, o serve prima, appena una famiglia tester ha una persona senza account Google? | No | **Chiusa** (utente, 2026-10-20, opzione a): email e password si riprendono non appena una famiglia tester ha una persona senza account Google, e comunque si decide prima dell'apertura al pubblico. Nel frattempo una persona senza account Google non accede all'app: può comparire nella famiglia solo come profilo senza account (FR-013), gestito da Amministratore o Pianificatore. *Impatto:* riprenderlo richiede di riattivare SR-002, SR-006, SR-034 … SR-036, SR-061, un provider email UE con DPA, SPF/DKIM/DMARC, l'aggiornamento dell'informativa e della DPIA. |

## Modifiche dopo G2

Decisioni esplicite dell'utente durante la fase di design P3 (2026-10-18 e 2026-10-19) e la discussione del gate G4 (CHG-020, 2026-10-19), dopo l'approvazione di G2. Ogni modifica è tracciata nei requisiti indicati.

| ID | Modifica | Requisiti toccati |
|---|---|---|
| CHG-001 | Nuovo punteggio priorità del piatto, da 1 a 10 e 5 per default, unico per famiglia, modificato da Pianificatori e Amministratori (S, M2). | FR-070, US-050, matrice, glossario, ASM-040, ASM-067, ASM-069 |
| CHG-002 | Ordinamento preferito per account, salvato sul server: nome, priorità, non cucinato da più tempo (S, M2). In M0 e M1 il selettore ordina solo per nome. FR-031 resta M2. | FR-071, FR-040, FR-031, US-051, AC-010.6, matrice, SR-014 |
| CHG-003 | Più "Altro pasto" nello stesso giorno, ognuno con un nome libero ("Altro pasto" per default). Interfaccia in M2, modello dati da M0. Per ognuno tutti presenti per default, presenza modificabile. | FR-072, FR-036, FR-039, FR-050, US-052, AC-020.8, ASM-032, ASM-041, ASM-068, matrice, glossario. Impatto su ADR-0009 (identità del pasto per data e tipo): da rivedere dall'architetto. |
| CHG-004 | L'ultima visita di FR-046 si conserva sul server, un valore per account, conservato finché esiste l'account. È un nuovo dato personale, citato nell'informativa. KPI-7 resta sulle visite settimanali. | FR-062, FR-046, ASM-060, ASM-070, SR-014, SR-019, SR-030, AC-024.6, .7, AC-028.7, glossario |
| CHG-005 | Domande di design registrate e chiuse (Q-023 … Q-030). Confermate ASM-063 … ASM-066 di `docs/05-data.md` e le decisioni di design DD-01 … DD-10 di `docs/03-ux.md`. | FR-029, AC-007.7, AC-033.2, ASM-063 … ASM-066, SR-043 (DD-07) |
| CHG-006 | Budget di archiviazione: eventi compatti da M0, misura nella prima slice, allarme al 70% della quota, piano a pagamento solo se necessario (Q-027). | NFR-017 |
| CHG-007 | AC-015.2 precisato per M1 e M2 (osservazione O-01 di `docs/03-ux.md`). | AC-015.2 |
| CHG-008 | SR-068 accettata: la riautenticazione è legata alla stessa identità e a un `auth_time` recente. | SR-068, SR-039, AC-043.6 |
| CHG-009 | **SR-069 respinta: recupero semplice dell'Amministratore.** Il membro scrive al Gestore dall'email del proprio account. Il Gestore esegue il comando con quell'email. La console verifica solo che l'email appartenga a un membro della famiglia. Il comando funziona solo se la famiglia non ha un Amministratore utilizzabile. Tutta la famiglia vede l'avviso "X è diventato Amministratore tramite il supporto", e tutto è registrato. Sostituisce la verifica forte con attesa di 72 ore. | FR-064, SR-066, SR-012, US-042 (AC-042.1-.6), ASM-057 (superata), ASM-071, matrice, rischi residui |
| CHG-010 | SR-070 accettata con questi valori: 60 scritture al minuto per account sommando le sessioni, 5.000 scritture tracciate al giorno per famiglia, al massimo 20 sessioni attive per account. | SR-070, SR-059, AC-047.4, AC-049.5 |
| CHG-011 | SR-071 ridotta a **sola scadenza**: la cache offline vale 7 giorni e il contenuto non cambia. Rischio residuo accettato. | SR-071, SR-026, FR-054, ASM-043, AC-041.5, rischi residui |
| CHG-012 | SR-072 accettata: esportazione della famiglia solo per chi è ancora Amministratore, file cancellati alla perdita del ruolo, riautenticazione per il download da M2, perimetro senza i dati di account degli altri membri. | SR-072, SR-016, SR-039, SR-067, FR-065, AC-044.6-.8, matrice |
| CHG-013 | SR-073 accettata: gli Amministratori vedono l'email verificata di chi è entrato con un invito. | SR-073, SR-014, SR-030, FR-010, AC-013.10, matrice |
| CHG-014 | SR-074 (igiene degli accessi del Gestore), SR-075 (hardening di Supabase) e SR-076 (catena di fornitura) accettate. Per SR-075: prima di M1 si verificano le network restrictions sul piano Free. Se sono disponibili, si usa un IP di uscita statico (circa 5 €/mese). Altrimenti il rischio residuo si registra nella DPIA. | SR-074, SR-075, SR-076 |
| CHG-015 | La sezione 8 del threat model è adottata come DPIA v1 per la beta da M1, rivista e firmata dall'utente, con revisione professionale prima dell'apertura al pubblico. Rischio residuo Medio del link di invito come segreto al portatore (THR-030) **accettato esplicitamente** dall'utente. | SR-065, SD-6, rischi residui |
| CHG-016 | **Recupero dell'Amministratore semplificato** (utente, 2026-10-19, dopo la revisione critica di G3): "non stiamo parlando di un sistema che gestisce cose critiche, facciamoci meno paranoie. Se non c'è più un amministratore, il gestore interviene su richiesta e aggiunge un altro amministratore". Cambia così:<br>- niente soglia di inattività, niente controllo "Amministratore utilizzabile", niente limite di 5 esecuzioni al giorno;<br>- il membro chiede dall'email del proprio account, e il Gestore lo aggiunge come Amministratore;<br>- restano l'avviso a tutta la famiglia e i registri;<br>- l'email arriva alla console solo come hash. | FR-064, SR-066, US-042 (AC-042.1, AC-042.3 rimosso, AC-042.7-.8), ASM-071 (superata), matrice, rischi residui |
| CHG-017 | "Altro pasto": un pasto tolto e poi aggiunto di nuovo si riusa, e il limite è di 5 pasti **attivi** per giorno. | ASM-068, AC-052.8 |
| CHG-018 | NFR-001: la misura Lighthouse si esegue ogni notte e prima di ogni rilascio, non a ogni pull request. La misura in sé non cambia. | NFR-001 |
| CHG-019 | Correzioni dalla revisione critica (secondo giro):<br>- il comando di recupero non riceve l'identificativo della famiglia. Il Gestore inserisce solo l'email del membro a un prompt interattivo, l'email viene trasformata in hash localmente e non compare mai sulla riga di comando, e la famiglia si ricava dall'unica persona attiva dell'account;<br>- un "Altro pasto" riusato riparte con tutti presenti. | FR-064, SR-066, AC-042.1, .2, .8, FR-050, AC-052.8 |
| CHG-020 | **Login con email e password rinviato dopo M2** (utente, 2026-10-19, discussione del gate G4): tutte le famiglie tester hanno un account Google, quindi registrazione, verifica, login e recupero con email e password escono da M2 e vanno nel backlog dopo l'MVP. Cambia così:<br>- FR-002, FR-003 e US-029 passano da M, M2 a W (rinviati), backlog dopo M2. Testi e criteri restano come riferimento;<br>- SR-002, SR-006, SR-034, SR-035 e SR-036, che valgono solo per email e password, seguono FR-002: backlog dopo M2, priorità M se FR-002 viene realizzato;<br>- SR-061 (abuso delle email): senza FR-002 e FR-003 l'app non invia email nell'MVP, quindi la SR si applica dal primo flusso email realizzato (FR-002 o avviso di inattività di SR-050 all'apertura al pubblico);<br>- SR-003, SR-004, SR-039, SR-059 e SR-068 restano attive per Google, inviti e codici. Le parti su registrazione, recupero password, reinvio della verifica e reinserimento della password seguono FR-002;<br>- le clausole condizionali "per email e password" o "cambio password" in SR-005, SR-014, SR-020 e SR-057 restano scritte ma non producono lavoro nell'MVP;<br>- ASM-024 della visione aggiornata: nell'MVP chi entra in una famiglia deve avere un account Google;<br>- nuova Q-031 (quando riprendere email e password). Q-021 segue FR-002. | FR-002, FR-003, US-029 (AC-029.1-.8), AC-013.1, SR-002, SR-003, SR-004, SR-006, SR-034, SR-035, SR-036, SR-039 (dettaglio), SR-059 (dettaglio), SR-061, SR-068, glossario, tracciabilità, Q-021, Q-031, ASM-024 (visione) |
| CHG-021 | **Limiti di frequenza in SL-03b** (utente, 2026-10-23, decisioni D1 e D2, opzioni raccomandate; ADR-0006 rev. 6):<br>- D1: finestra fissa allineata all'orologio del database, con `Retry-After` esatto; fino a 2 volte il limite a cavallo di due finestre, accettato per l'MVP; da rivedere se un limite protegge un segreto a bassa entropia (OTP);<br>- D2: rinviate le righe "Callback OIDC 30 per IP in 15 minuti" e "Login fallito 20 per IP in 15 minuti" di SR-059; da rivedere con SL-12 o con il ritorno di email e password. La verifica di SR-059 copre solo le righe attive. | SR-059 (dettaglio e verifica), SR-003 |
**Decisioni di design confermate (CHG-005).** Sono confermate le decisioni DD-01 … DD-10 di `docs/03-ux.md`: salvataggio immediato con "Annulla", selettore che resta aperto, nessuna funzione solo con trascinamento, comandi nascosti per ruolo e disabilitati per stato, schermate a tutto schermo su telefono, barra in basso a 3 voci, nome della famiglia solo dopo il login, solo tema chiaro, descrizioni della cronologia composte nel client, React Aria Components. Non cambiano i requisiti, salvo DD-07, ripresa in SR-043. Il dettaglio resta in `docs/03-ux.md`.

**Codici di errore della UX.** Le chiavi e i codici di errore elencati in `docs/03-ux.md` (per esempio `forbidden`, `not_found`, `reauth_required`, `rate_limited`, `family_pending_deletion`, `invite_invalid`, `validation.*`) realizzano requisiti già presenti e non richiedono modifiche. L'unica eccezione è `validation.duplicate_course`, il cui significato è precisato da AC-033.2 (Q-030). Con FR-070 e FR-072 servono anche codici per i limiti della priorità (1-10) e del numero di "Altro pasto" per giorno: li definisce l'ux-designer insieme al tech-lead.

## Aggiornamenti alla visione

Elementi di `docs/01-vision.md` che questo documento aveva superato. **Tutti applicati nella visione rev. 4 (2026-10-18).**

**Applicati nella visione rev. 5 (2026-10-19), insieme agli effetti di CHG-009, CHG-011, CHG-013 e CHG-015:**
- 18. punteggio priorità dei piatti e ordinamento preferito per account (M2), con il selettore di M0 ordinato per nome;
- 19. più "Altro pasto" con nome libero per giorno, che rende concreta la frase di ASM-025 sui "nomi dei pasti personalizzati";
- 20. ultima visita conservata sul server, da citare nei dati trattati e nell'informativa;
- 21. allarme di archiviazione al 70% (NFR-017) tra i vincoli di esercizio.

**Applicati nella visione rev. 7 (2026-10-19):**
- 22. CHG-020: login con email e password, con verifica e recupero, tolto da M2 e spostato tra gli sviluppi successivi; nell'MVP l'app non invia email; ASM-024 aggiornata.

1. **Gusti:** ASM-013 parla di gusto binario. Ora la scala è piace / neutro / non piace, più "sconosciuto" (FR-027). Anche "Dati trattati" in "Vincoli" va aggiornato.
2. **Adolescenti:** la tabella "Utenti", "Persone della famiglia" nello scope e "Minori" nei vincoli dicono "dai 14 anni con ruolo Membro". Ora vale qualunque ruolo (Q-012), e un invito assegna al massimo Pianificatore (SD-1).
3. **Piatto principale:** ASM-019 e "Definizioni comuni" vanno sostituite da ASM-026 (primo, secondo o piatto unico).
4. **KPI-7:** va sostituito con la definizione "Partecipazione" (vedi "Misurazione dei KPI").
5. **KPI-1 e KPI-2:** vanno aggiunti il fuso della famiglia, il fatto che voci libere e pasti speciali contano come copertura, e la sessione con pause di al massimo 30 minuti.
6. **Archivio:** nell'elenco "Dentro" vanno aggiunti più portate per piatto, portate personalizzate, tag, tempo di preparazione, fonti multiple, e la possibilità per un Membro di aggiungere idee "da provare".
7. **Piano:** vanno aggiunti voci libere, pasti speciali, spostare/scambiare/copiare, correzione dei pasti passati sempre possibile, cronologia visibile e passato congelato.
8. **Ospiti:** la visione parla di "numero di ospiti". Ora sono un numero più una nota libera (FR-052).
9. **Import CSV:** è una novità rispetto alla visione. Priorità Could, M2.
10. **Esportazione:** nella beta avviene su richiesta tramite il Gestore. Quella self-service passa all'apertura al pubblico.
11. **Offline:** consultazione PWA in sola lettura (Should, M2).
12. **Amministratori:** invariante e recupero tramite Gestore in M1, interfaccia per più Amministratori in M2. ASM-020 in M2 cita "più Amministratori" senza questa distinzione.
13. **Volumi:** Q-001 è parzialmente chiusa (50 famiglie e 250 account nell'anno uno).
14. **Gestore della piattaforma:** vanno aggiunti il comando di recupero dell'Amministratore e l'avvio delle esportazioni, che non leggono contenuti.
15. **Minori sotto i 14 anni:** va aggiunta la dichiarazione di responsabilità genitoriale alla creazione del profilo (SD-5).
16. **Conservazione:** va aggiunta la cancellazione delle famiglie e degli account inattivi da 24 mesi, entro l'apertura al pubblico (SD-4). Va aggiunta la DPIA prima dell'apertura al pubblico (SD-6).
17. **Ruolo Membro:** nella visione il Membro "consulta il piano e segna le proprie presenze". Va aggiunto che esprime i propri gusti, aggiunge idee "da provare", corregge le proprie presenze passate e gli ospiti dei pasti a cui era presente.
