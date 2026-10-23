"""Controllo d'inventario degli `ExportContributor` (plan §2.2, OBJ-02; 08 §6.8).

Funzione pura: confronta le tabelle di famiglia del catalogo con quelle dichiarate dai
contributori. La sua capacità di fallire è provata con dati sintetici in `tests/unit`.
"""

from collections.abc import Iterable, Mapping

# Tabelle di famiglia deliberatamente NON esportate, con il motivo (elenco chiuso, 08 §6.8).
# Ogni voce nuova va giustificata con `docs/05-data.md` §9.3 e rivista dal tester.
NOT_EXPORTED: dict[str, str] = {
    "family_bootstrap": "dato operativo del Gestore (hash dell'email), non contenuto della "
    "famiglia: assente dal perimetro di 05-data §9.3",
}

# Tabelle NON di famiglia che un contributore può dichiarare perché entrano nel perimetro `self`
# (05-data §9.3: «la propria riga `account`, le proprie sessioni»). Le dichiara `identity` (SL-03a)
# e solo `identity`; nel perimetro `family` non producono mai righe.
NON_FAMILY_EXPORTED = frozenset({"account", "session"})

# Colonne mai ammesse nell'output dei due perimetri (05-data §9.3, SR-072, plan §2.2).
FORBIDDEN_EXPORT_COLUMNS = frozenset(
    {
        "email",
        "email_sha256",
        "last_visit_at",
        "dish_sort_preference",
        "last_active_on",
        "auth_subject",
        "age_declared_at",
        "privacy_version",
        "privacy_ack_at",
        "ip",
        "ip_prefix",
        "token_hash",
        "csrf_token_hash",
        "session_id",
    }
)


def export_inventory_problems(
    contributors: Mapping[str, Iterable[str]],
    family_tables: Iterable[str],
    not_exported: Mapping[str, str] = NOT_EXPORTED,
    non_family_exported: Iterable[str] = NON_FAMILY_EXPORTED,
) -> list[str]:
    """`contributors`: nome del contributore -> tabelle dichiarate."""
    problems: list[str] = []
    claims: dict[str, list[str]] = {}
    for name, tables in contributors.items():
        for table in tables:
            claims.setdefault(table, []).append(name)
    expected = set(family_tables)
    for table in sorted(expected):
        owners = claims.get(table, [])
        if table in not_exported:
            if owners:
                problems.append(f"{table}: esclusa dall'export ma dichiarata da {sorted(owners)}")
        elif not owners:
            problems.append(f"{table}: tabella di famiglia senza ExportContributor")
        elif len(owners) > 1:
            problems.append(f"{table}: dichiarata da più contributori {sorted(owners)}")
    allowed_extra = set(non_family_exported)
    for table in sorted(set(claims) - expected):
        if table in allowed_extra:
            if len(claims[table]) > 1:
                problems.append(f"{table}: dichiarata da più contributori {sorted(claims[table])}")
            continue
        problems.append(f"{table}: dichiarata da {sorted(claims[table])} ma non è di famiglia")
    for table in sorted(set(not_exported) - expected):
        problems.append(f"{table}: voce di NOT_EXPORTED senza tabella di famiglia")
    return problems


def forbidden_columns_in(payload: Mapping[str, list[dict[str, object]]]) -> list[str]:
    found = []
    for table, rows in payload.items():
        for row in rows:
            for col in row:
                if col in FORBIDDEN_EXPORT_COLUMNS:
                    found.append(f"{table}.{col}")
    return sorted(set(found))
