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
import urllib.robotparser as robotparser
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

import base_donnees as bd
from scoring import analyser

log = logging.getLogger("radar")
EN_TETES = {"User-Agent": "RadarStages/1.0 (veille personnelle de stages)", "Accept-Language": "fr,en;q=0.8"}
HOTES_INTERDITS = ("linkedin.com", "indeed.")
LONGUEUR_MIN = 400
LONGUEUR_MAX = 6000
TITRES_DEBUT_OFFRE = ["detail de l'offre", "description du poste", "description de l'offre", "descriptif du poste",
                      "job description", "job details", "about the job", "le poste", "the role"]


def _norm_ligne(t):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t.replace("’", "'")).strip(" :#")


class RobotsInterdit(Exception):
    """Le fichier robots.txt du site demande aux programmes de ne pas lire cette page : on respecte."""


_ROBOTS = {}   # mémoire : un seul téléchargement de robots.txt par site et par exécution


def robots_autorise(url):
    """Vérifie le fichier robots.txt du site (les règles que le site donne aux programmes)."""
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _ROBOTS:
        parseur = robotparser.RobotFileParser()
        try:
            r = requests.get(base + "/robots.txt", headers=EN_TETES, timeout=10)
            if r.status_code in (401, 403):
                parseur.disallow_all = True
            elif r.status_code >= 400:
                parseur.allow_all = True
            else:
                parseur.parse(r.text.splitlines())
        except Exception:
            parseur.allow_all = True   # robots.txt injoignable : on ne peut rien en conclure
        _ROBOTS[base] = parseur
    return _ROBOTS[base].can_fetch("RadarStages", url)


def telecharger_page(url):
    hote = urlparse(url).netloc.lower()
    if not url.startswith("http") or any(h in hote for h in HOTES_INTERDITS):
        raise ValueError("page non autorisée pour l'enrichissement")
    if not robots_autorise(url):
        raise RobotsInterdit(f"robots.txt de {hote} interdit la lecture automatique de cette page")
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


def extraire_description(html, depuis_le_marqueur=True):
    """Renvoie le texte utile de l'annonce (sans menus, pied de page...)."""
    soup = BeautifulSoup(html, "html.parser")
    texte = _description_json_ld(soup)
    if not texte:
        # Attention : on ne supprime PAS les <form> : certains sites (ASP.NET) enveloppent toute la page dans un formulaire.
        # Les bandeaux <header>/<aside> sont conservés : la date de début s'y cache parfois.
        for balise in soup(["script", "style", "noscript", "nav", "footer", "select"]):
            balise.decompose()
        zone = soup.find("main") or soup.find("article") or soup.body or soup
        lignes = [re.sub(r"\s+", " ", l).strip() for l in zone.get_text("\n").splitlines()]
        lignes = [l for l in lignes if l]
        # On part du DERNIER titre "Détail de l'offre" (le premier est souvent le fil d'Ariane, en haut de page).
        debut = 0
        for titre in (TITRES_DEBUT_OFFRE if depuis_le_marqueur else []):
            positions = [i for i, l in enumerate(lignes) if _norm_ligne(l) == titre]
            if positions:
                debut = positions[-1]
                break
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
        except RobotsInterdit as e:
            bd.abandonner(conn, r["id"])   # inutile de réessayer : le site refuse les robots
            log.info("Page non lue : %s", e)
            continue
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
