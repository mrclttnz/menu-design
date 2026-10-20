# Visione di prodotto: Menu Design

> Documento di proprietà del product-analyst. Ultimo aggiornamento: 2026-10-19 (rev. 7).
>
> Fonti:
> - intervista con l'utente (idea originale, scope MVP confermato);
> - decisioni dell'utente sulle obiezioni della revisione critica e decisioni finali del gate G1;
> - requisiti approvati al gate G2 (`docs/02-requirements.md`).
>
> Le informazioni non fornite dall'utente sono registrate come ipotesi (ASM) o domande aperte (Q) in fondo al documento. I dettagli verificabili (FR, NFR, SR, US, AC) sono in `docs/02-requirements.md`. In caso di dubbio prevalgono i requisiti approvati.

## Storico delle revisioni

- **rev. 1**, 2026-10-17: prima stesura dall'intervista.
- **rev. 2**, 2026-10-17: decisioni dell'utente dopo la revisione critica (registrazione chiusa, link di invito, milestone M0-M2, minori dai 14 anni).
- **rev. 3**, 2026-10-17: decisioni finali del gate G1 (solo Google in M0, autodichiarazione dell'età, Gestore da console, predisposizione multilingua).
- **rev. 4**, 2026-10-18: **allineamento ai requisiti approvati G2.** Cambiano:
  - gusti a tre valori;
  - adolescenti con qualunque ruolo, ma inviti al massimo da Pianificatore;
  - piatto principale = primo, secondo o piatto unico;
  - KPI-7 = partecipazione;
  - definizione di "passato" e passato congelato;
  - import CSV come Could in M2;
  - esportazione nella beta tramite il Gestore;
  - recupero dell'Amministratore;
  - dichiarazione di responsabilità genitoriale;
  - conservazione dei dati inattivi;
  - nuova distribuzione delle milestone.
- **rev. 5**, 2026-10-19: **allineamento alle modifiche dopo G2 (CHG-001 … CHG-015 dei requisiti).** Cambiano:
  - punteggio priorità dei piatti e ordinamento preferito per account (M2), con il selettore di M0 ordinato per nome;
  - più "Altro pasto" con nome libero nello stesso giorno;
  - ultima visita conservata sul server;
  - allarme di archiviazione al 70%;
  - recupero semplice dell'Amministratore tramite il supporto;
  - email visibile agli Amministratori per chi entra con un invito;
  - cache offline valida 7 giorni;
  - DPIA v1 per la beta da M1;
  - rischio residuo del link di invito accettato.
- **rev. 6**, 2026-10-19: recupero dell'Amministratore ulteriormente semplificato (CHG-016 dei requisiti): il Gestore aggiunge l'Amministratore su richiesta, senza soglie né limiti, e riceve l'email solo come hash. Resta l'avviso a tutta la famiglia. CHG-017 (limite di 5 "Altro pasto" attivi) e CHG-018 (frequenza della misura Lighthouse) non toccano la visione.
- **rev. 7**, 2026-10-19: **login con email e password rinviato dopo M2** (CHG-020 dei requisiti, decisione dell'utente durante il gate G4): tutte le famiglie tester hanno un account Google. Nell'MVP l'unico metodo di accesso è Google e l'app non invia email. ASM-024 aggiornata.

## Problema

Chi pianifica i pasti di casa per la propria famiglia si trova sempre di fronte agli stessi problemi:

- **Poca varietà.** Si finisce a cucinare sempre gli stessi piatti, per mancanza di idee o perché non si ricorda cosa si è già provato.
- **Memoria dispersa.** Non si ricorda quali piatti hanno funzionato e sono piaciuti, e a chi. La lista dei piatti "da provare" esiste solo nella testa di chi pianifica.
- **Ricette introvabili.** Le ricette sono sparse tra libri, riviste, siti web, post e reel social, newsletter e altro. Si perde tempo a ritrovare dove si trovava quella ricetta.
- **Presenze incerte.** Non si sa chi sarà presente a ogni pasto, quindi per quante persone cucinare. Si perdono anche le occasioni per preparare un piatto che piace solo a una parte della famiglia (per esempio solo ai genitori) quando chi non lo gradisce è assente.
- **Piano non condiviso.** Il piano dei pasti, quando esiste, è su carta e non è consultabile da tutta la famiglia.

**Come lo si affronta oggi:** la famiglia dell'utente pianifica su carta. Non usa nessuna app di meal planning.

**Cosa costa non risolverlo:** pasti ripetitivi, tempo perso a pianificare e a cercare le ricette, cibo preparato per il numero sbagliato di persone, lamentele in famiglia, idee "da provare" dimenticate.

## Glossario essenziale

Il glossario completo è in `docs/02-requirements.md`. Qui ci sono solo i termini necessari a leggere la visione (ASM-016).

| Termine | Significato |
|---|---|
| Famiglia | Il gruppo che condivide archivio piatti e piano dei pasti. È l'unità di isolamento dei dati (tenant). Ha un proprio fuso orario, `Europe/Rome` per default. |
| Persona della famiglia | Chiunque faccia parte della famiglia, **con o senza account**. Ha presenze e gusti. Conta nei pasti dal giorno in cui entra nella famiglia. |
| Account | Identità di accesso di una persona. Nell'MVP solo Google; email e password sono rinviati a dopo M2 (ASM-024). Un account può appartenere a più famiglie nel modello dati, ma l'interfaccia dell'MVP ne gestisce una sola (ASM-002). |
| Profilo senza account | Persona della famiglia che non accede all'app (per esempio un bambino sotto i 14 anni), gestita da un adulto che dichiara di esercitarne la responsabilità genitoriale. |
| Ruolo | Insieme fisso di permessi assegnato a un account nella famiglia: Amministratore, Pianificatore o Membro. "Membro" indica **il ruolo**, non qualunque persona della famiglia. |
| Ospite | Persona esterna alla famiglia, registrata sul pasto come numero più una nota libera (per esempio "nonni"). Non ha profilo né gusti. |
| Coperti | Numero di persone presenti a un pasto: persone della famiglia presenti più ospiti. |
| Settimana tipo | Schema ricorrente delle presenze per giorno della settimana e pasto. Una modifica vale da oggi in avanti. |
| Pasto passato | Pasto di un giorno precedente a oggi, nel fuso della famiglia. I pasti di oggi non sono ancora passati. I pasti passati restano sempre modificabili, nei limiti del ruolo, e ogni modifica entra nella cronologia. |
| Passato congelato | I pasti passati conservano le presenze che avevano. Cambiare la settimana tipo o le persone della famiglia non li modifica. Solo una correzione esplicita li cambia. |
| Piatto "da provare" / "collaudato" | Stato di un piatto nell'archivio: idea non ancora cucinata o piatto già sperimentato con successo. |
| Voce libera / pasto speciale | Testo libero in un pasto (per esempio "avanzi di ieri"), oppure un pasto marcato "fuori casa", "ristorante" o "saltato". |
| Codice di invito alla creazione | Codice emesso dal gestore della piattaforma che permette di creare una nuova famiglia durante la fase a registrazione chiusa. |
| Link di invito alla famiglia | Link monouso con scadenza, generato in una famiglia per farvi entrare una persona come Membro o Pianificatore. |

## Utenti

Il prodotto è **multi-famiglia (multi-tenant) fin dal primo giorno**: ogni famiglia vede solo i propri dati. Nell'MVP la **registrazione è chiusa**: si parte dalla famiglia dell'utente e da poche famiglie di amici tester. L'apertura al pubblico è una milestone successiva ed esplicita (vedi "Ambito").

| Ruolo | Descrizione | Numero stimato (lancio / 12 mesi) |
|---|---|---|
| Gestore della piattaforma | Il proprietario del prodotto (l'utente). Agisce solo con comandi da console, perché nell'MVP non c'è un'interfaccia di amministrazione. I comandi servono a:<br>- emettere i codici di invito per creare nuove famiglie;<br>- creare la famiglia iniziale (M0);<br>- aggiungere come Amministratore un membro che lo chiede dall'email del proprio account, quando la famiglia non ha più un Amministratore (recupero tramite il supporto, visibile a tutta la famiglia, senza ulteriori condizioni);<br>- avviare le esportazioni richieste durante la beta.<br>Ogni comando è registrato in un audit log. Non legge mai i contenuti delle famiglie. Non è un ruolo dentro una famiglia. | 1 / 1 |
| Amministratore | Crea la famiglia (con un codice di invito alla creazione), invita persone tramite link, gestisce ruoli e profili, può fare tutto ciò che fanno gli altri ruoli. Possono esserci più Amministratori, sempre almeno uno. Il ruolo di Amministratore si assegna solo dall'interno della famiglia, mai con un link di invito. | 1 per famiglia / 1-2 per famiglia |
| Pianificatore | Gestisce l'archivio dei piatti e il piano dei pasti, comprese le correzioni dei pasti passati, e le presenze di tutti. | 1-2 per famiglia (ASM-001) |
| Membro | Consulta il piano, gestisce la propria settimana tipo e le proprie presenze, anche passate, esprime i propri gusti, aggiunge idee di piatti "da provare", e indica gli ospiti dei pasti a cui è presente. | 2-4 per famiglia (ASM-001) |
| Profilo senza account | Persona della famiglia senza credenziali (in particolare i minori di 14 anni), gestita da Amministratore o Pianificatore. Serve per presenze e gusti. In seguito può essere collegato a un account mantenendo gusti e storico presenze, previa conferma di un Amministratore. | 0-3 per famiglia (ASM-001) |
| Ospite | Registrato sul pasto come numero più una nota. | n/a |

Qualunque account, quindi dai 14 anni, può avere **qualunque ruolo**, a scelta dell'Amministratore. Un link di invito assegna al massimo il ruolo di Pianificatore.

Famiglie: al lancio 1 (quella dell'utente), poi alcune famiglie tester su invito. Nell'anno uno si prevedono fino a circa 50 famiglie e 250 account. La data di apertura al pubblico non è fissata (Q-001).

Nell'MVP i tre ruoli di famiglia sono **fissi**. I permessi configurabili per singolo utente sono previsti per una fase successiva.

## Proposta di valore

**La cosa da fare in modo eccellente: pianificare i pasti della famiglia per i prossimi X giorni**, in pochi minuti, con un piano consultabile da tutti sul telefono.

Rispetto alla carta e alle alternative esistenti, Menu Design mette insieme in un unico posto:

1. **La memoria della famiglia:** i piatti collaudati, quelli da provare, a chi piacciono, a chi sono indifferenti e a chi no, e dove si trova la ricetta (link, libro e pagina, rivista, testo libero, anche più fonti per piatto).
2. **Chi c'è e quando:** presenze ricavate da una settimana tipo, con assenze segnate per singolo pasto e ospiti, e quindi i coperti di ogni pasto.
3. **Aiuto alla varietà durante la scelta:** "cucinato N giorni fa", filtro sui piatti "da provare", avviso se a una persona presente il piatto non piace. Questo permette, per esempio, di proporre il piatto che piace solo ai genitori quando i figli non ci sono.
4. **Libertà di struttura:** ogni famiglia sceglie quali pasti pianificare (Colazione, Pranzo, Merenda, Cena, Altro pasto), quali compaiono di default e quali aggiungere nei singoli giorni. Ogni pasto può avere più piatti (primo, secondo, contorno, piatto unico e altre portate come antipasto, dolce, bevande), voci libere o uno stato speciale.
5. **Velocità:** spostare, scambiare e copiare giorni o settimane, anche passati, come base del nuovo piano.

## Alternative esistenti

| Alternativa | Punti di forza | Limiti |
|---|---|---|
| Carta (soluzione attuale dell'utente) | Gratuita, immediata, nessuna curva di apprendimento. | Non condivisa, nessuno storico, nessuna lista "da provare", nessun riferimento alle ricette, nessuna gestione delle presenze. |
| Paprika Recipe Manager | Archivio ricette maturo con importazione da siti web, calendario dei pasti, lista della spesa condivisa. [1][2] | È soprattutto un ricettario: il pianificatore è descritto come basilare (ricette e note su un calendario). [1] App a pagamento. [2] Non gestisce presenze, coperti né gradimento per singola persona (non riscontrato nelle fonti consultate). |
| Plan to Eat | Pensato per la pianificazione: calendario condiviso drag-and-drop e lista della spesa generata dal piano. [3] | Centrato su ricette importate e spesa, non su presenze, coperti e gradimento per persona (non riscontrato nelle fonti consultate). Interfaccia in inglese (da verificare). |

Fonti:
[1] [Plan to Eat, "Paprika App Review: Pros and Cons"](https://plantoeat.com/?p=38013) (recensione scritta da un concorrente).
[2] [Paprika Recipe Manager 3, App Store](https://apple.co/3AF2toV).
[3] [FoodiePrep, "Paprika vs Plan to Eat"](https://www.foodieprep.ai/blog/paprika-vs-plan-to-eat) (scritta da un concorrente, che lo dichiara).

L'analisi comparativa è indicativa: le fonti sono soprattutto recensioni di terze parti e non è stata fatta una prova diretta dei prodotti.

## Ambito dell'MVP

### Dentro (MVP)

- **Accesso a registrazione chiusa:** può creare una famiglia solo chi ha un codice di invito alla creazione emesso dal gestore della piattaforma con un comando da console, e non appartiene già a una famiglia. Ogni emissione viene registrata in un audit log. Chi crea la famiglia ne diventa Amministratore.
- **Ingresso in una famiglia:** l'Amministratore genera un **link di invito monouso con scadenza** (7 giorni), con ruolo **Membro o Pianificatore**, e lo invia con qualunque canale (WhatsApp, email, altro). Chi lo riceve può accettarlo o rifiutarlo. Accetta con il proprio account Google, l'unico metodo di accesso dell'MVP (ASM-024). Se in futuro arriverà la registrazione con email e password, esisterà solo dentro un invito o un codice.
- **Dichiarazione dell'età e informativa:** all'accettazione dell'invito o alla creazione della famiglia la persona dichiara di avere almeno 14 anni e prende visione di un'informativa privacy breve, comprensibile anche dai ragazzi. Si conservano solo il fatto "dichiarato ≥14" e la data, non la data di nascita. Se la persona dichiara meno di 14 anni, l'operazione è bloccata.
- **Autenticazione:** solo Google, da M0. Email e password sono rinviati a dopo M2 (ASM-024, CHG-020 dei requisiti). La sessione dura 30 giorni dall'ultimo utilizzo, con un massimo assoluto di 90 giorni. Le operazioni critiche richiedono un login recente.
- **Ruoli:** 3 ruoli fissi (Amministratore, Pianificatore, Membro), assegnabili a qualunque account. Più Amministratori ammessi, sempre almeno uno: l'ultimo Amministratore non può uscire dalla famiglia senza nominarne un altro o eliminare la famiglia. Se la famiglia non ha più un Amministratore, un membro scrive al Gestore dall'email del proprio account e il Gestore lo aggiunge come Amministratore con un comando. Il comando riceve l'email solo come hash e verifica solo che appartenga a un membro, e tutta la famiglia vede l'avviso "X è diventato Amministratore tramite il supporto". Gli Amministratori vedono l'email verificata di chi entra con un invito.
- **Persone della famiglia:** account (adulti e adolescenti dai 14 anni, con qualunque ruolo) e profili senza account per i minori di 14 anni. Chi crea un profilo dichiara di esercitare la responsabilità genitoriale o di averne il consenso. Un profilo senza account può essere collegato in seguito a un account, mantenendo gusti e storico presenze, previa conferma di un Amministratore. Ogni account modifica il proprio nome visualizzato.
- **Uscita ed eliminazioni:** quando una persona esce dalla famiglia, i suoi gusti, la sua settimana tipo e le sue eccezioni future vengono cancellati, mentre le presenze passate restano come "ex membro". Ogni account può eliminare il proprio account. L'eliminazione della famiglia cancella davvero tutti i dati dopo 7 giorni di ripensamento (ASM-022).
- **Archivio piatti:**
  - campi: nome, **una o più portate**, stato "da provare" o "collaudato", note, tempo di preparazione a fasce, tag liberi della famiglia, **una o più fonti** della ricetta, **punteggio priorità** da 1 a 10 (5 per default, unico per la famiglia, modificato da Pianificatori e Amministratori, M2);
  - **ordinamento preferito** di ogni account (nome, priorità, non cucinato da più tempo), salvato sul server (M2). In M0 e M1 il selettore ordina per nome;
  - gusti per persona: piace, neutro o non piace, oppure "sconosciuto" se non espresso;
  - "ultima volta cucinato" ricavata automaticamente dal piano (ASM-003);
  - portate personalizzate della famiglia;
  - un Membro può aggiungere idee "da provare";
  - un piatto già pianificato si archivia invece di cancellarlo;
  - ricerca, filtri e ordinamento per "non cucinato da più tempo";
  - avviso di nomi simili;
  - **import da CSV** (Could, M2: è una novità rispetto alle prime revisioni).
- **Piano dei pasti:**
  - orizzonte libero (qualunque intervallo di giorni), con la settimana come vista predefinita (ASM-018);
  - pasti di default della famiglia più pasti aggiunti nel singolo giorno, compresi **più "Altro pasto" nello stesso giorno, ognuno con un nome libero** (per esempio "Aperitivo" e "Dopocena"). L'interfaccia arriva in M2, ma il modello dati li supporta da M0;
  - più piatti per pasto, voci libere (salvabili in archivio) e pasti speciali ("fuori casa", "ristorante", "saltato");
  - spostare, scambiare e copiare piatti, pasti, giorni e settimane;
  - **pasti passati sempre correggibili** nei limiti del ruolo, compreso "non cucinato";
  - avviso di conflitto quando due persone modificano la stessa cosa;
  - cronologia delle modifiche visibile a tutta la famiglia, e indicatore "modificato da… dopo la tua ultima visita", che usa l'ultima visita conservata sul server.
- **Presenze:**
  - ogni persona è presente secondo la settimana tipo, o sempre presente se la settimana tipo non c'è, e si segnano le assenze (ASM-014). A ogni "Altro pasto" sono tutti presenti per default;
  - ospiti come numero più nota, coperti per pasto;
  - **passato congelato:** le modifiche alla settimana tipo valgono da oggi in avanti, e una persona conta solo dal giorno in cui è entrata.
- **Aiuto alla varietà durante la scelta di un piatto:** "cucinato N giorni fa", filtro "da provare", avviso se a una persona presente il piatto non piace (ASM-016).
- **Consultazione:** da parte di tutta la famiglia, da telefono (web app mobile-first). Consultazione offline in sola lettura dell'ultimo piano caricato, come PWA installabile (Should, M2). I dati offline restano validi al massimo 7 giorni.
- **Diritti sui dati durante la beta:** l'esportazione dei dati, propri o della famiglia, avviene su richiesta tramite il Gestore. Il file è scaricabile solo dal richiedente dentro l'app, e la risposta arriva entro un mese. L'esportazione self-service arriva all'apertura al pubblico.
- **Lingua e predisposizione multilingua:** interfaccia solo in italiano, ma già predisposta per altre lingue (vedi "Predisposizioni architetturali").

### Milestone di rilascio dentro l'MVP

L'ambito resta quello confermato. Le milestone ne definiscono solo l'ordine di rilascio. Il dettaglio è in ASM-020 e, per singolo requisito, in `docs/02-requirements.md`.

| Milestone | Contenuto | Risultato atteso |
|---|---|---|
| **M0** | Si attivano: <br>- la famiglia dell'utente, creata da console; <br>- **solo login Google**, quindi nessun invio di email; <br>- archivio piatti con portate multiple, tempo di preparazione, fonti multiple e archiviazione; <br>- piano dei pasti con voci libere, pasti speciali e correzione dei pasti passati; <br>- "cucinato N giorni fa" e filtro "da provare"; <br>- registrazione degli eventi di modifica; <br>- interfaccia in italiano predisposta per altre lingue. | La carta può già essere abbandonata. |
| **M1** | Si attivano: <br>- persone e ruoli, profili senza account con dichiarazione di responsabilità genitoriale, gusti; <br>- link di invito (accettazione con Google), dichiarazione dell'età, informativa breve; <br>- presenze, ospiti e coperti, passato congelato; <br>- spostare e copiare, conflitti, cronologia; <br>- invariante "almeno un Amministratore" e recupero tramite il Gestore; <br>- esportazione su richiesta. | Tutta la famiglia consulta il piano e segna le assenze. |
| **M2** | Si attivano: <br>- interfaccia per più Amministratori; <br>- avviso "non piace" e proposta di promozione a "collaudato"; <br>- tag, filtri avanzati, portate personalizzate (S), avviso di nomi simili (S), import CSV (C); <br>- punteggio priorità e ordinamento preferito (S), più "Altro pasto" con nome nello stesso giorno (S); <br>- codici di creazione per le famiglie tester; <br>- collegamento di un profilo a un account; <br>- eliminazione dell'account e della famiglia; <br>- consultazione offline (S). <br>L'accesso resta solo con Google, quindi anche in M2 l'app non invia email (il login con email e password è rinviato, CHG-020). | MVP completo, pronto per le famiglie tester. |

### Fuori (non nell'MVP)

- Registrazione aperta al pubblico.
- Caricamento di foto e immagini: nell'MVP solo link e riferimenti testuali.
- Allergie e intolleranze: sono dati sanitari, categoria particolare ai sensi dell'art. 9 GDPR. Rinviate per scelta concordata con l'utente.
- Importazione automatica delle ricette dai link.
- Notifiche (email o push). Nell'app c'è solo l'indicatore "modificato da… il…".
- Suggerimenti automatici di piatti o di piani.
- Modifica del piano senza connessione.
- Lista della spesa.
- Integrazioni con servizi esterni (oltre al login Google).
- Interfaccia in lingue diverse dall'italiano (la predisposizione invece è dentro l'MVP).
- Interfaccia di amministrazione della piattaforma.
- Traduzione dei contenuti inseriti dagli utenti (ASM-025, Q-014).
- Esportazione self-service e cambio dell'email di un account con password (Q-021 dei requisiti): entrambi da fare prima dell'apertura al pubblico, il secondo solo se nel frattempo arriva il login con email e password (CHG-020).

### In seguito (roadmap indicativa, non impegnativa)

- **Apertura al pubblico:** milestone esplicita. Condizioni di ingresso:
  - ASM-011 interamente soddisfatta (informativa privacy completa, termini d'uso, esportazione e cancellazione dei dati in self-service);
  - cancellazione automatica dei dati delle famiglie e degli account inattivi da 24 mesi, dopo un avviso;
  - revisione professionale della DPIA, che per la beta è già adottata da M1.
- App native Android e iOS, con login Apple insieme all'app iOS.
- Proposte delle persone della famiglia: variazioni al menù, spostamento di piatti da un giorno all'altro.
- Valutazione nutrizionale e di equilibrio del menù, alternanza dei piatti.
- Condivisione pubblica dei menù ed eventuale monetizzazione.
- Permessi configurabili per singolo utente.
- Interfaccia per gestire più famiglie con lo stesso account.
- Altre lingue dell'interfaccia, oltre all'italiano.
- Login con email e password, con email di verifica e recupero, solo dentro un invito o un codice (rinviato da M2 con CHG-020; quando riprenderlo è Q-031 dei requisiti).
- MFA opzionale per gli account con password.
- Allergie e intolleranze, foto, notifiche, lista della spesa, importazione ricette.

### Predisposizioni architetturali fin dal primo giorno

Non sono funzionalità, ma vincoli per il design.

- Isolamento rigoroso dei dati per famiglia (multi-tenant).
- Appartenenza account ↔ famiglia di tipo molti-a-molti nel modello dati.
- Non precludere una futura API riutilizzabile dalle app native. Lo stile dell'API è deciso dall'architetto con un ADR.
- Hosting portabile: da piano gratuito a costo fisso contenuto, poi a infrastruttura professionale.
- Modello dati che non impedisca una futura condivisione pubblica dei menù (ASM-010).
- **Eventi di modifica da M0:** ogni modifica a piano, presenze, ospiti e stato dei piatti registra data, autore e **ruolo dell'autore in quel momento**. Servono alla cronologia e ai KPI.
- **Fuso orario per famiglia** e **passato congelato:** il meccanismo è scelto dall'architetto con un ADR.
- **Internazionalizzazione (i18n) fin da M0**, su richiesta dell'utente: "voglio che l'applicazione supporti più lingue. In M0 può essere solo in italiano, ma deve già supportare la possibilità di estendere a più lingue in futuro". Quindi:
  - tutti i testi dell'interfaccia sono esternalizzati, senza testo italiano scritto direttamente nel codice;
  - date, ore e numeri sono formattati in base alla lingua, al formato locale e al fuso della famiglia;
  - aggiungere una lingua non deve richiedere modifiche al codice applicativo.

## Metriche di successo

Orizzonte: 3 mesi dall'adozione da parte della famiglia dell'utente. I KPI si chiamano KPI-1 … KPI-8 per non confondersi con le milestone M0, M1 e M2. I target sono stati **confermati dall'utente** (ASM-004 … ASM-008, ASM-021). Le definizioni operative sono in `docs/02-requirements.md`, sezione "Misurazione dei KPI".

**Avvertenza:** con una sola famiglia, più pochi tester, questi numeri sono **segnali di autovalutazione** dell'utilità del prodotto, non una prova di product-market fit. I KPI si calcolano sulla famiglia del Gestore, perché il Gestore non vede i dati delle famiglie tester.

**Baseline:** prima di usare l'app si raccolgono i piani su carta di 2-4 settimane, per confrontare ripetizioni e piatti nuovi (KPI-4 e KPI-5).

**Definizioni comuni (ASM-019):**
- la settimana inizia il lunedì alle 00:00, nel fuso della famiglia;
- un "piatto principale" è un'assegnazione con portata **primo, secondo o piatto unico** nel pasto. Contorni, antipasti, dolci e bevande sono esclusi.

| KPI | Target | Come si misura |
|---|---|---|
| KPI-1. Piano sempre pronto: copertura | In almeno 11 settimane su 12 (≥ 90%), entro le 00:00 del lunedì (fuso della famiglia) esiste un piano che copre tutti i pasti di default dei 7 giorni della settimana (ASM-004). | Eventi di modifica: per ogni settimana, stato del piano all'ora limite. Un pasto è coperto se ha almeno un piatto, una voce libera o uno stato speciale. |
| KPI-2. Piano sempre pronto: tempo | Tempo mediano per comporre il piano di una settimana ≤ 10 minuti (ASM-005). | Eventi di modifica. Una sessione è una sequenza di modifiche dello stesso autore sulla stessa settimana, con pause di al massimo 30 minuti. Si misura la durata dal primo all'ultimo evento. |
| KPI-3. Abbandono della carta | La carta non viene più usata per pianificare dal rilascio di M0 in poi. | Autovalutazione dell'utente a 1 e 3 mesi. |
| KPI-4. Più varietà: ripetizioni | Meno del 20% dei piatti principali pianificati è ripetuto entro 7 giorni, e comunque meno della baseline su carta (ASM-006). | Dati del piano: quota di assegnazioni di un piatto principale già pianificato nei 7 giorni precedenti. |
| KPI-5. Più varietà: piatti provati | In media almeno 1 passaggio "da provare" → "collaudato" ogni 2 settimane (ASM-007). | Conteggio dei cambi di stato registrati negli eventi di modifica. |
| KPI-6. Ricette ritrovate | Almeno l'80% dei piatti "collaudati" ha una fonte della ricetta registrata. Nessun episodio di "ricetta non trovata" riferito dall'utente nel trimestre (ASM-008). | Dati dell'archivio, più autovalutazione dell'utente a 1 e 3 mesi. |
| KPI-7. Partecipazione | In almeno il 30% delle settimane, almeno un account con ruolo Membro in quel momento ha aperto il piano o ha inserito un'eccezione di presenza (ASM-021). | Visita settimanale (un solo dato sì/no per account e per settimana) ed eventi di modifica delle presenze. Nessuna analitica di terze parti. |
| KPI-8. Coperti giusti | Al massimo 1 pasto al mese preparato per un numero sbagliato di persone, a causa di presenze non aggiornate (ASM-021). | Autovalutazione dell'utente a 1 e 3 mesi, confrontata con la situazione su carta. |

Le metriche si calcolano sui dati che l'app già conserva per il suo funzionamento. Non è prevista nessuna analitica comportamentale di terze parti (ASM-009).

## Vincoli

- **Piattaforme:** web app responsive mobile-first per l'MVP, installabile come PWA. In seguito app native Android e iOS: l'architettura non deve precludere una futura API riutilizzabile da queste app.
- **Tempi e budget:** sviluppo a cura del solo utente nel tempo libero, senza scadenze rigide. Si parte da piani gratuiti, con un'architettura migrabile prima verso un piccolo costo fisso e poi verso un'infrastruttura più professionale. Non c'è un tetto di spesa fisso: le parole dell'utente sono "valuto opzioni a pagamento di volta in volta, confrontandole con le opzioni analoghe gratis". Ogni scelta a pagamento va quindi presentata con il suo equivalente gratuito.
- **Esercizio e operazioni:**
  - Dati ospitati nell'Unione Europea.
  - Backup almeno settimanale, con un ripristino provato ogni 3 mesi.
  - Monitoraggio minimo di disponibilità ed errori.
  - Allarme al 70% della quota di archiviazione. Gli eventi di modifica sono salvati in forma compatta, e il passaggio a un piano a pagamento avviene solo se serve.
  - Igiene degli accessi del Gestore (MFA resistente al phishing, credenziali separate dall'ambiente di sviluppo), hardening del database e controlli sulla catena di fornitura. Se sul piano gratuito sono disponibili le restrizioni di rete, si usa un IP di uscita statico (circa 5 €/mese).
  - Disponibilità mensile ≥ 99%, in modalità best effort.
- **Accesso:** registrazione chiusa nell'MVP. Si entra con un codice di invito alla creazione (nuova famiglia) o con un link di invito monouso (famiglia esistente).
- **Dati trattati e normative:**
  - L'utente è nell'UE: si applica il **GDPR** già nella fase a registrazione chiusa, perché vengono trattati dati personali di persone diverse dall'utente (familiari e famiglie tester).
  - Dati nell'MVP:
    - dati di account: nome visualizzato, email, identità Google (nessuna password nell'MVP), dichiarazione di età, presa visione dell'informativa;
    - composizione della famiglia e profili di **minori**, con e senza account;
    - gusti alimentari per persona: piace, neutro, non piace;
    - presenze ai pasti, settimana tipo e ospiti con nota. Sono dati riservati, perché indicano quando una persona è o non è a casa;
    - per ogni account: l'ultima visita al piano (un solo valore, sul server), le visite settimanali e l'ordinamento preferito. L'email è visibile agli Amministratori della famiglia;
    - cronologia delle modifiche, visite settimanali al piano, link e riferimenti a ricette.
  - **Minori:** account propri solo dai 14 anni, con qualunque ruolo. La soglia è confermata dall'art. 2-quinquies del Codice privacy, in attuazione dell'art. 8 GDPR (ASM-015). Sotto i 14 anni ci sono solo profili gestiti da un adulto, che dichiara di esercitare la responsabilità genitoriale o di averne il consenso. L'età si verifica con un'autodichiarazione, conservando solo "dichiarato ≥14" e la data. L'informativa è scritta in linguaggio semplice.
  - **Prima di M1**, cioè prima che entrino persone diverse dalla famiglia del Gestore, servono:
    - un'informativa breve, che cita anche ultima visita, email visibile agli Amministratori, recupero tramite il supporto e cache offline;
    - un registro dei trattamenti;
    - gli accordi di trattamento con i fornitori;
    - una procedura per le violazioni dei dati;
    - la **DPIA v1**, cioè la sezione 8 del threat model adottata, rivista e firmata dall'utente.

    L'utente ha accettato esplicitamente il rischio residuo Medio del link di invito come segreto al portatore: chi ottiene il link entro 7 giorni può entrare come Membro o Pianificatore.
  - **Conservazione:** i dati restano finché esistono la famiglia e l'account. Le famiglie e gli account inattivi da 24 mesi si cancellano dopo un avviso, e questa regola deve essere attiva entro l'apertura al pubblico. I backup ruotano entro 30 giorni.
  - Dati esclusi dall'MVP per scelta: allergie e intolleranze (art. 9 GDPR, dati relativi alla salute) e foto.
  - L'apertura al pubblico richiede informativa privacy completa, termini d'uso, esportazione e cancellazione dei dati in self-service (ASM-011) e una DPIA.
- **Integrazioni:**
  - Autenticazione: Google da M0, unico metodo dell'MVP. Email e password dopo M2, Apple in seguito.
  - Nessun invio di email dall'app nell'MVP. Un provider email servirà solo con il login con email e password (verifica, recupero e notifiche) o con l'avviso di inattività richiesto per l'apertura al pubblico.
  - Gli inviti viaggiano su canali scelti dall'utente, quindi non richiedono un'integrazione.
- **Lingua:** interfaccia solo in italiano nell'MVP, ma con internazionalizzazione predisposta fin da M0 (testi esternalizzati, formati di data e numero legati alla lingua). Altre lingue in seguito. I contenuti inseriti dagli utenti, come nomi dei piatti e note, si conservano così come inseriti e non vengono tradotti (ASM-025, Q-014).
- **Amministrazione della piattaforma:** nell'MVP solo comandi da console, con audit log. Nessuna interfaccia di amministrazione e nessuna lettura dei contenuti delle famiglie da parte del gestore.
- **Competenze e manutenzione:** un solo sviluppatore part-time, quindi si privilegiano soluzioni semplici, servizi gestiti e poche dipendenze consolidate, con basso carico operativo.

## Ipotesi e domande aperte

Le ipotesi da ASM-026 in poi sono in `docs/02-requirements.md`.

### Ipotesi

- **ASM-001** Una famiglia tipica ha 2-6 persone, di cui 1-2 pianificatori. *Impatto se cambia:* limiti, prestazioni e UX della gestione presenze (per esempio famiglie allargate o comunità più numerose).
- **ASM-002** *Confermata dall'utente.* Nel modello dati l'appartenenza account ↔ famiglia è molti-a-molti fin dal primo giorno. L'interfaccia dell'MVP gestisce una sola famiglia per account. *Impatto se cambia:* nessuno sul modello dati. Gestire più famiglie nell'interfaccia richiede la scelta della famiglia attiva e controlli di autorizzazione per ogni famiglia.
- **ASM-003** *Confermata.* Un piatto assegnato a un pasto passato, non speciale, si considera "cucinato" e alimenta "ultima volta cucinato". È prevista una correzione rapida "non cucinato". Un pasto è passato quando il suo giorno è precedente a oggi, nel fuso della famiglia: i pasti di oggi non sono ancora cucinati. *Impatto se cambia:* serve un'azione esplicita "cucinato" e cambiano KPI-4 e KPI-5.
- **ASM-004** *Confermata.* Target KPI-1: piano pronto entro le 00:00 del lunedì, nel fuso della famiglia, in ≥ 90% delle settimane. *Impatto se cambia:* solo sulla valutazione del successo.
- **ASM-005** *Confermata.* Target KPI-2: tempo mediano ≤ 10 minuti per il piano settimanale, misurato dagli eventi di modifica. *Impatto se cambia:* solo sulla valutazione del successo, ma orienta le priorità UX.
- **ASM-006** *Confermata.* Target KPI-4: meno del 20% di ripetizioni dei piatti principali entro 7 giorni, e comunque meno della baseline su carta. *Impatto se cambia:* solo sulla valutazione del successo.
- **ASM-007** *Confermata.* Target KPI-5: almeno 1 passaggio "da provare" → "collaudato" ogni 2 settimane. *Impatto se cambia:* solo sulla valutazione del successo.
- **ASM-008** *Confermata.* Target KPI-6: ≥ 80% dei piatti collaudati con fonte registrata. *Impatto se cambia:* solo sulla valutazione del successo.
- **ASM-009** Le metriche si calcolano sui dati applicativi, senza strumenti di analitica di terze parti né tracciamento. *Impatto se cambia:* servono consenso cookie/tracking e valutazione privacy aggiuntiva.
- **ASM-010** La futura condivisione pubblica riguarderà menù e piatti, **mai** presenze, gusti per persona o dati dei minori. *Impatto se cambia:* la classificazione dei dati e il threat model vanno rivisti già ora.
- **ASM-011** *Confermata come condizione di ingresso della milestone "Apertura al pubblico".* Prima dell'apertura al pubblico saranno disponibili informativa privacy completa, termini d'uso, esportazione e cancellazione self-service dei dati di account e famiglia. *Impatto se cambia:* l'apertura al pubblico non sarebbe conforme al GDPR.
- **ASM-012** *Confermata.* Ogni account gestisce le proprie presenze, anche passate, e i propri gusti. Amministratore e Pianificatore gestiscono presenze e gusti di tutti, profili senza account compresi. *Impatto se cambia:* cambia la matrice ruoli × azioni.
- **ASM-013** ~~SUPERATA~~ (rev. 4). Diceva che il gradimento è binario. Ora i gusti sono piace, neutro o non piace, più "sconosciuto" se non espresso. L'avviso scatta solo su "non piace" (FR-027, FR-048).
- **ASM-014** *Confermata.* Regola di presenza di default: ogni persona è presente secondo la settimana tipo. Senza settimana tipo, è presente. Si segnano le assenze. A ogni "Altro pasto" sono tutti presenti per default. *Impatto se cambia:* cambiano UX delle presenze, calcolo dei coperti e KPI-7.
- **ASM-015** *Verificata dal security engineer.* La soglia italiana per il consenso digitale autonomo è 14 anni (art. 8 GDPR, attuato in Italia dall'art. 2-quinquies del Codice privacy). Il testo vigente va ricontrollato su Normattiva prima di pubblicare l'informativa. *Impatto se cambia:* cambia l'età minima per avere un account proprio.
- **ASM-016** *Confermata.* Il termine "persona della famiglia" indica chiunque faccia parte della famiglia, con o senza account. "Membro" indica solo il ruolo. L'avviso "non piace" riguarda ogni persona presente al pasto, con o senza account, ma non gli ospiti. *Impatto se cambia:* cambia la logica degli avvisi di varietà.
- **ASM-017** *Confermata.* Il passaggio "da provare" → "collaudato" è sempre manuale. Dopo che un piatto "da provare" è stato cucinato per la prima volta, l'app chiede se promuoverlo. *Impatto se cambia:* cambia KPI-5. Un passaggio automatico gonfierebbe il KPI.
- **ASM-018** *Confermata.* Orizzonte del piano libero (qualunque intervallo di giorni, al massimo 62 per vista), con la settimana come vista predefinita. Lo storico del piano si conserva finché esiste la famiglia e si cancella con essa. *Impatto se cambia:* cambiano UX del piano, politica di conservazione dei dati e calcolo di varietà e KPI.
- **ASM-019** *Aggiornata in rev. 4, confermata al gate G2.* La settimana inizia il lunedì, nel fuso della famiglia. "Piatto principale" significa assegnazione con portata **primo, secondo o piatto unico** nel pasto (ASM-026 dei requisiti). *Impatto se cambia:* cambiano le misure di KPI-1 e KPI-4.
- **ASM-020** *Aggiornata in rev. 4, confermata al gate G2.* La distribuzione nelle milestone è quella della tabella "Milestone di rilascio dentro l'MVP". Il dettaglio per requisito è nella colonna "Milestone" dei requisiti (ASM-027). *Impatto se cambia:* cambia solo l'ordine dei rilasci, non lo scope.
- **ASM-021** *Aggiornata in rev. 4, confermata.* Target di KPI-7 "Partecipazione": almeno il 30% delle settimane con almeno un account Membro che ha aperto il piano o inserito un'eccezione di presenza. Target di KPI-8: al massimo 1 pasto al mese con coperti sbagliati. *Impatto se cambia:* solo sulla valutazione del successo.
- **ASM-022** *Confermata.* Il periodo di ripensamento prima della cancellazione definitiva di una famiglia è di 7 giorni. In questo periodo la famiglia è in sola lettura, salvo le eccezioni previste dai requisiti, e un Amministratore può annullare l'eliminazione. *Impatto se cambia:* cambia solo la politica di conservazione.
- **ASM-023** *Confermata.* Il link di invito alla famiglia scade dopo 7 giorni, vale per una sola accettazione e può essere revocato dall'Amministratore. Assegna al massimo il ruolo di Pianificatore. Il codice di invito alla creazione vale per una sola famiglia e scade dopo 30 giorni. *Impatto se cambia:* cambia il rischio di accessi non autorizzati (threat model).
- **ASM-024** *Confermata, aggiornata in rev. 7 (CHG-020, decisione dell'utente del 2026-10-19).* Tutte le famiglie tester hanno un account Google. Per questo il login con email e password, con le email di verifica e di recupero password, **non è nell'MVP**: è rinviato al backlog dopo M2. In tutto l'MVP chi entra in una famiglia, adolescenti compresi, deve avere un account Google. *Prima:* email e password entravano in M2. *Impatto se cambia:* se una persona di una famiglia tester non ha o non vuole un account Google, può solo comparire come profilo senza account finché email e password non vengono ripresi (Q-031 dei requisiti), e con loro l'invio di email, un provider email con DPA e l'aggiornamento dell'informativa e della DPIA.
- **ASM-025** I contenuti inseriti dagli utenti (nomi dei piatti, note, fonti delle ricette, nomi dei pasti personalizzati) si conservano così come inseriti e non vengono mai tradotti. Solo l'interfaccia è multilingua. *Impatto se cambia:* servirebbero contenuti multilingua nel modello dati, con impatto sulla futura condivisione pubblica dei menù. Vedi Q-014.

### Domande aperte

- **Q-001** *Parzialmente chiusa.* L'apertura al pubblico è una milestone successiva ed esplicita, con le condizioni di ingresso indicate nell'ambito. Per l'anno uno si prevedono fino a circa 50 famiglie e 250 account. Resta aperto l'orizzonte dell'apertura al pubblico. *Impatto:* dimensionamento oltre l'anno uno.
- **Q-002** **CHIUSA** (2026-10-17). Modello dati molti-a-molti fin dal primo giorno, interfaccia MVP con una famiglia per account. Vedi ASM-002.
- **Q-003** **CHIUSA** (2026-10-17, aggiornata dal 2026-10-18). Account propri dai 14 anni, con qualunque ruolo. Sotto i 14 anni solo profili gestiti da un adulto, collegabili in seguito a un account.
- **Q-004** **CHIUSA.** Vedi ASM-003 e ASM-017.
- **Q-005** **CHIUSA** (2026-10-17). Nessun tetto fisso: le opzioni a pagamento si valutano caso per caso rispetto agli equivalenti gratuiti.
- **Q-006** **CHIUSA.** Vedi ASM-018.
- **Q-007** **CHIUSA.** KPI-2 si misura in modo automatico dagli eventi di modifica.
- **Q-008** **CHIUSA** (2026-10-17, precisata il 2026-10-18). Più Amministratori, sempre almeno uno, con l'invariante attiva da M1. Il ruolo si assegna solo dall'interno della famiglia. Il recupero tramite il Gestore è semplice (rev. 6): su richiesta dall'email di un membro, il Gestore lo aggiunge come Amministratore, senza soglie né limiti, con un avviso a tutta la famiglia. L'eliminazione è una cancellazione reale dopo 7 giorni.
- **Q-009** **CHIUSA** (2026-10-18). Presenze: settimana tipo per tutti i tipi di pasto tranne "Altro pasto", dove sono tutti presenti. Ospiti come numero più nota, modificabili da chi è presente e da Pianificatori e Amministratori. Nessuna azione "confermo". Correzioni sempre possibili anche sul passato.
- **Q-010** **CHIUSA** (2026-10-18). Concorrenza ottimistica con avviso di conflitto, ricarica o sovrascrittura esplicita, senza perdite silenziose. Le modifiche su unità diverse (contenuto del pasto, presenza di ogni persona, ospiti, scheda del piatto, settimana tipo) non vanno in conflitto.
- **Q-011** **CHIUSA** (2026-10-17). Autodichiarazione all'accettazione dell'invito, conservando solo "dichiarato ≥14" e la data. Il caso di una dichiarazione falsa è gestito come Q-018 dei requisiti.
- **Q-012** **CHIUSA** (2026-10-18). Un account dai 14 anni può avere qualunque ruolo, a scelta dell'Amministratore. Con un invito si arriva al massimo a Pianificatore, come per tutti.
- **Q-013** **CHIUSA** (2026-10-17). Il Gestore opera da console, con audit log, senza interfaccia di amministrazione e senza leggere i dati delle famiglie.
- **Q-014** *Aperta, non bloccante.* I contenuti inseriti dagli utenti dovranno mai essere tradotti, per esempio per la futura condivisione pubblica dei menù tra famiglie di lingue diverse? **Default: no** (ASM-025). *Impatto:* modello dati dei contenuti e funzioni di condivisione pubblica.
