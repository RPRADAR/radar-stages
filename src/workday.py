"""
Connecteur Workday : lit les offres d'un site carrières Workday (adresse en .myworkdayjobs.com).

Le site carrières Workday affiche ses offres à partir d'un flux de données JSON que son propre site utilise.
Le robot interroge ce flux avec des requêtes simples (comme le ferait un navigateur), en respectant le robots.txt.
Ce n'est pas une interface documentée par Workday : si elle change, le robot signalera une erreur.

Dans data/sources.csv, la colonne « identifiant » s'écrit :  hôte/nom-du-site
exemple :  gam.wd3.myworkdayjobs.com/GAM
"""
import html as html_lib
import logging
import re

import requests
from bs4 import BeautifulSoup

from alertes_email import _age_en_jours
from datetime import datetime, timedelta, timezone

log = logging.getLogger("radar")
EN_TETES = {"User-Agent": "RadarStages/1.0 (veille personnelle de stages)", "Accept": "application/json",
            "Content-Type": "application/json", "Accept-Language": "en-US"}
TERMES = ["intern", "internship", "stage", "stagiaire", "trainee", "London intern", "Paris intern", "Luxembourg intern"]
TITRE_STAGE = re.compile(r"\b(intern|internship|stage|stagiaire|trainee|placement|summer analyst|spring week)\b", re.I)
TITRE_EXCLU = re.compile(r"apprent|alternan|graduate programme|graduate program", re.I)
MAX_PAR_TERME = 40
MAX_DETAILS = 25
CACHE_DESCRIPTION = None   # fonction(id_source) -> description déjà connue ; branchée par radar.py pour éviter de relire les mêmes offres


def _separer(identifiant):
    hote, _, site = identifiant.partition("/")
    return hote, site.strip("/"), hote.split(".")[0]


def _texte(html_brut):
    return BeautifulSoup(html_lib.unescape(html_brut or ""), "html.parser").get_text("\n", strip=True)


def collecter_workday(identifiant, societe, post=None, get=None, robots=None):
    post, get = post or requests.post, get or requests.get
    hote, site, tenant = _separer(identifiant)
    base = f"https://{hote}/wday/cxs/{tenant}/{site}"
    if robots is None:
        import enrichissement
        robots = enrichissement.robots_autorise
    if not robots(base + "/jobs"):
        log.warning("Workday %s : robots.txt interdit la lecture automatique, source ignorée", hote)
        return []

    postes = {}
    for terme in TERMES:
        decalage = 0
        while decalage < MAX_PAR_TERME:
            r = post(base + "/jobs", headers=EN_TETES, timeout=30,
                     json={"appliedFacets": {}, "limit": 20, "offset": decalage, "searchText": terme})
            r.raise_for_status()
            donnees = r.json()
            liste = donnees.get("jobPostings") or []
            for p in liste:
                if p.get("externalPath"):
                    postes.setdefault(p["externalPath"], p)
            decalage += 20
            if not liste or decalage >= (donnees.get("total") or 0):
                break

    candidats = [p for p in postes.values() if TITRE_STAGE.search(p.get("title", "")) and not TITRE_EXCLU.search(p.get("title", ""))]
    offres, details_lus = [], 0
    for p in candidats:
        chemin = p["externalPath"]
        reference = (p.get("bulletFields") or [chemin.rsplit("_", 1)[-1]])[0]
        id_source = f"workday:{hote}:{reference}"
        lieu = (p.get("locationsText") or "").strip()
        description, url, date_pub = "", f"https://{hote}/{site}{chemin}", ""
        age = _age_en_jours(p.get("postedOn") or "")
        if age is not None:
            date_pub = (datetime.now(timezone.utc) - timedelta(days=age)).strftime("%Y-%m-%d")
        connue = CACHE_DESCRIPTION(id_source) if CACHE_DESCRIPTION else ""
        besoin_lieu = bool(re.match(r"^\d+\s+locations?$", lieu, re.I))
        if connue and not besoin_lieu:
            description = connue
        elif details_lus < MAX_DETAILS:
            try:
                d = get(base + chemin, headers=EN_TETES, timeout=30)
                d.raise_for_status()
                info = d.json().get("jobPostingInfo") or {}
                description = _texte(info.get("jobDescription"))
                if info.get("startDate"):
                    description = f"Start date: {info['startDate']}\n" + description
                if besoin_lieu or not lieu:
                    lieux = [info.get("location", "")] + list(info.get("additionalLocations") or [])
                    lieu = " | ".join(l for l in lieux if l)
                url = info.get("externalUrl") or url
                details_lus += 1
            except Exception as e:
                log.warning("Workday %s : détail illisible (%s)", hote, e)
                description = connue
        if re.match(r"^\d+\s+locations?$", lieu, re.I):
            lieu = ""     # lieux inconnus : on ne rejette pas l'offre pour cette raison
        offres.append({"societe": societe, "plateforme": "workday", "id_source": id_source, "titre": p.get("title", "").strip(),
                       "lieu": lieu, "url": url, "description": description, "date_publication": date_pub})
    log.info("Workday %s : %d postes vus, %d stages candidats", hote, len(postes), len(offres))
    return offres
