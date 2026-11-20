"""
Notation des offres (sur 100), sans IA payante : des règles Python.

Pour chaque offre, on répond à ces questions :
  1. Est-ce un stage ?                      (sinon : rejet)
  2. Y a-t-il une exclusion stricte ?       (M&A, trading, produits structurés... : rejet)
  3. Le début est-il entre avril et août 2027 ? (avant avril ou après août : rejet ; inconnu : on garde et on le signale)
  4. Puis une note sur 100 :
        30 pts  société de gestion / Asset Management
        25 pts  Sales OU Investment Management (même poids pour les deux)
        15 pts  pertinence des missions
        15 pts  localisation (Paris, Londres, Genève, Luxembourg)
        15 pts  compatibilité de la date de début
Règle de sécurité : sans preuve sérieuse d'Asset Management (moins de 15 pts sur 30),
la note est plafonnée à 40. Un simple mot-clé dans le titre ne suffit donc jamais.
"""
import csv
import re
import unicodedata
from datetime import date
from pathlib import Path

SEUIL_NOTIFICATION = 60          # note minimale pour recevoir l'offre par email
DEBUT_MIN = (2027, 4)            # avril 2027
DEBUT_MAX = (2027, 8)            # août 2027

NOMS_MOIS = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet",
             "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
MOIS = {"janvier": 1, "january": 1, "fevrier": 2, "february": 2, "mars": 3, "march": 3,
        "avril": 4, "april": 4, "mai": 5, "may": 5, "juin": 6, "june": 6,
        "juillet": 7, "july": 7, "aout": 8, "august": 8, "septembre": 9, "september": 9,
        "octobre": 10, "october": 10, "novembre": 11, "november": 11,
        "decembre": 12, "december": 12}

MOTS_STAGE = ["stage", "stagiaire", "intern", "internship", "trainee"]
MOTS_PAS_STAGE = ["alternance", "apprenti", "apprenticeship", "work-study", "cdi", "cdd",
                  "permanent", "graduate programme", "graduate program", "graduate scheme",
                  "volontariat international"]
# Exclusions strictes (cherchées dans le TITRE)
EXCLUSIONS_TITRE = [
    (r"\bm&a\b|\bm and a\b|mergers|fusions? (et|&) acquisitions?", "M&A"),
    (r"investment banking|banque d'investissement|\bibd\b", "banque d'investissement"),
    (r"structured products?|produits? structures?|structuration", "produits structurés"),
    (r"\btrad(er|ing)\b|\btrading\b", "trading"),
    (r"global markets", "Global Markets"),
    (r"\baudit\b|\bauditor\b|\bauditeur\b", "audit"),
    (r"consult(ant|ing)|\bconseil en\b|advisory services", "conseil"),
    (r"corporate finance|finance d'entreprise", "finance d'entreprise"),
    (r"private banking|banquier prive|banque privee|family office|wealth planning", "banque privée"),
]
# Signaux faibles (cherchés dans la description) : retirent des points mais ne rejettent pas
SIGNAUX_DESCRIPTION = [
    (r"structured products?|produits? structures?", "mentionne les produits structurés"),
    (r"\bm&a\b|mergers", "mentionne le M&A"),
    (r"\btrading desk\b|\btrader\b", "mentionne le trading"),
]

MOTS_SALES = ["sales", "distribution", "commercial", "client relationship", "relation client",
              "business development", "developpement commercial", "investment specialist",
              "investment solutions", "client portfolio solutions", "client & product",
              "client and product", "product specialist", "wholesale", "sales support",
              "sales strategy", "client service", "client advisory", "relations investisseurs"]
MOTS_IM = ["portfolio management", "portfolio manager", "gestion sous mandat", "gestion de portefeuille",
           "assistant gerant", "gerant", "gestion actions", "gestion obligataire", "gestion taux",
           "gestion diversifiee", "fund management", "investment management", "equity research",
           "fixed income research", "credit research", "research analyst", "investment analyst",
           "analyste investissement", "analyste credit", "analyste actions", "analyste financier",
           "multi-asset", "multi asset", "quantitative investment", "quantitative research",
           "analyse de titrisations", "risk management", "gestion des risques", "gestion actions",
           "fund analyst", "investment intern", "assistant gestion"]
MOTS_AM = ["asset management", "gestion d'actifs", "societe de gestion", "fonds", "fund",
           "etf", "portfolio", "portefeuille", "investment management", "mandat",
           "investisseurs institutionnels", "institutional investors", "asset manager",
           "gerant", "ucits", "opcvm", "buy-side", "buy side", "sicav"]
MOTS_MISSIONS = ["client", "portfolio", "portefeuille", "fund", "fonds", "analyse", "analysis",
                 "research", "investment", "investissement", "reporting", "marche", "market",
                 "allocation", "performance", "produit", "product", "commercial", "gerant"]

CLASSES_ACTIFS = [("Actions", ["equity", "equities", "actions", "action "]),
                  ("Obligations / Fixed Income", ["fixed income", "obligataire", "obligations", "bond", "credit", "taux"]),
                  ("ETF", ["etf", "indiciel", "passive"]),
                  ("Multi-Asset", ["multi-asset", "multi asset", "diversifie", "allocation d'actifs"]),
                  ("Money Market", ["money market", "monetaire"]),
                  ("Private Equity", ["private equity", "capital investissement", "capital-investissement"]),
                  ("Private Debt", ["private debt", "dette privee", "private credit"]),
                  ("Infrastructure", ["infrastructure"]),
                  ("Immobilier", ["immobilier", "real estate", "reim"])]

VILLES = [("Paris", ["paris", "ile-de-france", "ile de france", "la defense", "courbevoie", "puteaux",
                     "nanterre", "neuilly", "levallois", "boulogne-billancourt", "issy", "rueil", "montrouge"]),
          ("Londres", ["london", "londres"]),
          ("Genève", ["geneva", "geneve", "genf"]),
          ("Luxembourg", ["luxembourg"])]


def _norm(texte):
    texte = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", texte.lower()).strip()


def _contient(texte, mots):
    return [m for m in mots if m in texte]


def extraire_debut(texte, aujourd_hui=None):
    """Cherche une date de début ('juin 2027', 'starting in April'...). Renvoie (année, mois) ou None."""
    aujourd_hui = aujourd_hui or date.today()
    t = _norm(texte)
    motif = re.compile(r"\b(" + "|".join(MOIS) + r")\b(?:\s+(?:de\s+)?(20\d\d))?")
    cles = ("debut", "start", "starting", "from", "a partir", "des ", "demarrage", "commenc", "begin", "stage de", "stage en", "stage -")
    for m in motif.finditer(t):
        mois, annee = MOIS[m.group(1)], m.group(2)
        avant = t[max(0, m.start() - 30):m.start()]
        if not annee and not any(c in avant for c in cles):
            continue  # évite "may" (verbe) ou un mois cité sans lien avec le début
        if not annee:
            annee = aujourd_hui.year if mois >= aujourd_hui.month else aujourd_hui.year + 1
        return (int(annee), mois)
    return None


def _ville(lieu):
    l = _norm(lieu)
    if not l or "non precise" in l:
        return "Non précisé"
    for nom, cles in VILLES:
        if any(c in l for c in cles):
            return nom
    return "Autre : " + (lieu or "").strip()


NOMS_INUTILES = {"asset", "management", "managers", "investment", "investments", "gestion", "group", "partners"}


def _coeur(nom):
    """'Man Group' -> 'man' ; 'Amundi Asset Management' -> 'amundi' (pour comparer les noms de sociétés)."""
    base = _norm(re.sub(r"\([^)]*\)", " ", nom or ""))
    return " ".join(m for m in re.findall(r"[a-z0-9&]+", base) if m not in NOMS_INUTILES)


def _nom_exact(nom):
    """Nom complet normalisé, sans parenthèses : 'Pictet Asset Management' -> 'pictet asset management'."""
    base = _norm(re.sub(r"\([^)]*\)", " ", nom or ""))
    return " ".join(re.findall(r"[a-z0-9&]+", base))


def charger_societes(chemin=None):
    """Renvoie un ensemble de noms : 'amundi' (nom court, ambigu : peut être le groupe bancaire)
    et '=amundi asset management' (nom EXACT d'une société de ta liste : preuve forte d'Asset Management)."""
    chemin = Path(chemin) if chemin else Path(__file__).resolve().parent.parent / "data" / "companies.csv"
    noms = set()
    with open(chemin, encoding="utf-8-sig") as f:
        for ligne in csv.DictReader(f):
            coeur = _coeur(ligne["nom"])
            if coeur:
                noms.add(coeur)
            exact = _nom_exact(ligne["nom"])
            if exact:
                noms.add("=" + exact)
            for acronyme in re.findall(r"\(([^)]+)\)", ligne["nom"]):
                noms.add("=" + _nom_exact(acronyme))
    return noms


def analyser(offre, societes_connues=None, aujourd_hui=None):
    """Analyse une offre. Renvoie un dictionnaire avec la note, la catégorie, les raisons, etc."""
    societes_connues = societes_connues or set()
    titre = _norm(offre.get("titre"))
    description = _norm(offre.get("description"))
    texte = f"{titre} {description}"
    contrat = _norm(offre.get("contrat"))
    structure = _norm(offre.get("structure"))
    ville = _ville(offre.get("lieu"))
    resultat = {"retenue": False, "rejet": "", "score": 0, "categorie": "", "classe_actifs": "Non précisée",
                "ville": ville, "debut": "", "statut_date": "inconnue", "raisons": [], "alertes": []}

    def rejeter(motif):
        resultat["rejet"] = motif
        resultat["score"] = 0
        return resultat

    # 1. Est-ce un stage ?
    if contrat:
        if contrat != "stage":
            return rejeter(f"contrat : {offre.get('contrat')} (pas un stage)")
    else:
        zone = f"{titre} {description[:300]}"
        brut = f"{offre.get('titre', '')} {(offre.get('description') or '')[:300]}"
        if any(m in f" {zone} " for m in MOTS_PAS_STAGE) or re.search(r"\bVIE\b", brut):
            return rejeter("alternance / CDI / CDD / graduate programme")
        if not any(re.search(rf"\b{m}", zone) for m in MOTS_STAGE):
            return rejeter("ce n'est pas clairement un stage")

    # 2. Exclusions strictes
    for motif, nom in EXCLUSIONS_TITRE:
        if re.search(motif, titre):
            return rejeter(f"exclusion : {nom}")
    penalite = 0
    for motif, texte_alerte in SIGNAUX_DESCRIPTION:
        if re.search(motif, description):
            penalite += 10
            resultat["alertes"].append(f"La description {texte_alerte}.")

    # 3. Date de début
    debut = extraire_debut(f"{offre.get('titre', '')} {offre.get('description', '')}", aujourd_hui)
    if debut:
        resultat["debut"] = f"{NOMS_MOIS[debut[1]]} {debut[0]}"
        if debut < DEBUT_MIN or debut > DEBUT_MAX:
            return rejeter(f"début en {resultat['debut']} (hors avril-août 2027)")
        resultat["statut_date"] = "ok"
        pts_date = 15
        resultat["raisons"].append(f"Début en {resultat['debut']}, compatible avec ton calendrier.")
    else:
        pts_date = 8
        resultat["alertes"].append("Date de début non indiquée : à vérifier sur l'annonce.")

    # 4. Asset Management (30)
    pts_am = 0
    if structure == "societe de gestion":
        pts_am = 30
        resultat["raisons"].append("Société de gestion d'actifs.")
    else:
        coeur_societe = _coeur(offre.get("societe"))
        if "=" + _nom_exact(offre.get("societe")) in societes_connues:
            pts_am += 20
            resultat["raisons"].append("Société de gestion présente dans ta liste de suivi.")
        elif coeur_societe and coeur_societe in societes_connues:
            pts_am += 10  # nom court : peut désigner le groupe bancaire plutôt que sa filiale de gestion
            resultat["raisons"].append("Groupe présent dans ta liste de suivi (filiale de gestion à confirmer).")
        trouves = _contient(f"{texte} {_norm(offre.get('societe'))}", MOTS_AM)
        pts_am += 15 if len(trouves) >= 2 else 8 if len(trouves) == 1 else 0
        if trouves:
            resultat["raisons"].append("Vocabulaire Asset Management dans l'annonce.")
        pts_am = min(pts_am, 30)

    # 5. Catégorie Sales / Investment Management (25, même poids)
    sales_t, im_t = _contient(titre, MOTS_SALES), _contient(titre, MOTS_IM)
    sales_d, im_d = _contient(description, MOTS_SALES), _contient(description, MOTS_IM)
    pts_cat = 0
    if sales_t or im_t:
        pts_cat = 25
        resultat["categorie"] = "Sales Asset Management" if (sales_t and not im_t) or (sales_t and im_t and len(sales_t) >= len(im_t)) else "Investment Management"
    elif sales_d or im_d:
        pts_cat = 14
        resultat["categorie"] = "Sales Asset Management" if len(sales_d) >= len(im_d) else "Investment Management"
        resultat["alertes"].append("Catégorie déduite de la description (le titre est neutre).")
    if pts_cat:
        resultat["raisons"].append(f"Missions orientées {resultat['categorie']}.")

    # 6. Missions (15)
    if description:
        pts_missions = min(15, 5 + 2 * len(_contient(description, MOTS_MISSIONS)))
    else:
        pts_missions = 8
        resultat["alertes"].append("Pas de description complète disponible : note provisoire.")

    # 7. Localisation (15)
    if ville in ("Paris", "Londres", "Genève", "Luxembourg"):
        pts_lieu = 15
        resultat["raisons"].append(f"Localisation : {ville}.")
    elif ville == "Non précisé":
        pts_lieu = 7
        resultat["alertes"].append("Ville non précisée.")
    else:
        pts_lieu = 0
        resultat["alertes"].append(f"Localisation hors des 4 villes ciblées ({ville}).")

    # Classe d'actifs
    trouvees = [nom for nom, cles in CLASSES_ACTIFS if any(c in texte for c in cles)]
    if trouvees:
        resultat["classe_actifs"] = " / ".join(trouvees[:2])

    score = max(0, pts_am + pts_cat + pts_missions + pts_lieu + pts_date - penalite)
    if pts_am < 15:
        score = min(score, 40)
        resultat["alertes"].append("Peu de preuves d'Asset Management : note plafonnée à 40.")
    if pts_cat == 0:
        score = min(score, 40)
        resultat["alertes"].append("Ni Sales ni Investment Management détecté : note plafonnée à 40.")
    resultat["score"] = score
    resultat["retenue"] = score >= SEUIL_NOTIFICATION
    if not resultat["retenue"] and not resultat["rejet"]:
        resultat["rejet"] = f"note trop basse ({score}/100)"
    return resultat
