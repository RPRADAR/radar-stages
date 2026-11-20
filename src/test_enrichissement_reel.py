"""Test réel : lit 2 vraies pages d'annonces Amundi et affiche ce que le robot en comprend."""
from enrichissement import telecharger_page, extraire_description
from scoring import extraire_debut

PAGES = [
    "https://jobs.amundi.com/offre-de-emploi/emploi-stage-assistant-sales-strategy-distribution-wealth-h-f_117476.aspx",
    "https://groupecreditagricole.jobs/fr/nos-offres-emploi/579-170464-124-stage---gestion-sous-mandat--assistant-gerant-hf-reference--2026-117530--/",
]
for url in PAGES:
    print("=" * 80)
    print(url[:90])
    try:
        texte = extraire_description(telecharger_page(url))
    except Exception as erreur:
        print(f"[ERREUR] {erreur}")
        continue
    debut = extraire_debut(texte)
    print(f"[OK] {len(texte)} caractères lus. Date de début détectée : {debut if debut else 'aucune'}")
    print("Extrait :", texte[:400].replace("\n", " | "))
