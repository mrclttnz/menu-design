# ADR-0005: Hosting dell'applicazione (servizio web e job schedulati) e osservabilità, nell'UE e a costo quasi nullo

- **Stato:** ACCEPTED (decisione dell'utente, 2026-10-18: H1, Google Cloud Run in europe-west3. Le altre opzioni sono respinte e restano documentate qui sotto.)
- **Data:** 2026-10-18 (revisione 2). Revisione 3 del 2026-10-19: A-18, SR-074 e SR-076 dal threat model, nuovi job, IP statico per M1. Revisione 4: elenco dei job semplificato (OBJ-03) e verifica della conservazione delle esecuzioni (OBJ-02). Revisione 5 del 2026-10-19 (gate G4, decisione dell'utente): ambiente di **staging** e repository remoto GitHub privato.
- **Decisori:** utente, architect. Revisione di devops e security-engineer.
- **Requisiti collegati:** NFR-002, NFR-004, NFR-005, NFR-007, NFR-014, NFR-016, SR-027, SR-040, SR-051, SR-052, SR-058, SR-062
- **ADR collegati:**
  - ADR-0014: database Supabase, ACCEPTED;
  - ADR-0015: backup giornalieri, ACCEPTED;
  - ADR-0016: accettazione del rischio sull'endpoint del database;
  - ADR-0013: worker.

> **Revisione 2.** Questo ADR ora copre solo dove gira l'applicazione (servizio web più job schedulati) e l'osservabilità. Le parti già decise dall'utente sono state spostate:
> - database Supabase Free a Francoforte → ADR-0014;
> - backup giornaliero → ADR-0015;
> - endpoint del database esposto → ADR-0016;
> - regione Francoforte, o la più vicina disponibile → decisa.
>
> Su richiesta dell'utente, il confronto include 4 alternative gratuite o quasi gratuite a Cloud Run.

## Contesto
Bisogna eseguire:
- un container Python (FastAPI, ADR-0002) per l'API e i file statici;
- un worker ogni 10 minuti (ADR-0013);
- un backup giornaliero (ADR-0015);
- le migrazioni al deploy.

I vincoli sono:
- dati, log e backup nell'UE, vicino al database Supabase di Francoforte;
- controllo esterno ogni ≤ 5 minuti che tocca il database (NFR-005), quindi niente sospensioni che lo rompano e avvii a freddo accettabili;
- errori notificati entro 15 minuti (NFR-007);
- gestione dei segreti;
- avvisi o tetti di spesa (SR-062);
- portabilità (NFR-014).

### Fatti verificati il 2026-10-18
Le fonti sono in fondo. I valori dei piani gratuiti cambiano spesso: vanno ricontrollati alla configurazione.

| Piattaforma | Piano gratuito reale | Cosa succede oltre la quota | Job schedulati e backup | Log, segreti, monitoraggio | Carta e tetto di spesa |
|---|---|---|---|---|---|
| **Google Cloud Run** (riferimento), europe-west3 Francoforte | Fatturazione a richiesta: 2 M richieste, 180.000 vCPU-s e 360.000 GiB-s al mese per account di fatturazione. La quota è espressa sui prezzi di `us-central1`. L'idoneità delle regioni UE non è confermata in modo univoco dalle fonti. Nessun costo a istanza inattiva. | Pagamento a consumo, centesimi a questo carico. | Cloud Scheduler (3 job gratuiti) avvia due Cloud Run Job: worker ogni 10 minuti e backup giornaliero. Cloud Storage UE con ciclo di vita a 30 giorni. | Cloud Logging con bucket UE configurabile (30 giorni). Secret Manager (6 versioni gratuite, poi centesimi). Uptime check (1 M esecuzioni gratuite per progetto) e allarmi email. Error Reporting. | Carta richiesta. Nessun tetto rigido: budget con avvisi e `max-instances`. |
| **Azure Container Apps** (piano Consumption), Germany West Central (Francoforte) | La stessa quota per sottoscrizione: 180.000 vCPU-s, 360.000 GiB-s, 2 M richieste al mese. Una revisione scalata a zero non costa nulla. Si paga l'inattività solo con `minReplicas` > 0. | Pagamento a consumo, con tariffe simili. | Container Apps **Jobs** con trigger *schedule* (cron) per worker e backup, fatturati solo durante l'esecuzione. Blob Storage nella stessa regione con gestione del ciclo di vita (centesimi). | Log Analytics nella regione (5 GB al mese gratuiti, 31 giorni di conservazione inclusi). Segreti di Container Apps o Key Vault con identità gestita. Regole di allarme e test di disponibilità di Azure Monitor a pagamento (pochi euro al mese, tariffe da verificare), oppure monitor di uptime esterno gratuito. | Carta richiesta. Pay-as-you-go senza tetto rigido: budget con avvisi. |
| **Scaleway Serverless Containers + Serverless Jobs**, fr-par (Parigi, circa 10 ms da Francoforte) | 200.000 vCPU-s e 400.000 GB-s al mese per account. Dopo la quota si pagano circa 0,00001 € per vCPU-s e 0,000002 € per GB-s. Non è chiaro se un'istanza tenuta "calda" dai controlli ogni 5 minuti venga fatturata anche da inattiva. | Pagamento a consumo. Nel caso peggiore (istanza sempre attiva) circa 3-6 €/mese. | **Serverless Jobs** con cron integrato per worker e backup. Object Storage a pagamento (centesimi per pochi GB; 75 GB gratuiti solo di egress). | Cockpit: log dei prodotti Scaleway gratuiti per **7 giorni**, sufficienti perché SR-051 fissa solo un massimo di 30. Secret Manager a pagamento (0,04 € per versione al mese, quindi meno di 0,50 €/mese). Nessun controllo di uptime esterno nativo: serve un servizio esterno. | Carta richiesta. Avvisi di fatturazione. Azienda UE (Francia). |
| **Koyeb Free**, Francoforte | 1 servizio web da 0,1 vCPU, 512 MB e 2 GB di disco. Scale-to-zero dopo 1 ora senza traffico. Nessun worker. Mai addebitato. | Non si può superare: è un'istanza fissa. Per avere di più serve un piano a pagamento. | **Nessun cron né worker nel piano Free.** Il worker andrebbe avviato da un cron esterno (per esempio GitHub Actions) che chiama un endpoint interno autenticato. Il lavoro gira nell'istanza web. Il backup richiede `pg_dump` nell'immagine web e uno storage UE di un altro fornitore. | Log e monitoraggio di base. Uptime e allarmi esterni. | Carta richiesta da febbraio 2026 (pre-autorizzazione di 29 $). Acquisita da Mistral AI nel 2026. |
| **Oracle Cloud Always Free (VM)**, Francoforte o Milano | VM sempre accesa: Ampere A1 ridotta nel 2026 da 4 OCPU e 24 GB a **2 OCPU e 12 GB** (date di entrata in vigore discordanti, giugno o agosto 2026), oppure 2 micro AMD da 1 GB. 200 GB di block storage. | Le risorse "Always Free" non si possono superare. **Le istanze inattive possono essere recuperate da Oracle** (CPU, rete e memoria al 95° percentile sotto il 20% per 7 giorni, che è il nostro caso), a meno di passare a Pay-as-you-go. | cron o timer di systemd sulla VM per worker e backup. Object Storage OCI (quota Always Free da verificare). | Tutto da gestire in proprio: journald, Docker, Caddy per TLS, aggiornamenti del sistema operativo. Monitoraggio esterno o allarmi OCI. | Carta richiesta all'iscrizione. Capacità A1 spesso esaurita. |

Altre opzioni valutate e scartate:
- **Render Free:** si sospende dopo 15 minuti, ma i controlli lo tengono sveglio. Il cron è a pagamento al minuto (centesimi). La località dei log non è documentata. Punteggio 96.
- **Fly.io:** nessun piano gratuito per i nuovi clienti, circa 2-5 $/mese.
- **Railway:** nessun piano gratuito permanente.
- **Northflank Sandbox:** 2 servizi e 2 cron gratuiti, ma le regioni UE del piano gratuito non sono documentate.
- **VPS Hetzner a pagamento:** circa 5,5 €/mese più IVA. Con il database ormai su Supabase non nasconde più l'endpoint del database. Punteggio 95.

## Criteri di decisione
| Criterio | Peso (1-5) |
|---|---|
| Residenza UE e garanzie contrattuali | 5 |
| Sicurezza (IAM, segreti, superficie dei job) | 5 |
| Semplicità operativa per uno sviluppatore singolo | 5 |
| Costo | 4 |
| Affidabilità (niente sospensioni, scheduler affidabile) | 4 |
| Portabilità | 3 |
| Osservabilità integrata (uptime, errori, allarmi, log UE) | 3 |

## Opzioni considerate
| Criterio | H1: Cloud Run | H5: Azure Container Apps | H6: Scaleway Serverless | H3: Koyeb Free | H7: Oracle Always Free VM |
|---|---|---|---|---|---|
| Residenza UE (5) | 5 | 5 | 5 | 4 | 5 |
| Sicurezza (5) | 3 | 3 | 3 | 2 | 3 |
| Semplicità (5) | 3 | 2 | 3 | 3 | 1 |
| Costo (4) | 4 | 4 | 3 | 5 | 5 |
| Affidabilità (4) | 4 | 4 | 4 | 2 | 2 |
| Portabilità (3) | 4 | 4 | 4 | 4 | 5 |
| Osservabilità (3) | 5 | 4 | 3 | 1 | 2 |
| **Totale pesato** | **114** | **106** | **104** | **88** | **94** |

### H1: Google Cloud Run (riferimento)
- Pro:
  - il progetto Google Cloud serve già per il client OAuth;
  - fatturazione solo durante le richieste;
  - scheduler, job, segreti, log UE, uptime e allarmi in un'unica piattaforma, quasi tutti entro le quote gratuite.
- Contro:
  - carta e nessun tetto rigido;
  - IAM e Workload Identity Federation da configurare;
  - concentrazione su Google: login, hosting, log e backup (R-05).

### H5: Azure Container Apps
- Pro:
  - stesso modello e stessa quota di Cloud Run;
  - regione a Francoforte;
  - Jobs con cron nativi, Log Analytics nella regione con 5 GB gratuiti;
  - riduce la concentrazione su Google.
- Contro:
  - due cloud da gestire, perché Google resta necessario per OAuth;
  - Azure è più laborioso da configurare (environment, Log Analytics, identità gestite, credenziali federate per GitHub);
  - allarmi e test di disponibilità di Azure Monitor costano qualche euro al mese, a meno di usare un monitor esterno gratuito.

### H6: Scaleway Serverless Containers + Jobs
- Pro:
  - **fornitore UE** (Francia), senza trasferimenti extra-UE per l'hosting;
  - Jobs con cron integrato;
  - log dei prodotti gratuiti per 7 giorni;
  - interfaccia semplice.
- Contro:
  - Parigi invece di Francoforte (circa +10 ms per query);
  - costo incerto se l'istanza tenuta calda dai controlli viene fatturata (fino a circa 6 €/mese);
  - Secret Manager e storage a pagamento (centesimi);
  - serve un monitor di uptime esterno.

### H3: Koyeb Free
- Pro: costo zero garantito, Francoforte.
- Contro:
  - 0,1 vCPU, poco per FastAPI con 25 utenti concorrenti (NFR-002 a rischio);
  - nessun cron né worker, quindi trigger esterni best-effort (gli schedule di GitHub Actions possono ritardare e si disattivano dopo 60 giorni di inattività del repository);
  - backup dentro l'istanza web;
  - storage e monitoraggio da altri fornitori;
  - futuro del piano incerto.

### H7: Oracle Cloud Always Free VM
- Pro: VM sempre accesa senza avvii a freddo, cron nativo, costo zero.
- Contro:
  - **recupero delle istanze inattive** (servirebbe un carico finto, oppure il passaggio a Pay-as-you-go);
  - quota ridotta del 50% nel 2026 (tendenza sfavorevole);
  - capacità A1 scarsa;
  - sistema operativo, TLS, firewall, Docker e log tutti a carico del Gestore.

## Decisione
**H1, Google Cloud Run in europe-west3**, con questi dettagli. H5, H6, H3, H7, Render, Fly.io, Railway, Northflank e Hetzner sono respinte. Restano il riferimento se in futuro si deve migrare.
- **Servizio web:**
  - fatturazione a richiesta, `min-instances=0`, `max-instances=2` (tetto di costo), `concurrency` intorno a 40;
  - utente non root, file system di sola lettura;
  - segreti dal Secret Manager come variabili d'ambiente;
  - account di servizio dedicato.
- **Job (stessa immagine):**
  - `menu-worker` (`python -m menu worker --once`) ogni 10 minuti;
  - `menu-backup` ogni giorno (ADR-0015);
  - `menu-migrate` (`alembic upgrade head`) eseguito dal deploy. Con la stessa identità, avviato a mano, esegue anche `maint replay-deletions` dopo un ripristino (ADR-0015);
  - `menu-console` avviato dal Gestore con `gcloud` (ADR-0011);
  - `db/bootstrap.sql` non è un job: si esegue una volta dall'editor SQL di Supabase (ADR-0015, OBJ-03);
  - **verifica di devops (OBJ-02):** accertare che cosa conservano le esecuzioni dei job Cloud Run (argomenti) e gli audit log, e per quanto tempo. Impostare la conservazione delle esecuzioni al minimo utile. Esito in `docs/09-release.md`;
  - ogni job ha un account di servizio dedicato con `secretAccessor` sul **solo** segreto che gli serve, e un timeout.
- **IP di uscita statico (prima di M1, se le restrizioni di rete di Supabase sono disponibili sul piano Free):** Direct VPC egress più Cloud NAT con IP riservato in europe-west3, per il servizio e per tutti i job. Costo di circa 5 €/mese, da verificare (ADR-0016).
- **Log (SR-051):** sink verso un bucket di log in europe-west3 con conservazione di 30 giorni, esclusione dal bucket `_Default`, structlog in JSON con campo `severity`. Più un bucket dedicato al registro delle cancellazioni (35 giorni, ADR-0015).
- **Monitoraggio (NFR-005, NFR-007, SR-058):** uptime check ogni 5 minuti su `/healthz` (contratto in `docs/04-architecture.md`, componente `platform.http`), metriche basate sui log per 5xx, eccezioni ed eventi di sicurezza, allarmi email e app mobile. I controlli tengono calda l'istanza Python, il cui avvio a freddo è di 2-4 s.
- **Costi (SR-062):** budget con avvisi a 1 € e 5 €, `max-instances`, timeout dei job, degrado documentato (riduzione di `max-instances`, sospensione del worker).
- **Deploy (A-18, THR-091):**
  - repository remoto privato `github.com/mrclttnz/menu-design`. **Finché l'utente non dice altrimenti si fanno solo commit locali e ogni push richiede il suo consenso esplicito.** Di conseguenza GitHub Actions, e quindi ogni deploy, parte solo dal primo push autorizzato. Non esiste un deploy dal PC: le credenziali operative non stanno nell'ambiente di sviluppo (SR-074);
  - GitHub Actions con Workload Identity Federation;
  - la condizione del provider WIF accetta solo **questo repository** (`attribute.repository == "mrclttnz/menu-design"`) e `refs/heads/main`;
  - **due identità di deploy distinte**, ciascuna legata al `subject` del proprio environment GitHub:
    - `deploy-staging` ← `repo:mrclttnz/menu-design:environment:staging`, con permessi solo sulle risorse `*-staging`;
    - `deploy-prod` ← `repo:mrclttnz/menu-design:environment:production`, con permessi solo sulle risorse di produzione;
    - il `subject` nomina l'environment, non il ramo. Per questo **la condizione di ogni binding controlla anche `assertion.ref == "refs/heads/main"`** oltre al repository. In più **entrambi gli environment GitHub ammettono solo il ramo `main`** (deployment branch policy);
  - flusso (allineato al piano v3 §6.3, I-P13, per il budget dei minuti di Actions):
    - push su `main` → CI → **un'unica immagine** in Artifact Registry, identificata per digest;
    - environment `staging` **su richiesta** (`workflow_dispatch`) e **prima di ogni rilascio**, non a ogni push: `menu-migrate-staging`, deploy di `menu-staging`, smoke;
    - environment `production` protetto (solo da `main`, approvazione manuale dell'utente). Parte **solo se esiste un'esecuzione di staging riuscita con lo stesso digest**. Con quel digest esegue `menu-migrate` e poi aggiorna il servizio `menu`;
  - azioni fissate a SHA, `permissions` minime;
  - nessun segreto esposto alle PR da fork;
  - le migrazioni girano nel cloud, prima in staging.
- **Ambiente di staging (decisione dell'utente del 2026-10-19):**
  - **A cosa serve:** smoke dopo ogni deploy, Lighthouse e carico NFR-002 ufficiali, ZAP/DAST, esercitazioni sugli allarmi, verifica V-3 di devops (`X-Forwarded-For`).
  - **Risorse:** stesso progetto Google Cloud e stessa regione europe-west3. Nomi con suffisso `-staging`:
    - servizio `menu-staging` con `min-instances=0` e `max-instances=1`;
    - job `menu-migrate-staging`, `menu-console-staging` e `menu-worker-staging`. Il worker si avvia **a mano** o dallo smoke, senza Cloud Scheduler, così restano liberi i 3 job gratuiti;
    - job `menu-seed-staging`, che carica i dataset sintetici (per esempio `load`);
    - nessun job di backup, nessun IP statico, nessun uptime check;
    - un secondo progetto **Supabase Free** a Francoforte, con lo stesso `db/bootstrap.sql` e gli stessi quattro ruoli.
  - **Segreti e identità separati:**
    - segreti `*-staging` distinti: URL del database per ruolo, client secret OIDC, pepper;
    - account di servizio di runtime `*-staging` con `secretAccessor` sui soli segreti di staging;
    - nessuna identità di staging legge un segreto di produzione, e viceversa.
  - **OAuth:** un client OAuth **separato** per staging, nello stesso progetto, con il solo redirect URI `https://<url di menu-staging>/api/v1/auth/google/callback`. Il client di produzione non ammette URI di staging. Per i login dei test si usano account Google di prova dedicati.
  - **Regole sui dati:**
    - in staging **solo dati sintetici**: niente copie, estratti o ripristini dei dati di produzione;
    - i dataset sintetici **non si caricano mai in produzione**. Il comando `seed` parte solo se `APP_ENV` è in allow-list (`dev` o `staging`), e si ferma con qualsiasi altro valore. In produzione non esiste un job di seed, e le identità di staging non possono raggiungere il database di produzione;
    - le esportazioni di staging contengono solo dati sintetici.
  - **Pausa di Supabase Free:** un progetto Free inattivo per 7 giorni va in pausa e non risponde finché non lo si riattiva dalla dashboard. Staging non ha uptime check, quindi la pausa è attesa:
    - prima di una sessione di prove, il primo passo del runbook è "riattiva il progetto" **dalla dashboard, a mano** (pochi minuti). La pipeline e `make prerelease` non riattivano nulla: attendono `/healthz` = 200 e si fermano con un messaggio chiaro. Automatizzarla richiederebbe in CI un token di gestione Supabase valido per l'intera organizzazione, quindi anche per la produzione: rischio non giustificato;
    - se il progetto non si potesse riattivare, lo si ricrea da zero con bootstrap, `role-secret.sh` e seed. Non c'è nulla da salvare.
  - **Limite di 2 progetti Free attivi:** produzione e staging occupano entrambi i posti. La prova trimestrale di ripristino (ADR-0015) richiede un progetto temporaneo. Prima della prova si **mette in pausa staging**, che secondo fonti secondarie non conta più nel limite (da verificare, V-8), e lo si riattiva dopo aver cancellato il progetto temporaneo. Nel ripristino reale su un nuovo progetto si fa lo stesso, oppure si cancella staging e lo si ricrea in seguito.
  - **Osservabilità:** log nello stesso bucket UE, distinti per `service_name`. Gli allarmi di produzione filtrano per servizio. Le policy di staging esistono ma restano disattivate fuori dalle esercitazioni.
  - **Alternativa scartata:** un progetto Google Cloud separato per staging. Isolerebbe meglio l'IAM, ma richiede un secondo registry, la promozione dell'immagine tra progetti e configurazioni duplicate di log e budget. Con identità e segreti per risorsa l'isolamento del progetto unico basta per questo sistema. Si rivaluta prima dell'apertura al pubblico.
  - **Costi:** circa 0 €. Cloud Run scala a zero e la quota gratuita è condivisa con la produzione (per account di fatturazione), Supabase è Free e non ci sono Scheduler né NAT. I test di carico consumano un po' di quota: si eseguono in una finestra concordata. Il budget con avvisi copre entrambi gli ambienti.
- **Catena di fornitura (SR-076, THR-090 … THR-093):**
  - cooldown di 7 giorni sulle nuove versioni delle dipendenze: uv `exclude-newer` con durata relativa e pnpm `minimumReleaseAge`, con il supporto nelle versioni adottate da verificare (V-7);
  - script d'installazione npm bloccati, salvo un'allow-list;
  - immagini base fissate per digest;
  - scansioni bloccanti in CI: gitleaks, semgrep, pip-audit, `pnpm audit`, osv-scanner, trivy (`docs/06-threat-model.md` §11).
- **Igiene degli accessi del Gestore (SR-074):**
  - MFA resistente al phishing su Google Cloud, Supabase, GitHub, registrar e DNS;
  - credenziali operative mai in cache nell'ambiente dove si installano dipendenze o si esegue codice di terzi;
  - disco cifrato;
  - verifica annotata in `docs/09-release.md`.
- **Verifica di devops sull'IP del client (THR-012, V-3):** in staging, con una richiesta con `X-Forwarded-For` falsificato, si conferma quale voce aggiunge il Google Front End e che l'app registri l'IP reale (ADR-0006). Esito in `docs/09-release.md` prima di M0.
- **Uscite di riserva** (per esempio per ridurre la concentrazione su Google, R-05):
  - H5, Azure a Francoforte, con un monitor di uptime esterno gratuito;
  - H6, Scaleway, fornitore UE con qualche euro al mese nel caso peggiore.
  - Il codice non cambia: cambiano solo infrastruttura e configurazione (NFR-014).

## Dipendenze proprietarie (NFR-014), per H1
| Dipendenza | Impatto sul codice applicativo | Sostituto |
|---|---|---|
| Cloud Run (servizio e job) | Nessuno (container OCI, porta da `PORT`) | Container Apps, Scaleway, VPS |
| Cloud Scheduler | Nessuno (comandi CLI) | Jobs con cron, cron, systemd |
| Secret Manager | Nessuno (variabili d'ambiente). La console usa `CONSOLE_DB_URL_COMMAND` | Key Vault, Scaleway Secret Manager, file protetto |
| Cloud Logging e Monitoring | Nessuno (JSON su stdout, `/healthz`) | Log Analytics, Cockpit, monitor esterno |
| Cloud Storage | Solo lo script di backup | Qualunque storage a oggetti UE |
| Artifact Registry | Nessuno | Qualunque registry OCI |

## Conseguenze
- Positive: costo atteso tra 0 e 1 €/mese, osservabilità completa senza altri fornitori, codice portabile.
- Negative e costi: carta, configurazione iniziale, concentrazione su Google.
- Azioni successive:
  - il devops scrive `docs/09-release.md` (configurazione di Cloud Run, Scheduler, Secret Manager, bucket di log e backup in europe-west3, budget, runbook, rotazione dei segreti, checklist MFA);
  - l'utente crea il progetto e l'account di fatturazione con la carta;
  - l'utente accetta il DPA di Google Cloud prima di M1;
  - all'avvio, il devops verifica se europe-west3 rientra nella quota gratuita di Cloud Run;
  - staging (rev. 5): il devops descrive in `docs/09-release.md` i due environment GitHub, le due identità WIF, le risorse `*-staging`, il client OAuth di staging, il runbook "riattiva Supabase staging" e la verifica **V-8** (i progetti Free in pausa non contano nel limite di 2 progetti attivi, e per quanto tempo restano riattivabili);
  - l'utente crea il secondo progetto Supabase Free e il client OAuth di staging.

## Quando rivedere
- Se cambiano le quote gratuite o i costi superano 5 €/mese.
- Prima dell'apertura al pubblico.

## Fonti
- [Cloud Run, pricing](https://cloud.google.com/run/pricing)
- [Google Cloud Observability, pricing](https://cloud.google.com/monitoring/pricing)
- [Cloud Logging, conservazione dei log](https://docs.cloud.google.com/logging/docs/store-log-entries)
- [Azure Container Apps, pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/)
- [Azure Container Apps, fatturazione](https://learn.microsoft.com/en-us/azure/container-apps/billing)
- [Azure Monitor, pricing (ManageEngine)](https://www.manageengine.com/it-operations-management/blog/azure-monitor-pricing.html)
- [Scaleway Serverless, pricing](https://www.scaleway.com/en/pricing/serverless/)
- [Scaleway Serverless Containers, FAQ](https://www.scaleway.com/en/docs/serverless-containers/faq/)
- [Scaleway Serverless Jobs, FAQ](https://www.scaleway.com/en/docs/serverless-jobs/faq/)
- [Scaleway Cockpit, pricing](https://www.scaleway.com/en/docs/cockpit/reference-content/cockpit-pricing/)
- [Scaleway, pricing sicurezza e account](https://www.scaleway.com/en/pricing/security-and-account/)
- [Scaleway Object Storage, FAQ](https://scaleway.com/en/docs/faq/objectstorage)
- [Koyeb, FAQ prezzi](https://www.koyeb.com/docs/faq/pricing)
- [Koyeb, sintesi di un concorrente](https://snapdeploy.dev/koyeb-alternative)
- [Oracle, risorse Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm)
- [InfoQ, limiti del free tier Oracle 2026](https://infoq.com/news/2026/07/oracle-cloud-free-tier-limits/)
- [Analisi del free tier OCI](https://fullmetalbrackets.com/blog/oci-free-tier-breakdown)
- [Render, piani gratuiti 2026](https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026.md)
- [Render, pricing 2026 (temps.sh)](https://temps.sh/blog/render-pricing-2026)
- [Fly.io, storico prezzi](https://www.saaspricepulse.com/blog/flyio-pricing-history)
- [Northflank, free tier (agentdeals)](https://agentdeals.dev/vendor/northflank)
- [Confronto prezzi cloud, agosto 2026](https://kimmo.suominen.com/stuff/cpc-2026-08.txt)
- [Supabase, pricing (2 progetti Free attivi, pausa dopo una settimana)](https://supabase.com/pricing.md)
- [Neon vs Supabase, piani gratuiti (riattivazione dalla dashboard)](https://neon.com/guides/neon-vs-supabase-free-plan)
- [Guida al piano Free di Supabase (progetti in pausa fuori dal limite, fonte secondaria)](https://medium.com/@reliabledataengineering/making-the-most-of-supabases-free-tier-a-practical-guide-ef4817d84a26)
