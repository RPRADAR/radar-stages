"""
Le robot : une exécution = une vérification complète.
    python src/radar.py                 -> vérification normale (envoie les emails)
    python src/radar.py --sans-email    -> essai : affiche l'email au lieu de l'envoyer
    python src/radar.py --test-email    -> envoie un email de test pour vérifier ta configuration
"""
import argparse
import csv
import logging
import os
import sys
from functools import partial
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_donnees as bd
import emailing
from alertes_email import collecter_alertes
from connecteur_jjf import recuperer_offres_jjf
from connecteurs import recuperer_offres
import enrichissement
import workday
from erreurs import SourceIgnoree
from scoring import analyser, charger_societes

RACINE = Path(__file__).resolve().parent.parent
SOURCE_ALERTES = "alertes_email"
log = logging.getLogger("radar")


def sources_par_defaut():
    sources = [("jjf", recuperer_offres_jjf)]
    if os.environ.get("ALERTES_EMAIL", "").strip().lower() == "oui":   # alertes LinkedIn / Indeed
        sources.append((SOURCE_ALERTES, collecter_alertes))
    fichier = RACINE / "data" / "sources.csv"
    if fichier.exists():
        with open(fichier, encoding="utf-8-sig") as f:
            for l in csv.DictReader(f):
                if l.get("plateforme") and l.get("identifiant") and not (l.get("statut") or "").lower().startswith("ignor"):
                    sources.append((f"{l['plateforme']}:{l['identifiant']}",
                                    partial(recuperer_offres, l["plateforme"], l["identifiant"], l["nom"])))
    return sources


def _est_un_stage(analyse):
    r = analyse["rejet"]
    return not (r.startswith("contrat") or "pas clairement un stage" in r or r.startswith("alternance"))


def lien_accessible(url):
    """False seulement si la page n'existe plus (404/410). Un blocage anti-robot (403...) n'est pas une preuve."""
    if "linkedin.com" in url or "indeed." in url:
        return True  # ces sites bloquent les robots : on ne les interroge pas
    try:
        r = requests.get(url, headers={"User-Agent": "RadarStages/1.0"}, timeout=10, stream=True)
        r.close()
        return r.status_code not in (404, 410)
    except Exception:
        return True


def executer(chemin_db, sources, envoi=None, societes=None, verifier_liens=True, enrichir=False, telecharger=None):
    """Fait une vérification complète. `envoi` = fonction d'envoi d'email (None = essai sans envoi)."""
    conn = bd.ouvrir(chemin_db)
    societes = societes if societes is not None else charger_societes()
    now = bd.maintenant()
    workday.CACHE_DESCRIPTION = lambda id_source: bd.description_connue(conn, id_source)   # évite de relire les offres déjà connues
    compte = {"lues": 0, "nouvelles": 0, "republiees": 0, "modifiees": 0, "doublons": 0}
    erreurs, ignorees, sources_ok = [], [], 0

    for nom_source, collecteur in sources:
        try:
            offres = collecteur()
        except SourceIgnoree as e:
            ignorees.append(f"{nom_source} : {e}")
            log.warning("Source ignorée : %s -> %s", nom_source, e)
            continue
        except Exception as e:
            erreurs.append(f"{nom_source} : {type(e).__name__} : {e}")
            log.error("Source en erreur : %s -> %s", nom_source, e)
            continue
        sources_ok += 1
        compte["lues"] += len(offres)
        for o in offres:
            for k in ("famille", "structure", "contrat"):
                o.setdefault(k, "")
            # si la description a déjà été lue sur la page de l'annonce, on la réutilise pour la notation
            a = analyser(dict(o, description=o["description"] or bd.description_connue(conn, o["id_source"])), societes)
            if not _est_un_stage(a):
                continue
            etat = bd.enregistrer_offre(conn, o, nom_source, a, now)
            cle = {"nouvelle": "nouvelles", "republiee": "republiees", "modifiee": "modifiees", "doublon": "doublons"}.get(etat)
            if cle:
                compte[cle] += 1
        if nom_source != SOURCE_ALERTES:   # une alerte ne liste pas toutes les offres : elle ne prouve pas qu'une offre a disparu
            bd.marquer_disparues(conn, nom_source, now)
        conn.commit()
        log.info("Source %s : %d offres lues", nom_source, len(offres))

    if enrichir:   # lecture des pages d'annonces des entreprises (description complète + date de début)
        try:
            nb = enrichissement.enrichir(conn, societes, telecharger or enrichissement.telecharger_page)
            log.info("Enrichissement : %d pages lues", nb)
        except Exception as e:
            log.error("Enrichissement en erreur (sans gravité) : %s", e)
    if verifier_liens:
        for r in bd.offres_a_notifier(conn):
            if r["lien_ok"] is None:
                conn.execute("UPDATE offres SET lien_ok=? WHERE id=?", (int(lien_accessible(r["url"])), r["id"]))
        conn.commit()
    a_notifier = bd.offres_a_notifier(conn)

    tout_en_echec = sources_ok == 0
    if tout_en_echec:
        statut, (objet, texte, corps), type_email = "erreur", emailing.composer_erreur(erreurs + ignorees), "erreur"
    elif a_notifier:
        statut = "ok" if not erreurs else "partielle"
        (objet, texte, corps), type_email = emailing.composer_offres(a_notifier, erreurs, ignorees), "offres"
    elif erreurs:
        statut, (objet, texte, corps), type_email = "partielle", emailing.composer_erreur(erreurs, partiel=True), "partiel"
    else:
        statut, (objet, texte, corps), type_email = "ok", emailing.composer_ras(ignorees), "ras"

    bd.journaliser_verification(conn, now, statut, compte["lues"], compte["nouvelles"], compte["republiees"], compte["modifiees"], erreurs)
    envoye = False
    if envoi is None:
        print(f"\n=== EMAIL (non envoyé, mode essai) ===\nObjet : {objet}\n\n{texte}\n")
        (RACINE / "logs").mkdir(exist_ok=True)
        (RACINE / "logs" / "dernier_email.html").write_text(corps, encoding="utf-8")
    else:
        try:
            envoi(objet, texte, corps)
            envoye = True
            bd.journaliser_email(conn, type_email, objet, len(a_notifier) if type_email == "offres" else 0, True)
            if type_email == "offres":
                bd.marquer_notifiees(conn, [r["id"] for r in a_notifier])
        except Exception as e:
            bd.journaliser_email(conn, type_email, objet, 0, False, str(e))
            log.error("Échec d'envoi de l'email : %s", e)
    conn.commit()
    conn.close()
    return {"statut": statut, "type_email": type_email, "objet": objet, "envoye": envoye,
            "erreurs": erreurs, "nb_a_notifier": len(a_notifier), **compte}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sans-email", action="store_true")
    parser.add_argument("--test-email", action="store_true")
    args = parser.parse_args()
    try:
        from dotenv import load_dotenv
        load_dotenv(RACINE / ".env")
    except ImportError:
        pass
    (RACINE / "logs").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(RACINE / "logs" / "radar.log", encoding="utf-8")])
    if args.test_email:
        emailing.envoyer("Test – Radar stages Asset Management", "Si tu lis ce message, l'envoi d'emails fonctionne ✅",
                         "<p>Si tu lis ce message, l'envoi d'emails fonctionne ✅</p>")
        print("Email de test envoyé.")
        return 0
    envoi = None if args.sans_email else emailing.envoyer
    resultat = executer(RACINE / "data" / "radar.db", sources_par_defaut(), envoi, enrichir=True)
    log.info("Résultat : %s", resultat)
    if envoi is not None and not resultat["envoye"]:
        return 1  # l'exécution apparaîtra en rouge sur GitHub, ce qui te prévient
    return 0


if __name__ == "__main__":
    sys.exit(main())
