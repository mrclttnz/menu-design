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
  "dishes.title": msg({ id: "dishes.title", message: "Piatti" }),
  "dishes.new": msg({ id: "dishes.new", message: "Nuovo piatto" }),
  "dishes.search": msg({ id: "dishes.search", message: "Cerca per nome" }),
  "dishes.filter.status": msg({ id: "dishes.filter.status", message: "Stato" }),
  "dishes.filter.archived": msg({ id: "dishes.filter.archived", message: "Mostra archiviati" }),
  "dishes.empty.title": msg({ id: "dishes.empty.title", message: "Il tuo archivio è vuoto" }),
  "dishes.empty.body": msg({
    id: "dishes.empty.body",
    message: "Aggiungi i piatti che cucinate e quelli che vorreste provare.",
  }),
  "dishes.empty.cta": msg({ id: "dishes.empty.cta", message: "Aggiungi il primo piatto" }),
  "dishes.noResults": msg({ id: "dishes.noResults", message: "Nessun piatto trovato" }),
  "dishes.error.load": msg({
    id: "dishes.error.load",
    message: "Non riusciamo a caricare i piatti. Riprova.",
  }),
  "dish.course.first": msg({ id: "dish.course.first", message: "Primo" }),
  "dish.course.second": msg({ id: "dish.course.second", message: "Secondo" }),
  "dish.course.side": msg({ id: "dish.course.side", message: "Contorno" }),
  "dish.course.single": msg({ id: "dish.course.single", message: "Piatto unico" }),
  "dish.course.starter": msg({ id: "dish.course.starter", message: "Antipasto" }),
  "dish.course.dessert": msg({ id: "dish.course.dessert", message: "Dolce" }),
  "dish.course.drink": msg({ id: "dish.course.drink", message: "Bevanda" }),
  "dish.course.other": msg({ id: "dish.course.other", message: "Altro" }),
  "dish.status.toTry": msg({ id: "dish.status.toTry", message: "Da provare" }),
  "dish.status.tested": msg({ id: "dish.status.tested", message: "Collaudato" }),
  "dish.status.archived": msg({ id: "dish.status.archived", message: "Archiviato" }),
  "dish.status.markTested": msg({ id: "dish.status.markTested", message: "Segna come collaudato" }),
  "dish.status.markToTry": msg({ id: "dish.status.markToTry", message: "Riporta a «da provare»" }),
  "dish.status.changed.toast": msg({
    id: "dish.status.changed.toast",
    message: "{name} è ora {status}",
  }),
  "dish.status.memberLocked": msg({
    id: "dish.status.memberLocked",
    message: "Come Membro puoi proporre solo piatti da provare.",
  }),
  "dish.time.label": msg({ id: "dish.time.label", message: "Tempo di preparazione" }),
  "dish.time.under30": msg({ id: "dish.time.under30", message: "Meno di 30 minuti" }),
  "dish.time.30to60": msg({ id: "dish.time.30to60", message: "30-60 minuti" }),
  "dish.time.over60": msg({ id: "dish.time.over60", message: "Più di 60 minuti" }),
  "dish.time.none": msg({ id: "dish.time.none", message: "Non indicato" }),
  "dish.field.name": msg({ id: "dish.field.name", message: "Nome del piatto" }),
  "dish.field.courses": msg({ id: "dish.field.courses", message: "Portate" }),
  "dish.field.courses.hint": msg({
    id: "dish.field.courses.hint",
    message: "Scegli almeno una portata.",
  }),
  "dish.field.status": msg({ id: "dish.field.status", message: "Stato" }),
  "dish.field.notes": msg({ id: "dish.field.notes", message: "Note" }),
  "dish.field.notes.hint": msg({
    id: "dish.field.notes.hint",
    message: "Non scrivere informazioni sulla salute di nessuno (per esempio allergie).",
  }),
  "dish.lastCooked": msg({
    id: "dish.lastCooked",
    message: "Cucinato {n, plural, one {1 giorno fa} other {# giorni fa}} ({date})",
  }),
  "dish.neverCooked": msg({ id: "dish.neverCooked", message: "Mai cucinato" }),
  "dish.sources.title": msg({ id: "dish.sources.title", message: "Dove trovi la ricetta" }),
  "dish.source.type.link": msg({ id: "dish.source.type.link", message: "Link" }),
  "dish.source.type.book": msg({ id: "dish.source.type.book", message: "Libro" }),
  "dish.source.type.magazine": msg({ id: "dish.source.type.magazine", message: "Rivista" }),
  "dish.source.type.other": msg({ id: "dish.source.type.other", message: "Altro" }),
  "dish.source.url": msg({ id: "dish.source.url", message: "Indirizzo (https://…)" }),
  "dish.source.bookTitle": msg({ id: "dish.source.bookTitle", message: "Titolo" }),
  "dish.source.page": msg({ id: "dish.source.page", message: "Pagina" }),
  "dish.source.text": msg({ id: "dish.source.text", message: "Descrizione" }),
  "dish.source.note": msg({ id: "dish.source.note", message: "Nota" }),
  "dish.source.add": msg({ id: "dish.source.add", message: "Aggiungi una fonte" }),
  "dish.source.remove": msg({ id: "dish.source.remove", message: "Togli questa fonte" }),
  "dish.source.open": msg({
    id: "dish.source.open",
    message: "Apri la ricetta (si apre in una nuova scheda)",
  }),
  "dish.source.limit": msg({
    id: "dish.source.limit",
    message: "Hai raggiunto il massimo di {max} fonti.",
  }),
  "dish.saved.toast": msg({ id: "dish.saved.toast", message: "Piatto salvato" }),
  "dish.archive": msg({ id: "dish.archive", message: "Archivia" }),
  "dish.archive.confirm.title": msg({
    id: "dish.archive.confirm.title",
    message: "Archiviare «{name}»?",
  }),
  "dish.archive.confirm.body": msg({
    id: "dish.archive.confirm.body",
    message:
      "Non comparirà più tra le scelte, ma resterà visibile nei piani passati. Potrai ripristinarlo quando vuoi.",
  }),
  "dish.restore": msg({ id: "dish.restore", message: "Ripristina" }),
  "dish.delete.confirm.title": msg({
    id: "dish.delete.confirm.title",
    message: "Eliminare «{name}»?",
  }),
  "dish.delete.confirm.body": msg({
    id: "dish.delete.confirm.body",
    message: "Non è mai stato pianificato, quindi verrà eliminato per sempre.",
  }),
  "dish.archivedBanner": msg({
    id: "dish.archivedBanner",
    message: "Questo piatto è archiviato e non compare più tra le scelte.",
  }),
  "form.discard.title": msg({ id: "form.discard.title", message: "Uscire senza salvare?" }),
  "form.discard.body": msg({
    id: "form.discard.body",
    message: "Le modifiche che hai fatto andranno perse.",
  }),
  "form.discard.confirm": msg({ id: "form.discard.confirm", message: "Esci senza salvare" }),
  "form.errorSummary": msg({
    id: "form.errorSummary",
    message: "Controlla questi campi prima di salvare",
  }),
  // Voci di SL-04: sezione Piatti e selettore.
  "picker.create": msg({ id: "picker.create", message: "Crea il piatto «{text}»" }),
  "dishes.back": msg({ id: "dishes.back", message: "Torna ai piatti" }),
  "dishes.filter.allCourses": msg({ id: "dishes.filter.allCourses", message: "Tutte le portate" }),
  "dishes.filter.allStatuses": msg({ id: "dishes.filter.allStatuses", message: "Tutti gli stati" }),
  "dish.source.type": msg({ id: "dish.source.type", message: "Tipo" }),
  "dish.source.n": msg({ id: "dish.source.n", message: "Fonte {n}" }),
  "form.discard.keep": msg({ id: "form.discard.keep", message: "Continua a modificare" }),
  "plan.title": msg({ id: "plan.title", message: "Piano" }),
  "plan.range": msg({ id: "plan.range", message: "{start} - {end}" }),
  "plan.nav.prev": msg({ id: "plan.nav.prev", message: "Settimana precedente" }),
  "plan.nav.next": msg({ id: "plan.nav.next", message: "Settimana successiva" }),
  "plan.menu.otherRange": msg({
    id: "plan.menu.otherRange",
    message: "Mostra un altro intervallo…",
  }),
  "plan.day.menu": msg({ id: "plan.day.menu", message: "Azioni per {day}" }),
  "plan.day.addMeal": msg({ id: "plan.day.addMeal", message: "Aggiungi un pasto" }),
  "plan.day.past": msg({ id: "plan.day.past", message: "Passato" }),
  "plan.day.today": msg({ id: "plan.day.today", message: "Oggi" }),
  "plan.meal.add": msg({ id: "plan.meal.add", message: "Aggiungi piatto" }),
  "plan.meal.nothing": msg({ id: "plan.meal.nothing", message: "Ancora niente" }),
  "plan.meal.aria": msg({
    id: "plan.meal.aria",
    message: "{meal} di {date}: {summary}. Apri il pasto",
  }),
  "plan.empty.noMeals.title": msg({
    id: "plan.empty.noMeals.title",
    message: "Nessun pasto da pianificare",
  }),
  "plan.empty.noMeals.body": msg({
    id: "plan.empty.noMeals.body",
    message: "Scegli quali pasti compaiono ogni giorno, oppure aggiungine uno a un giorno.",
  }),
  "plan.empty.noMeals.cta1": msg({
    id: "plan.empty.noMeals.cta1",
    message: "Scegli i pasti di ogni giorno",
  }),
  "plan.empty.noMeals.cta2": msg({
    id: "plan.empty.noMeals.cta2",
    message: "Aggiungi un pasto a un giorno",
  }),
  "plan.empty.notReady.title": msg({
    id: "plan.empty.notReady.title",
    message: "Il piano non è ancora pronto",
  }),
  "plan.empty.notReady.body": msg({
    id: "plan.empty.notReady.body",
    message: "Chi pianifica non ha ancora inserito i pasti di questa settimana.",
  }),
  "plan.error.load": msg({
    id: "plan.error.load",
    message: "Non riusciamo a caricare il piano. Controlla la connessione e riprova.",
  }),
  "plan.dayChanged.toast": msg({
    id: "plan.dayChanged.toast",
    message: "È cambiato il giorno: il piano è stato aggiornato.",
  }),
  "plan.range.title": msg({ id: "plan.range.title", message: "Scegli un intervallo" }),
  "plan.range.from": msg({ id: "plan.range.from", message: "Dal" }),
  "plan.range.to": msg({ id: "plan.range.to", message: "Al" }),
  "plan.range.show": msg({ id: "plan.range.show", message: "Mostra" }),
  "plan.range.thisWeek": msg({ id: "plan.range.thisWeek", message: "Questa settimana" }),
  "plan.range.nextTwo": msg({ id: "plan.range.nextTwo", message: "Prossime 2 settimane" }),
  "meal.type.breakfast": msg({ id: "meal.type.breakfast", message: "Colazione" }),
  "meal.type.lunch": msg({ id: "meal.type.lunch", message: "Pranzo" }),
  "meal.type.snack": msg({ id: "meal.type.snack", message: "Merenda" }),
  "meal.type.dinner": msg({ id: "meal.type.dinner", message: "Cena" }),
  "meal.type.other": msg({ id: "meal.type.other", message: "Altro pasto" }),
  "meal.add.title": msg({ id: "meal.add.title", message: "Aggiungi un pasto" }),
  "meal.special.normal": msg({ id: "meal.special.normal", message: "Normale" }),
  "meal.special.out": msg({ id: "meal.special.out", message: "Fuori casa" }),
  "meal.special.restaurant": msg({ id: "meal.special.restaurant", message: "Ristorante" }),
  "meal.special.skipped": msg({ id: "meal.special.skipped", message: "Saltato" }),
  "meal.section.items": msg({ id: "meal.section.items", message: "Piatti e voci" }),
  "meal.section.type": msg({ id: "meal.section.type", message: "Tipo di pasto" }),
  "meal.empty": msg({ id: "meal.empty", message: "Ancora niente in questo pasto" }),
  "meal.add": msg({ id: "meal.add", message: "Aggiungi piatto o voce" }),
  "meal.past.banner": msg({
    id: "meal.past.banner",
    message:
      "Stai correggendo un pasto passato. Le modifiche cambiano anche «cucinato N giorni fa».",
  }),
  "meal.freeText.label": msg({ id: "meal.freeText.label", message: "Voce libera" }),
  "meal.item.archived": msg({ id: "meal.item.archived", message: "Archiviato" }),
  "meal.item.notCooked": msg({ id: "meal.item.notCooked", message: "Non cucinato" }),
  "meal.item.moveUp": msg({ id: "meal.item.moveUp", message: "Sposta su" }),
  "meal.item.moveDown": msg({ id: "meal.item.moveDown", message: "Sposta giù" }),
  "meal.item.changeCourse": msg({ id: "meal.item.changeCourse", message: "Cambia portata" }),
  "meal.item.markNotCooked": msg({
    id: "meal.item.markNotCooked",
    message: "Segna come non cucinato",
  }),
  "meal.item.markCooked": msg({ id: "meal.item.markCooked", message: "Segna come cucinato" }),
  "meal.item.saveToArchive": msg({ id: "meal.item.saveToArchive", message: "Salva tra i piatti" }),
  "meal.item.remove": msg({ id: "meal.item.remove", message: "Togli {name} dal pasto" }),
  "meal.added.toast": msg({ id: "meal.added.toast", message: "Aggiunto {name}" }),
  "meal.removed.toast": msg({ id: "meal.removed.toast", message: "Tolto {name}" }),
  "meal.typeChanged.toast": msg({
    id: "meal.typeChanged.toast",
    message: "Pasto segnato come {type}",
  }),
  "meal.limit": msg({ id: "meal.limit", message: "Un pasto può avere al massimo {max} voci." }),
  "meal.removeFromDay": msg({
    id: "meal.removeFromDay",
    message: "Togli questo pasto da questo giorno",
  }),
  // Chiavi di SL-06a senza voce in docs/03-ux.md §7.3: da ratificare dalla UX.
  "plan.menu.week": msg({ id: "plan.menu.week", message: "Menu della settimana" }),
  "plan.back": msg({ id: "plan.back", message: "Torna al piano" }),
  "meal.menu": msg({ id: "meal.menu", message: "Menu del pasto" }),
  "meal.heading": msg({ id: "meal.heading", message: "{meal} · {date}" }),
} as const;

export type MessageId = keyof typeof messages;
