"""Base de données SQLite : un simple fichier (data/radar.db) qui garde la mémoire du robot."""
import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS offres (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_source TEXT UNIQUE, cle_doublon TEXT, source TEXT,
    societe TEXT, titre TEXT, lieu TEXT, url TEXT, urls_alt TEXT DEFAULT '',
    description TEXT, date_publication TEXT,
    premiere_detection TEXT, derniere_vue TEXT, derniere_modif TEXT,
    hash TEXT, actif INTEGER DEFAULT 1, republiee INTEGER DEFAULT 0,
    score INTEGER, retenue INTEGER, categorie TEXT, classe_actifs TEXT, ville TEXT,
    debut TEXT, statut_date TEXT, rejet TEXT, raisons TEXT, alertes TEXT,
    notifiee INTEGER DEFAULT 0, lien_ok INTEGER,
    statut_candidature TEXT DEFAULT 'À postuler'
);
CREATE INDEX IF NOT EXISTS idx_cle ON offres(cle_doublon);
CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT, date_envoi TEXT, type TEXT,
    objet TEXT, nb_offres INTEGER, ok INTEGER, erreur TEXT
);
CREATE TABLE IF NOT EXISTS verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, date_verif TEXT, statut TEXT,
    nb_lues INTEGER, nb_nouvelles INTEGER, nb_republiees INTEGER, nb_modifiees INTEGER, erreurs TEXT
);
"""


def maintenant():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def ouvrir(chemin):
    conn = sqlite3.connect(str(chemin))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _norm(texte):
    texte = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", texte.lower()).strip()


def cle_doublon(offre):
    """Deux annonces de même société et de même titre sont considérées comme la même offre,
    même si elles viennent de deux sources différentes."""
    return f"{_norm(offre.get('societe'))}|{_norm(offre.get('titre'))}"


def _hash(offre):
    brut = f"{_norm(offre.get('titre'))}|{_norm(offre.get('lieu'))}|{_norm(offre.get('description'))}"
    return hashlib.sha1(brut.encode()).hexdigest()


def _champs_analyse(a):
    return (a["score"], int(a["retenue"]), a["categorie"], a["classe_actifs"], a["ville"], a["debut"],
            a["statut_date"], a["rejet"], json.dumps(a["raisons"], ensure_ascii=False),
            json.dumps(a["alertes"], ensure_ascii=False))


def enregistrer_offre(conn, offre, source, analyse, now):
    """Enregistre une offre. Renvoie : 'nouvelle', 'republiee', 'modifiee', 'doublon' ou 'inchangee'."""
    h, cle = _hash(offre), cle_doublon(offre)
    ca = _champs_analyse(analyse)
    row = conn.execute("SELECT * FROM offres WHERE id_source=?", (offre["id_source"],)).fetchone()
    if row is None:
        autre = conn.execute("SELECT * FROM offres WHERE cle_doublon=? ORDER BY id LIMIT 1", (cle,)).fetchone()
        if autre is not None:  # même offre, autre adresse / autre source
            alt = autre["urls_alt"] or ""
            if offre["url"] and offre["url"] != autre["url"] and offre["url"] not in alt:
                alt = (alt + " " + offre["url"]).strip()
            if not autre["actif"]:  # l'offre réapparaît : republication
                conn.execute("UPDATE offres SET actif=1, republiee=republiee+1, notifiee=0, derniere_vue=?, urls_alt=? WHERE id=?",
                             (now, alt, autre["id"]))
                return "republiee"
            conn.execute("UPDATE offres SET derniere_vue=?, urls_alt=? WHERE id=?", (now, alt, autre["id"]))
            return "doublon"
        conn.execute(
            """INSERT INTO offres (id_source, cle_doublon, source, societe, titre, lieu, url, description,
               date_publication, premiere_detection, derniere_vue, derniere_modif, hash,
               score, retenue, categorie, classe_actifs, ville, debut, statut_date, rejet, raisons, alertes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (offre["id_source"], cle, source, offre["societe"], offre["titre"], offre["lieu"], offre["url"],
             offre["description"], offre["date_publication"], now, now, now, h) + ca)
        return "nouvelle"
    statut = "inchangee"
    if not row["actif"]:
        statut = "republiee"
        conn.execute("UPDATE offres SET actif=1, republiee=republiee+1, notifiee=0 WHERE id=?", (row["id"],))
    elif row["hash"] != h:
        statut = "modifiee"
        conn.execute("UPDATE offres SET derniere_modif=? WHERE id=?", (now, row["id"]))
    conn.execute(
        """UPDATE offres SET derniere_vue=?, hash=?, titre=?, lieu=?, url=?, description=?, date_publication=?,
           score=?, retenue=?, categorie=?, classe_actifs=?, ville=?, debut=?, statut_date=?, rejet=?, raisons=?, alertes=?
           WHERE id=?""",
        (now, h, offre["titre"], offre["lieu"], offre["url"], offre["description"], offre["date_publication"]) + ca + (row["id"],))
    return statut


def marquer_disparues(conn, source, now):
    """Les offres de cette source qu'on n'a pas revues pendant cette vérification passent 'inactives'."""
    conn.execute("UPDATE offres SET actif=0 WHERE source=? AND actif=1 AND derniere_vue < ?", (source, now))


def offres_a_notifier(conn):
    return conn.execute(
        "SELECT * FROM offres WHERE retenue=1 AND notifiee=0 AND actif=1 AND (lien_ok IS NULL OR lien_ok=1) ORDER BY score DESC"
    ).fetchall()


def marquer_notifiees(conn, ids):
    conn.executemany("UPDATE offres SET notifiee=1 WHERE id=?", [(i,) for i in ids])


def journaliser_email(conn, type_, objet, nb, ok, erreur=""):
    conn.execute("INSERT INTO emails (date_envoi, type, objet, nb_offres, ok, erreur) VALUES (?,?,?,?,?,?)",
                 (maintenant(), type_, objet, nb, int(ok), erreur))


def journaliser_verification(conn, now, statut, lues, nouvelles, republiees, modifiees, erreurs):
    conn.execute(
        "INSERT INTO verifications (date_verif, statut, nb_lues, nb_nouvelles, nb_republiees, nb_modifiees, erreurs) VALUES (?,?,?,?,?,?,?)",
        (now, statut, lues, nouvelles, republiees, modifiees, "; ".join(erreurs)))
