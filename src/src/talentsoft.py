"""
Connecteur Talentsoft : lit les flux RSS OFFICIELS des sites carrières construits sur Talentsoft
(adresses en .aspx, comme jobs.candriam.com ou jobs.amundi.com).

Ces sites publient eux-mêmes une page « RSS et autres flux ». Le robot :
  1. repère sur cette page le flux des stages (« Internship », « Stage »...) ;
  2. repère les flux par pays (France, Luxembourg, Royaume-Uni, Suisse) pour savoir où se trouve chaque offre ;
  3. lit les offres (description complète incluse) et les renvoie au format du projet.
"""
import html as html_lib
import re
import unicodedata
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

EN_TETES = {"User-Agent": "RadarStages/1.0 (veille personnelle de stages)"}
PAGES_FLUX = ["/job/all-rss-feeds.aspx", "/offre-de-emploi/tous-les-flux-rss.aspx"]
CONTRAT_STAGE = re.compile(r"\b(intern|internship|stage|stagiaire|trainee)\b", re.I)
CONTRAT_EXCLU = re.compile(r"apprent|alternan|profession|graduate|\bvie\b|volontariat", re.I)
PAYS_CIBLES = [("France", r"^france$"), ("Luxembourg", r"^luxembourg$"),
               ("Royaume-Uni", r"^(united kingdom|royaume.uni|uk|great britain)$"), ("Suisse", r"^(switzerland|suisse)$")]


def _norm(t):
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower().strip()


def decouvrir_flux(hote, get=None):
    """Lit la page « flux RSS » du site et renvoie ({libellé contrat: url}, {libellé pays: url})."""
    get = get or requests.get
    for chemin in PAGES_FLUX:
        try:
            r = get(f"https://{hote}{chemin}", headers=EN_TETES, timeout=20)
            if r.status_code != 200:
                continue
        except Exception:
            continue
        soupe = BeautifulSoup(r.text, "html.parser")
        contrats, pays = {}, {}
        for a in soupe.find_all("a", href=True):
            if "offerRss.ashx" not in a["href"]:
                continue
            params = parse_qs(urlparse(a["href"]).query)
            lien = urljoin(r.url if hasattr(r, "url") and r.url else f"https://{hote}", a["href"])
            libelle = a.get_text(" ", strip=True)
            if "Rss_Contract" in params:
                contrats[libelle] = lien
            elif "Rss_JobCountry" in params:
                pays[libelle] = lien
        if contrats:
            return contrats, pays
    raise RuntimeError(f"page des flux RSS introuvable sur {hote}")


def lire_flux(contenu_xml):
    """Transforme un flux RSS Talentsoft en liste de dictionnaires (id, reference, titre, description, date, lien)."""
    racine = ET.fromstring(contenu_xml)
    offres = []
    for item in racine.iter("item"):
        lien = (item.findtext("link") or "").strip()
        identifiant = parse_qs(urlparse(lien).query).get("idOffre", [""])[0]
        titre_complet = (item.findtext("title") or "").strip()
        m = re.match(r"^(\d{4}-\d+)\s*-\s*(.*)$", titre_complet)
        reference, titre = (m.group(1), m.group(2)) if m else ("", titre_complet)
        corps = BeautifulSoup(item.findtext("description") or "", "html.parser")
        for saut in corps.find_all("br"):
            saut.replace_with("\n")          # les <br> deviennent de vrais retours à la ligne
        description = re.sub(r"[ \t]*\n\s*", "\n", corps.get_text("")).strip()
        try:
            date_pub = parsedate_to_datetime(item.findtext("pubDate")).strftime("%Y-%m-%d")
        except Exception:
            date_pub = ""
        if identifiant:
            offres.append({"id": identifiant, "reference": reference, "titre": titre, "description": description,
                           "date": date_pub, "lien": lien})
    return offres


def _telecharger_flux(url, get):
    r = get(url, headers=EN_TETES, timeout=20)
    r.raise_for_status()
    return lire_flux(r.content)


def collecter_talentsoft(hote, societe, get=None):
    """Renvoie les offres de STAGE du site, avec leur pays (France, Luxembourg, Royaume-Uni, Suisse)."""
    get = get or requests.get
    contrats, pays = decouvrir_flux(hote, get)
    flux_stage = [u for lib, u in contrats.items() if CONTRAT_STAGE.search(lib) and not CONTRAT_EXCLU.search(lib)]
    if not flux_stage:
        raise RuntimeError(f"aucun flux « stage » trouvé sur {hote}")
    offres = {}
    for url in flux_stage:
        for o in _telecharger_flux(url, get):
            offres.setdefault(o["id"], o)
    lieu_par_id = {}
    for nom_pays, motif in PAYS_CIBLES:
        for lib, url in pays.items():
            if re.match(motif, _norm(lib)):
                for o in _telecharger_flux(url, get):
                    lieu_par_id[o["id"]] = nom_pays
    resultat = []
    for o in offres.values():
        resultat.append({
            "societe": societe, "plateforme": "talentsoft", "id_source": f"talentsoft:{hote}:{o['id']}",
            "titre": o["titre"], "lieu": lieu_par_id.get(o["id"], "Hors zone ciblée"), "url": o["lien"],
            "description": o["description"], "date_publication": o["date"], "contrat": "Stage",
        })
    return resultat
