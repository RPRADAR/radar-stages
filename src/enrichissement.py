"""
Enrichissement : le robot lit la PAGE de l'annonce (sur le site de l'entreprise) pour récupérer
la description complète et la date de début, afin de noter l'offre avec toutes les informations.

On ne lit jamais les pages de LinkedIn ou d'Indeed (conditions d'utilisation).
Au plus quelques pages par vérification, avec une pause entre deux pages.
"""
import json
import logging
import re
import time
import unicodedata
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

import base_donnees as bd
from scoring import analyser

log = logging.getLogger("radar")
EN_TETES = {"User-Agent": "RadarStages/1.0 (veille personnelle de stages)", "Accept-Language": "fr,en;q=0.8"}
HOTES_INTERDITS = ("linkedin.com", "indeed.")
LONGUEUR_MIN = 200
LONGUEUR_MAX = 6000
TITRES_DEBUT_OFFRE = ["detail de l'offre", "description du poste", "description de l'offre", "descriptif du poste",
                      "job description", "job details", "about the job", "le poste", "the role"]


def _norm_ligne(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t.replace("’", "'")).strip(" :#")


def telecharger_page(url):
    hote = urlparse(url).netloc.lower()
    if not url.startswith("http") or any(h in hote for h in HOTES_INTERDITS):
        raise ValueError("page non autorisée pour l'enrichissement")
    r = requests.get(url, headers=EN_TETES, timeout=15)
    r.raise_for_status()
    return r.text[:2_000_000]


def _description_json_ld(soup):
    """Beaucoup de sites publient l'offre dans un bloc structuré 'JobPosting' : c'est la source la plus propre."""
    for balise in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(balise.string or "")
        except Exception:
            continue
        candidats = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for c in candidats:
            if isinstance(c, dict) and "JobPosting" in str(c.get("@type", "")) and c.get("description"):
                import html as h
                texte = BeautifulSoup(h.unescape(str(c["description"])), "html.parser").get_text("\n", strip=True)
                if c.get("datePosted"):
                    texte += f"\nDate de parution : {c['datePosted']}"
                return texte
    return ""


def extraire_description(html):
    """Renvoie le texte utile de l'annonce (sans menus, bandeaux, filtres de recherche...)."""
    soup = BeautifulSoup(html, "html.parser")
    texte = _description_json_ld(soup)
    if not texte:
        for balise in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "aside", "select"]):
            balise.decompose()
        zone = soup.find("main") or soup.find("article") or soup.body or soup
        lignes = [re.sub(r"\s+", " ", l).strip() for l in zone.get_text("\n").splitlines()]
        lignes = [l for l in lignes if l]
        debut = next((i for i, l in enumerate(lignes) if _norm_ligne(l) in TITRES_DEBUT_OFFRE), 0)
        texte = "\n".join(lignes[debut:])
    return texte[:LONGUEUR_MAX]


def enrichir(conn, societes, telecharger=telecharger_page, limite=15, pause=1.0):
    """Lit les pages des offres qui en ont besoin, puis re-note ces offres. Renvoie le nombre de pages enrichies."""
    nb = 0
    for r in bd.offres_a_enrichir(conn, limite):
        try:
            texte = extraire_description(telecharger(r["url"]))
            if len(texte) < LONGUEUR_MIN:
                raise ValueError("page vide ou non lisible (probablement chargée par JavaScript)")
        except Exception as e:
            bd.noter_tentative(conn, r["id"])
            log.warning("Enrichissement impossible (%s) : %s", r["url"][:80], e)
            continue
        meta = json.loads(r["meta"] or "{}")
        offre = {"societe": r["societe"], "titre": r["titre"], "lieu": r["lieu"], "description": texte,
                 "contrat": meta.get("contrat", ""), "structure": meta.get("structure", ""), "famille": meta.get("famille", "")}
        analyse = analyser(offre, societes)
        bd.enregistrer_enrichissement(conn, r["id"], texte, analyse)
        nb += 1
        log.info("Offre enrichie : %s | %s -> %s/100 %s", r["societe"], r["titre"][:50], analyse["score"],
                 "(rejetée : " + analyse["rejet"] + ")" if not analyse["retenue"] else "")
        time.sleep(pause)
    conn.commit()
    return nb
