"""Test réel : lit 2 vraies pages d'annonces Amundi / Crédit Agricole et affiche ce que le robot en comprend."""
import re
import requests
from enrichissement import telecharger_page, extraire_description, robots_autorise, RobotsInterdit, EN_TETES
from scoring import extraire_debut

PAGES = [
    "https://jobs.amundi.com/offre-de-emploi/emploi-stage-assistant-sales-strategy-distribution-wealth-h-f_117476.aspx",
    "https://groupecreditagricole.jobs/fr/nos-offres-emploi/579-170464-124-stage---gestion-sous-mandat--assistant-gerant-hf-reference--2026-117530--/",
]
for url in PAGES:
    print("=" * 80)
    print(url[:90])
    print("robots.txt du site :", "AUTORISE" if robots_autorise(url) else "INTERDIT (le robot ne lira pas cette page)")
    try:
        texte = extraire_description(telecharger_page(url))
    except RobotsInterdit:
        print("-> Page ignorée volontairement : le site demande aux robots de ne pas la lire.")
        continue
    except Exception as erreur:
        print(f"[ERREUR] {erreur}")
        continue
    debut = extraire_debut(texte)
    print(f"[OK] {len(texte)} caractères lus. Date de début détectée : {debut if debut else 'aucune'}")
    if not debut:
        # Diagnostic : on cherche toute ligne de la page qui parle de date ou de début
        complet = extraire_description(requests.get(url, headers=EN_TETES, timeout=15).text, depuis_le_marqueur=False)
        lignes = [l for l in complet.splitlines() if re.search(r"date|d[ée]but|prise de|start|dès", l, re.I)]
        print("Lignes de la page qui parlent de date ou de début :")
        for l in lignes[:12]:
            print("   *", l[:160])
