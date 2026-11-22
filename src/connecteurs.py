"""
Connecteurs : lisent les offres d'emploi publiées par les entreprises
sur leurs plateformes de recrutement (Greenhouse, Lever, SmartRecruiters, Ashby).

Ces plateformes proposent des flux publics, prévus pour être lus par des programmes.
Chaque connecteur renvoie des offres au même format (un "dictionnaire") :
    societe, titre, lieu, url, description, date_publication, id_source, plateforme
"""
import html
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup

EN_TETES = {"User-Agent": "RadarStages/1.0 (veille personnelle de stages)"}
DELAI_MAX = 20  # secondes d'attente maximum par requête


def _texte(contenu_html):
    """Transforme du HTML en texte simple."""
    contenu_html = html.unescape(contenu_html or "")
    return BeautifulSoup(contenu_html, "html.parser").get_text(" ", strip=True)


def _get_json(url):
    reponse = requests.get(url, headers=EN_TETES, timeout=DELAI_MAX)
    reponse.raise_for_status()  # lève une erreur si le site répond "erreur"
    return reponse.json()


def _offre(societe, plateforme, id_source, titre, lieu, url, description, date_pub):
    return {
        "societe": societe,
        "plateforme": plateforme,
        "id_source": f"{plateforme}:{id_source}",
        "titre": (titre or "").strip(),
        "lieu": (lieu or "").strip(),
        "url": url or "",
        "description": description or "",
        "date_publication": date_pub or "",
    }


def greenhouse(identifiant, societe):
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{identifiant}/jobs?content=true")
    offres = []
    for j in data.get("jobs", []):
        offres.append(_offre(
            societe, "greenhouse", j.get("id"), j.get("title"),
            (j.get("location") or {}).get("name"), j.get("absolute_url"),
            _texte(j.get("content")), (j.get("first_published") or j.get("updated_at") or "")[:10],
        ))
    return offres


def lever(identifiant, societe):
    data = _get_json(f"https://api.lever.co/v0/postings/{identifiant}?mode=json")
    offres = []
    for j in data:
        cree = j.get("createdAt")
        date_pub = datetime.fromtimestamp(cree / 1000, tz=timezone.utc).strftime("%Y-%m-%d") if cree else ""
        offres.append(_offre(
            societe, "lever", j.get("id"), j.get("text"),
            (j.get("categories") or {}).get("location"), j.get("hostedUrl"),
            j.get("descriptionPlain"), date_pub,
        ))
    return offres


def ashby(identifiant, societe):
    data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{identifiant}")
    offres = []
    for j in data.get("jobs", []):
        offres.append(_offre(
            societe, "ashby", j.get("id"), j.get("title"), j.get("location"),
            j.get("jobUrl"), j.get("descriptionPlain"), (j.get("publishedAt") or "")[:10],
        ))
    return offres


def smartrecruiters(identifiant, societe):
    data = _get_json(f"https://api.smartrecruiters.com/v1/companies/{identifiant}/postings?limit=100")
    offres = []
    for j in data.get("content", []):
        lieu_brut = j.get("location") or {}
        lieu = ", ".join(x for x in [lieu_brut.get("city"), lieu_brut.get("country")] if x)
        description = ""
        try:  # la liste ne contient pas la description : on va la chercher offre par offre
            detail = _get_json(j["ref"])
            sections = (detail.get("jobAd") or {}).get("sections") or {}
            description = " ".join(_texte(s.get("text")) for s in sections.values() if isinstance(s, dict))
        except Exception:
            pass  # sans description, l'offre sera notée uniquement sur son titre
        offres.append(_offre(
            societe, "smartrecruiters", j.get("id"), j.get("name"), lieu,
            f"https://jobs.smartrecruiters.com/{identifiant}/{j.get('id')}",
            description, (j.get("releasedDate") or "")[:10],
        ))
    return offres


CONNECTEURS = {
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    "smartrecruiters": smartrecruiters,
}


def recuperer_offres(plateforme, identifiant, societe):
    """Point d'entrée : choisit le bon connecteur selon la plateforme."""
    if plateforme not in CONNECTEURS:
        raise ValueError(f"Plateforme inconnue : {plateforme}")
    return CONNECTEURS[plateforme](identifiant, societe)


# Sites carrières Talentsoft (flux RSS officiels) : le module est importé ici pour éviter une dépendance circulaire
from talentsoft import collecter_talentsoft  # noqa: E402

CONNECTEURS["talentsoft"] = collecter_talentsoft

from workday import collecter_workday  # noqa: E402

CONNECTEURS["workday"] = collecter_workday
