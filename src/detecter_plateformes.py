"""
Détecteur de plateformes de recrutement.

Pour chacune des sociétés de data/companies.csv, le programme essaie les
adresses publiques de Greenhouse, Lever, Ashby et SmartRecruiters.
Si une adresse répond avec de vraies offres, il l'enregistre dans
data/sources_candidates.csv, avec des exemples d'offres pour que TU puisses vérifier
qu'il s'agit bien de la bonne société (un nom peut être partagé par deux entreprises).
"""
import csv
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

EN_TETES = {"User-Agent": "RadarStages/1.0 (veille personnelle de stages)"}
DELAI_MAX = 15
RACINE = Path(__file__).resolve().parent.parent
MOTS_STAGE = re.compile(r"intern|stage|stagiaire|internship|trainee", re.I)
MOTS_GENERIQUES = {"banque", "swiss", "union", "european", "royal", "global", "international"}
MOTS_INUTILES = {"asset", "management", "managers", "manager", "investment", "investments",
                 "gestion", "group", "partners", "and", "de", "la", "le", "les", "des", "du",
                 "investors", "fund", "funds", "reim"}


def _ascii(texte):
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return texte.lower()


def variantes(nom):
    """Fabrique les identifiants probables d'une société (ex : 'amundi')."""
    acronyme = re.findall(r"\(([^)]+)\)", nom)
    base = _ascii(re.sub(r"\([^)]*\)", " ", nom)).replace("&", "")
    base = re.sub(r"[^a-z0-9 ]", " ", base.replace("'", ""))
    mots = [m for m in base.split() if m]
    coeur = [m for m in mots if m not in MOTS_INUTILES] or mots
    candidats = [_ascii(a) for a in acronyme if re.fullmatch(r"[A-Za-z]{3,6}", a.strip())]
    candidats += ["".join(coeur), "-".join(coeur), "".join(mots), "-".join(mots)]
    if len(coeur) > 1 and len(coeur[0]) >= 5 and coeur[0] not in MOTS_GENERIQUES:
        candidats.append(coeur[0])  # ex : "amundi" pour "Amundi Luxembourg"
    resultat = []
    for c in candidats:
        if len(c) >= 3 and c not in resultat:
            resultat.append(c)
    return resultat[:6]


def _requete(url):
    reponse = requests.get(url, headers=EN_TETES, timeout=DELAI_MAX)
    if reponse.status_code != 200:
        return None
    return reponse.json()


def _verifier(plateforme, slug):
    """Renvoie (nb_offres, liste de (titre, lieu)) ou None si la plateforme ne connaît pas ce slug."""
    if plateforme == "greenhouse":
        data = _requete(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
        jobs = (data or {}).get("jobs") or []
        offres = [(j.get("title", ""), (j.get("location") or {}).get("name", "")) for j in jobs]
    elif plateforme == "lever":
        data = _requete(f"https://api.lever.co/v0/postings/{slug}?mode=json")
        jobs = data if isinstance(data, list) else []
        offres = [(j.get("text", ""), (j.get("categories") or {}).get("location", "")) for j in jobs]
    elif plateforme == "ashby":
        data = _requete(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
        jobs = (data or {}).get("jobs") or []
        offres = [(j.get("title", ""), j.get("location", "")) for j in jobs]
    elif plateforme == "smartrecruiters":
        data = _requete(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100")
        jobs = (data or {}).get("content") or []
        offres = [(j.get("name", ""), (j.get("location") or {}).get("city", "")) for j in jobs]
    else:
        return None
    return (len(offres), offres) if offres else None


def tester(tache):
    nom, plateforme, slug = tache
    try:
        resultat = _verifier(plateforme, slug)
    except Exception:
        return None
    if not resultat:
        return None
    nb, offres = resultat
    stages = [o for o in offres if MOTS_STAGE.search(o[0])]
    return {
        "nom": nom, "plateforme": plateforme, "identifiant": slug,
        "nb_offres": nb, "nb_stages": len(stages),
        "exemples_titres": " || ".join(o[0] for o in offres[:3]),
        "exemples_lieux": " || ".join(o[1] for o in offres[:3]),
        "statut": "à valider",
    }


def main():
    with open(RACINE / "data" / "companies.csv", encoding="utf-8-sig") as f:
        societes = [l["nom"] for l in csv.DictReader(f)]
    taches = [(n, p, s) for n in societes for s in variantes(n)
              for p in ("greenhouse", "lever", "ashby", "smartrecruiters")]
    print(f"{len(societes)} sociétés, {len(taches)} vérifications. Patiente 2 à 5 minutes...")
    with ThreadPoolExecutor(max_workers=8) as pool:
        resultats = [r for r in pool.map(tester, taches) if r]
    resultats.sort(key=lambda r: r["nom"])
    sortie = RACINE / "data" / "sources_candidates.csv"
    colonnes = ["nom", "plateforme", "identifiant", "nb_offres", "nb_stages",
                "exemples_titres", "exemples_lieux", "statut"]
    with open(sortie, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=colonnes)
        w.writeheader()
        w.writerows(resultats)
    trouvees = sorted({r["nom"] for r in resultats})
    print(f"\nTerminé : {len(trouvees)} sociétés sur {len(societes)} ont une plateforme détectée.")
    for r in resultats:
        print(f" - {r['nom']} -> {r['plateforme']} / {r['identifiant']} "
              f"({r['nb_offres']} offres, dont {r['nb_stages']} stages) | ex : {r['exemples_titres'][:70]}")
    print(f"\nFichier créé : {sortie}")


if __name__ == "__main__":
    main()
