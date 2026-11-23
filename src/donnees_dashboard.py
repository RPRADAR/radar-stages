"""Données du tableau de bord : téléchargement de la base du robot, lecture, statuts de candidature."""
import csv
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from zoneinfo import ZoneInfo
    FUSEAU = ZoneInfo("Europe/Paris")
except Exception:
    FUSEAU = timezone.utc

RACINE = Path(__file__).resolve().parent.parent
DEPOT_GITHUB = os.environ.get("DEPOT_GITHUB", "RPRADAR/radar-stages")   # compte/dépôt
CHEMIN_BASE = RACINE / "data" / "radar_telechargee.db"
CHEMIN_STATUTS = RACINE / "data" / "candidatures.csv"
CHEMIN_PREFS = RACINE / "data" / "preferences_tableau.json"
STATUTS = ["À postuler", "Candidature envoyée", "Refus", "Entretien", "Accepté"]


def telecharger_base(depot=DEPOT_GITHUB, destination=CHEMIN_BASE):
    """Télécharge la dernière base du robot depuis GitHub (dépôt public). Renvoie (ok, message)."""
    url = f"https://raw.githubusercontent.com/{depot}/main/data/radar.db"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 404:
            return False, "Base introuvable sur GitHub : le robot n'a peut-être pas encore tourné."
        r.raise_for_status()
        Path(destination).write_bytes(r.content)
        return True, "Base mise à jour."
    except Exception as e:
        return False, f"Téléchargement impossible : {e}"


def _heure_locale(iso):
    try:
        dt = datetime.strptime(iso[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.astimezone(FUSEAU).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso or ""


def _date_fr(iso):
    try:
        return datetime.strptime((iso or "")[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return ""


def charger_statuts(chemin=CHEMIN_STATUTS):
    chemin = Path(chemin)
    if not chemin.exists():
        return {}
    with open(chemin, encoding="utf-8-sig", newline="") as f:
        return {l["id_source"]: l["statut"] for l in csv.DictReader(f) if l.get("statut") in STATUTS}


def sauver_statuts(statuts, chemin=CHEMIN_STATUTS):
    with open(chemin, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id_source", "statut"])
        for k, v in sorted(statuts.items()):
            if v != STATUTS[0]:          # "À postuler" est le statut par défaut : inutile de le stocker
                w.writerow([k, v])


def charger_offres(chemin_base=CHEMIN_BASE, chemin_statuts=CHEMIN_STATUTS, inclure_inactives=False, inclure_rejetees=False):
    """Renvoie la liste des offres (dictionnaires), prêtes à être affichées."""
    conn = sqlite3.connect(str(chemin_base))
    conn.row_factory = sqlite3.Row
    requete = "SELECT * FROM offres WHERE 1=1"
    if not inclure_rejetees:
        requete += " AND retenue=1"
    if not inclure_inactives:
        requete += " AND actif=1"
    lignes = conn.execute(requete).fetchall()
    conn.close()
    statuts = charger_statuts(chemin_statuts)
    offres = []
    for r in lignes:
        alertes = json.loads(r["alertes"] or "[]")
        offres.append({
            "id": r["id_source"], "Score": r["score"], "Entreprise": r["societe"], "Poste": r["titre"],
            "Ville": r["ville"], "Catégorie": r["categorie"] or "", "Classe d'actifs": r["classe_actifs"],
            "Début": r["debut"] or "À vérifier", "Publication": _date_fr(r["date_publication"]),
            "Détectée le": _heure_locale(r["premiere_detection"]), "_tri_detection": r["premiere_detection"] or "",
            "Statut": statuts.get(r["id_source"], STATUTS[0]), "Lien": r["url"],
            "Actif": "oui" if r["actif"] else "non (disparue)", "Republiée": r["republiee"],
            "À vérifier": " ".join(alertes),
        })
    return offres


def etat_robot(chemin_base=CHEMIN_BASE):
    """Dernière vérification du robot et derniers emails envoyés."""
    conn = sqlite3.connect(str(chemin_base))
    conn.row_factory = sqlite3.Row
    v = conn.execute("SELECT * FROM verifications ORDER BY id DESC LIMIT 1").fetchone()
    emails = conn.execute("SELECT date_envoi, type, objet, nb_offres, ok FROM emails ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    derniere = None
    if v:
        derniere = {"date": _heure_locale(v["date_verif"]), "statut": v["statut"], "lues": v["nb_lues"],
                    "nouvelles": v["nb_nouvelles"], "erreurs": v["erreurs"]}
    historique = [{"Date": _heure_locale(e["date_envoi"]), "Type": e["type"], "Objet": e["objet"],
                   "Offres": e["nb_offres"], "Envoyé": "oui" if e["ok"] else "ÉCHEC"} for e in emails]
    return derniere, historique


def charger_preferences(chemin=CHEMIN_PREFS):
    try:
        return json.loads(Path(chemin).read_text(encoding="utf-8"))
    except Exception:
        return {}


def sauver_preferences(prefs, chemin=CHEMIN_PREFS):
    Path(chemin).write_text(json.dumps(prefs, ensure_ascii=False), encoding="utf-8")
