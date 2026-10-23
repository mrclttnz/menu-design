// Registro dei messaggi (ADR-0010): fonte unica dei testi italiani, con ID espliciti da
// docs/03-ux.md §7.3. Non è importato dall'app: serve a `lingui extract`, che ne ricava il
// catalogo `it`. Il codice cita i messaggi per ID (`_("common.retry")`), anche quando l'ID viene da
// una mappa (src/api/errors.ts). Le chiavi senza voce UX sono marcate «da ratificare».
import { msg } from "@lingui/core/macro";

export const messages = {
  "common.save": msg({ id: "common.save", message: "Salva" }),
  "common.cancel": msg({ id: "common.cancel", message: "Annulla" }),
  "common.close": msg({ id: "common.close", message: "Chiudi" }),
  "common.back": msg({ id: "common.back", message: "Indietro" }),
  "common.retry": msg({ id: "common.retry", message: "Riprova" }),
  "common.confirm": msg({ id: "common.confirm", message: "Conferma" }),
  "common.edit": msg({ id: "common.edit", message: "Modifica" }),
  "common.delete": msg({ id: "common.delete", message: "Elimina" }),
  "common.add": msg({ id: "common.add", message: "Aggiungi" }),
  "common.remove": msg({ id: "common.remove", message: "Togli" }),
  "common.done": msg({ id: "common.done", message: "Fatto" }),
  "common.today": msg({ id: "common.today", message: "Oggi" }),
  "common.undo": msg({ id: "common.undo", message: "Annulla" }),
  "common.optional": msg({ id: "common.optional", message: "(facoltativo)" }),
  "common.required": msg({ id: "common.required", message: "(obbligatorio)" }),
  "common.loading": msg({ id: "common.loading", message: "Caricamento…" }),
  "common.loading.slow": msg({
    id: "common.loading.slow",
    message: "Ci sta mettendo più del solito…",
  }),
  "common.showMore": msg({ id: "common.showMore", message: "Mostra altri" }),
  "nav.label": msg({ id: "nav.label", message: "Navigazione principale" }),
  "nav.plan": msg({ id: "nav.plan", message: "Piano" }),
  "nav.dishes": msg({ id: "nav.dishes", message: "Piatti" }),
  "nav.more": msg({ id: "nav.more", message: "Altro" }),
  "nav.skipToContent": msg({ id: "nav.skipToContent", message: "Vai al contenuto" }),
  "role.admin": msg({ id: "role.admin", message: "Amministratore" }),
  "role.planner": msg({ id: "role.planner", message: "Pianificatore" }),
  "role.member": msg({ id: "role.member", message: "Membro" }),
  "role.admin.desc": msg({
    id: "role.admin.desc",
    message: "Gestisce la famiglia, le persone e tutto il piano.",
  }),
  "role.planner.desc": msg({
    id: "role.planner.desc",
    message: "Gestisce piatti e piano dei pasti, e le presenze di tutti.",
  }),
  "role.member.desc": msg({
    id: "role.member.desc",
    message:
      "Consulta il piano, segna le sue presenze, dice cosa gli piace e propone piatti da provare.",
  }),
  "account.menu": msg({ id: "account.menu", message: "Account di {name}" }),
  "account.signedInAs": msg({
    id: "account.signedInAs",
    message: "Hai effettuato l'accesso come {name}",
  }),
  "account.logout": msg({ id: "account.logout", message: "Esci" }),
  "auth.loggedOut": msg({ id: "auth.loggedOut", message: "Hai effettuato l'uscita." }),
  "auth.login.title": msg({ id: "auth.login.title", message: "Accedi a Menu Design" }),
  "auth.login.subtitle": msg({
    id: "auth.login.subtitle",
    message: "Il piano dei pasti della tua famiglia, sempre in tasca.",
  }),
  "auth.login.google": msg({ id: "auth.login.google", message: "Continua con Google" }),
  "auth.login.inProgress": msg({ id: "auth.login.inProgress", message: "Accesso in corso…" }),
  "auth.cancelled": msg({
    id: "auth.cancelled",
    message: "Accesso annullato. Puoi riprovare quando vuoi.",
  }),
  "auth.failed": msg({
    id: "auth.failed",
    message: "Non siamo riusciti a completare l'accesso. Riprova.",
  }),
  "auth.sessionExpired": msg({
    id: "auth.sessionExpired",
    message: "La sessione è scaduta. Accedi di nuovo per continuare.",
  }),
  "auth.noFamily.title": msg({ id: "auth.noFamily.title", message: "Serve un invito" }),
  "auth.noFamily.body": msg({
    id: "auth.noFamily.body",
    message:
      "Questo account Google non fa ancora parte di una famiglia. Chiedi a chi gestisce la tua famiglia di mandarti un link di invito.",
  }),
  "auth.noFamily.switch": msg({
    id: "auth.noFamily.switch",
    message: "Usa un altro account Google",
  }),
  "auth.removed.title": msg({
    id: "auth.removed.title",
    message: "Non fai più parte di questa famiglia",
  }),
  "auth.removed.body": msg({
    id: "auth.removed.body",
    message: "Se pensi sia un errore, chiedi a un Amministratore di invitarti di nuovo.",
  }),
  "error.generic": msg({
    id: "error.generic",
    message: "Qualcosa non ha funzionato. Riprova tra poco.",
  }),
  "error.network": msg({
    id: "error.network",
    message: "Non riesco a collegarmi. Controlla la connessione e riprova.",
  }),
  "error.notFound": msg({
    id: "error.notFound",
    message: "Non troviamo quello che cerchi. Potrebbe essere stato eliminato.",
  }),
  "error.forbidden": msg({
    id: "error.forbidden",
    message: "Non hai il permesso di fare questa operazione.",
  }),
  "error.reauth": msg({
    id: "error.reauth",
    message: "Per sicurezza, accedi di nuovo per continuare.",
  }),
  "error.rateLimited": msg({
    id: "error.rateLimited",
    message: "Troppi tentativi. Riprova tra {seconds, plural, one {# secondo} other {# secondi}}.",
  }),
  "error.sessionExpired": msg({
    id: "error.sessionExpired",
    message: "La sessione è scaduta. Accedi di nuovo per continuare.",
  }),
  "error.familyPendingDeletion": msg({
    id: "error.familyPendingDeletion",
    message: "La famiglia è in sola lettura: verrà eliminata il {date}.",
  }),
  "error.inviteInvalid": msg({
    id: "error.inviteInvalid",
    message: "Questo invito non è valido o è scaduto. Chiedi di mandartene uno nuovo.",
  }),
  "validation.required": msg({ id: "validation.required", message: "Compila questo campo." }),
  "validation.string_too_long": msg({
    id: "validation.string_too_long",
    message: "Massimo {max} caratteri.",
  }),
  "validation.course_required": msg({
    id: "validation.course_required",
    message: "Scegli almeno una portata.",
  }),
  "validation.url_invalid": msg({
    id: "validation.url_invalid",
    message: "Inserisci un indirizzo che inizi con http:// o https://.",
  }),
  "validation.limit_reached": msg({
    id: "validation.limit_reached",
    message: "Hai raggiunto il limite di {max}.",
  }),
  "validation.guests_range": msg({
    id: "validation.guests_range",
    message: "Inserisci un numero da 0 a 50.",
  }),
  "validation.date_invalid": msg({
    id: "validation.date_invalid",
    message: "Inserisci una data valida.",
  }),
  "validation.range_order": msg({
    id: "validation.range_order",
    message: "La data finale deve essere dopo quella iniziale.",
  }),
  "error.range_too_large": msg({
    id: "error.range_too_large",
    message: "Scegli al massimo {maxDays} giorni.",
  }),
  "validation.duplicate_course": msg({
    id: "validation.duplicate_course",
    message: "Esiste già una portata con questo nome.",
  }),
  "validation.invalid_value": msg({
    id: "validation.invalid_value",
    message:
      "Questo valore non è valido. Controllalo e riprova. Se il problema resta, ricarica la pagina.",
  }),
  "validation.unknown_field": msg({
    id: "validation.unknown_field",
    message: "Qualcosa non è andato come previsto. Ricarica la pagina e riprova.",
  }),
  "error.course_in_use": msg({
    id: "error.course_in_use",
    message:
      "{usageCount, plural, one {Questa portata è usata da 1 piatto, quindi non si può eliminare. Cambia prima la portata di quel piatto.} other {Questa portata è usata da # piatti, quindi non si può eliminare. Cambia prima la portata di quei piatti.}}",
  }),
  "error.dish_not_planned": msg({
    id: "error.dish_not_planned",
    message:
      "Questo piatto non è mai stato pianificato, quindi non si può archiviare. Se non ti serve più, eliminalo.",
  }),
  "validation.dish_archived": msg({
    id: "validation.dish_archived",
    message:
      "Questo piatto è archiviato e non si può aggiungere. Scegline un altro o ripristinalo dalla scheda.",
  }),
  "validation.dish_archived.noRestore": msg({
    id: "validation.dish_archived.noRestore",
    message: "Questo piatto è archiviato e non si può aggiungere. Scegline un altro.",
  }),
  "error.reauth_wrong_account": msg({
    id: "error.reauth_wrong_account",
    message:
      "Hai usato un account Google diverso da quello con cui sei collegato. Accedi con {expectedEmailMasked}.",
  }),
  "accept.invalid": msg({
    id: "accept.invalid",
    message: "Questo invito non è valido o è scaduto. Chiedi di mandartene uno nuovo.",
  }),
  "code.invalid": msg({ id: "code.invalid", message: "Questo codice non è valido o è scaduto." }),
  "accept.alreadyInFamily": msg({
    id: "accept.alreadyInFamily",
    message:
      "Fai già parte di una famiglia. In questa versione ogni account può far parte di una sola famiglia, quindi non puoi entrare con questo invito. L'invito non è stato usato.",
  }),
  "people.lastAdmin.blocked": msg({
    id: "people.lastAdmin.blocked",
    message:
      "Una famiglia deve avere sempre un Amministratore, e al momento sei l'unico. Per ora non puoi uscire.",
  }),
  "dish.deleteBlocked": msg({
    id: "dish.deleteBlocked",
    message:
      "Nel frattempo questo piatto è stato aggiunto a un pasto, quindi non si può eliminare. Puoi archiviarlo.",
  }),
  "picker.courseChoice": msg({ id: "picker.courseChoice", message: "Come lo servi?" }),
  "presence.beforeJoin": msg({
    id: "presence.beforeJoin",
    message: "Non facevi ancora parte della famiglia in questo giorno.",
  }),
  "invite.limit": msg({
    id: "invite.limit",
    message: "Hai già {max} inviti in sospeso. Revocane uno per crearne un altro.",
  }),
  "accept.under14.body": msg({
    id: "accept.under14.body",
    message:
      "Se hai meno di 14 anni non puoi avere un account. Un adulto della tua famiglia può aggiungerti come profilo senza account, così le tue presenze e i tuoi gusti contano comunque. L'invito resta valido.",
  }),
  "error.quota_exceeded.other_meals_per_day": msg({
    id: "error.quota_exceeded.other_meals_per_day",
    message:
      "Puoi avere al massimo {limit} «Altro pasto» al giorno. Togline uno per aggiungerne un altro.",
  }),
  "validation.priority_range": msg({
    id: "validation.priority_range",
    message: "Scegli un numero da 1 a 10.",
  }),
  "error.save": msg({
    id: "error.save",
    message: "Non siamo riusciti a salvare. Controlla la connessione e riprova.",
  }),
  "conflict.title.meal": msg({
    id: "conflict.title.meal",
    message: "Qualcuno ha modificato questo pasto",
  }),
  "app.name": msg({ id: "app.name", message: "Menu Design" }),
  "app.documentTitle": msg({ id: "app.documentTitle", message: "{title} · {app}" }),
  "error.notFound.title": msg({ id: "error.notFound.title", message: "Pagina non trovata" }),
  "error.notFound.back": msg({ id: "error.notFound.back", message: "Vai alla pagina di accesso" }),
  "conflict.title.generic": msg({
    id: "conflict.title.generic",
    message: "Qualcuno ha modificato questi dati",
  }),
} as const;

export type MessageId = keyof typeof messages;
