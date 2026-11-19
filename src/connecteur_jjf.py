"""
Connecteur Junior Job Finance (juniorjobfinance.com).

Le site publie lui-même un flux RSS officiel de ses nouvelles offres :
https://juniorjobfinance.com/offres.xml
Chaque offre renvoie vers l'annonce d'origine, chez l'entreprise.
Le flux est mis à jour une fois par jour (le matin) : ce n'est pas du "temps réel",
mais c'est une très bonne source complémentaire, surtout pour Paris.
"""
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

URL_FLUX = "https://juniorjobfinance.com/offres.xml"
EN_TETES = {"User-Agent": "RadarStages/1.0 (veille personnelle de stages)"}


def lire_flux(contenu_xml):
    """Transforme le texte XML du flux en liste d'offres au format du projet."""
    racine = ET.fromstring(contenu_xml)
    offres = []
    for item in racine.iter("item"):
        titre_complet = (item.findtext("title") or "").strip()
        poste, _, societe = titre_complet.rpartition(" — ")
        if not poste:  # pas de " — " dans le titre
            poste, societe = titre_complet, ""
        morceaux = [m.strip() for m in (item.findtext("description") or "").split(" · ")]
        famille = morceaux[0] if morceaux else ""
        contrat = morceaux[-1] if len(morceaux) >= 2 else ""
        lieu = morceaux[-2] if len(morceaux) >= 3 else ""
        structure = " · ".join(morceaux[1:-2]) if len(morceaux) >= 4 else ""
        try:
            date_pub = parsedate_to_datetime(item.findtext("pubDate")).strftime("%Y-%m-%d")
        except Exception:
            date_pub = ""
        url = (item.findtext("link") or "").strip()
        offres.append({
            "societe": societe, "plateforme": "juniorjobfinance",
            "id_source": f"jjf:{url}", "titre": poste, "lieu": lieu, "url": url,
            "description": "", "date_publication": date_pub,
            "famille": famille, "structure": structure, "contrat": contrat,
        })
    return offres


def recuperer_offres_jjf():
    reponse = requests.get(URL_FLUX, headers=EN_TETES, timeout=20)
    reponse.raise_for_status()
    return lire_flux(reponse.content)


def candidats_gestion_actifs(offres):
    """Garde les stages (uniquement) chez des sociétés de gestion ou dans le métier 'Gestion d'actifs'.
    Ce n'est qu'un premier tri : la notation fine sur 100 viendra à l'étape suivante."""
    gardees = []
    for o in offres:
        if o["contrat"].lower() != "stage":
            continue  # pas d'alternance, de VIE, de CDI/CDD
        if o["structure"] == "Société de gestion" or o["famille"] == "Gestion d'actifs":
            gardees.append(o)
    return gardees
