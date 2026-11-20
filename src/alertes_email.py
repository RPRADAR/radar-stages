"""
Lecture des alertes d'emploi (LinkedIn, Indeed) reçues dans la boîte Gmail du robot.

Ces sites envoient eux-mêmes des emails d'alerte : c'est la méthode officielle et autorisée.
Le robot lit la boîte en LECTURE SEULE (il ne modifie, ne déplace et ne supprime aucun email).
"""
import hashlib
import imaplib
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from email import message_from_bytes, policy
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urlparse

log = logging.getLogger("radar")
MOIS_IMAP = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

BRUIT_LINKEDIN = re.compile(
    r"^(cette entreprise recrute activement|actively recruiting|postulez avec un cv.*|apply with your resume.*|"
    r"\d+ (relations?|connections?|alumni|alumnus|anciens? [ée]l[èe]ves?|contacts?|school alumni)|"
    r"candidature simplifi[ée]e|easy apply|"
    r"soyez parmi les premiers.*|be an early applicant|\d+ candidat.*|.*vous correspond.*)$", re.I)
LIGNE_VOIR_OFFRE = re.compile(r"^(voir l['’]offre d['’]emploi|view job)\s*:\s*(https?://\S+)", re.I)


def _id_linkedin(url):
    m = re.search(r"/jobs/view/(\d+)", url)
    return m.group(1) if m else None


def analyser_linkedin(texte, date_email=None):
    """Lit un email d'alerte LinkedIn (texte brut). Renvoie une liste d'offres au format du projet."""
    lignes = [re.sub(r"\s+", " ", l).strip() for l in texte.splitlines()]  # \s inclut les espaces insécables
    offres = []
    for i, ligne in enumerate(lignes):
        m = LIGNE_VOIR_OFFRE.match(ligne)
        if not m:
            continue
        identifiant = _id_linkedin(m.group(2))
        if not identifiant:
            continue
        # On remonte depuis le lien : lieu, entreprise, titre (en sautant les lignes "bruit")
        trouvees = []
        j = i - 1
        while j >= 0 and len(trouvees) < 3:
            l = lignes[j]
            if re.fullmatch(r"-{5,}", l) or re.match(r"^(gérer les alertes|manage alerts)", l, re.I):
                break
            if l and not BRUIT_LINKEDIN.match(l):
                trouvees.append(l)
            j -= 1
        trouvees.reverse()
        if len(trouvees) < 2:
            continue
        titre = trouvees[0]
        societe = trouvees[1]
        lieu = trouvees[2] if len(trouvees) > 2 else ""
        offres.append({
            "societe": societe, "plateforme": "linkedin", "id_source": f"linkedin:{identifiant}",
            "titre": titre, "lieu": lieu, "url": f"https://www.linkedin.com/jobs/view/{identifiant}/",
            "description": "", "date_publication": "",  # LinkedIn n'indique ni description ni date dans l'email
        })
    return offres


def _age_en_jours(ligne):
    l = ligne.lower()
    if re.search(r"(à l['’]instant|aujourd['’]hui|just posted|today|il y a moins de)", l):
        return 0
    m = re.search(r"(?:il y a|posted)\s+(?:plus de\s+)?(\d+)\+?\s*(heures?|jours?|semaines?|mois|hours?|days?|weeks?|months?)", l)
    if not m:
        m = re.search(r"(\d+)\+?\s*(heures?|jours?|semaines?|mois|hours?|days?|weeks?|months?)\s+ago", l)
    if not m:
        return None
    n, unite = int(m.group(1)), m.group(2)
    if unite.startswith(("heure", "hour")):
        return 0
    if unite.startswith(("jour", "day")):
        return n
    if unite.startswith(("semaine", "week")):
        return 7 * n
    return 30 * n


BRUIT_INDEED = re.compile(r"^(candidature simplifi[ée]e|easily apply|.*(de l['’]heure|par (an|mois|heure)|per (hour|year|month)).*|"
                          r"urgent(ly hiring)?|recrute de façon urgente)$", re.I)


def analyser_indeed(texte, date_email=None):
    """Lit un email d'alerte Indeed (texte brut)."""
    date_email = date_email or datetime.now(timezone.utc)
    offres = []
    for paragraphe in re.split(r"\n\s*\n", texte):
        lignes = [l.strip() for l in paragraphe.splitlines() if l.strip()]
        liens = [l for l in lignes if re.match(r"^https?://", l)]
        if not liens or len(lignes) < 3:
            continue
        url = liens[-1]
        corps = [l for l in lignes if not re.match(r"^https?://", l)]
        titre = corps[0]
        societe, lieu = corps[1], ""
        if " - " in corps[1]:
            societe, lieu = corps[1].rsplit(" - ", 1)
        age = next((_age_en_jours(l) for l in corps[2:] if _age_en_jours(l) is not None and re.match(r"^(il y a|posted|\d)", l.lower())), None)
        extrait = " ".join(l for l in corps[2:] if not BRUIT_INDEED.match(l) and not re.match(r"^(il y a|posted)", l.lower()))
        jk = parse_qs(urlparse(url).query).get("jk", [None])[0]
        if jk:
            hote = urlparse(url).netloc or "fr.indeed.com"
            identifiant, lien = jk, f"https://{hote}/viewjob?jk={jk}"
        else:
            identifiant = "h" + hashlib.sha1(f"{titre}|{societe}|{lieu}".encode()).hexdigest()[:12]
            lien = url
        date_pub = (date_email - timedelta(days=age)).strftime("%Y-%m-%d") if age is not None else ""
        offres.append({
            "societe": societe.strip(), "plateforme": "indeed", "id_source": f"indeed:{identifiant}",
            "titre": titre, "lieu": lieu.strip(), "url": lien, "description": extrait, "date_publication": date_pub,
        })
    return offres


def _corps_texte(message):
    partie = message.get_body(preferencelist=("plain",))
    return partie.get_content() if partie else ""


def offres_depuis_message(message):
    """Choisit le bon lecteur selon l'expéditeur. Renvoie (offres, expediteur_reconnu)."""
    expediteur = (message["From"] or "").lower()
    try:
        date_email = parsedate_to_datetime(message["Date"])
    except Exception:
        date_email = datetime.now(timezone.utc)
    texte = _corps_texte(message)
    # On reconnaît l'alerte par l'expéditeur, ou, si tu as transféré l'email à la main, par son contenu.
    if "linkedin.com" in expediteur or "jobalerts-noreply@linkedin.com" in texte.lower():
        return analyser_linkedin(texte, date_email), True
    if "indeed.com" in expediteur or "alerte emploi indeed" in texte.lower() or "jobalert.indeed.com" in texte.lower():
        return analyser_indeed(texte, date_email), True
    return [], False


def lire_boite(utilisateur, mot_de_passe, hote="imap.gmail.com", jours=3):
    """Lit (en lecture seule) les emails des derniers jours de la boîte du robot."""
    boite = imaplib.IMAP4_SSL(hote)
    try:
        boite.login(utilisateur, mot_de_passe)
        boite.select("INBOX", readonly=True)
        depuis = date.today() - timedelta(days=jours)
        depuis_txt = f"{depuis.day:02d}-{MOIS_IMAP[depuis.month - 1]}-{depuis.year}"
        _, donnees = boite.search(None, "SINCE", depuis_txt)
        for numero in donnees[0].split():
            _, brut = boite.fetch(numero, "(BODY.PEEK[])")
            yield message_from_bytes(brut[0][1], policy=policy.default)
    finally:
        try:
            boite.logout()
        except Exception:
            pass


def collecter_alertes(jours=3):
    """Collecteur utilisé par le robot : renvoie les offres trouvées dans les alertes récentes."""
    utilisateur, mot_de_passe = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
    if not utilisateur or not mot_de_passe:
        raise RuntimeError("SMTP_USER / SMTP_PASSWORD manquants pour lire la boîte du robot")
    offres, lus, reconnus, inconnus = [], 0, 0, set()
    for message in lire_boite(utilisateur, mot_de_passe, os.environ.get("IMAP_HOST", "imap.gmail.com"), jours):
        lus += 1
        trouvees, reconnu = offres_depuis_message(message)
        offres.extend(trouvees)
        if reconnu:
            reconnus += 1
        else:
            inconnus.add(re.sub(r".*@", "@", (message["From"] or "inconnu").strip(" <>")))  # on ne garde que le domaine
    log.info("Alertes email : %d emails lus, %d alertes reconnues, %d offres extraites. Expéditeurs non reconnus : %s",
             lus, reconnus, len(offres), sorted(inconnus) or "aucun")
    return offres
