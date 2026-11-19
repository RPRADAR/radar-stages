"""Test réel : lit le flux de Junior Job Finance et affiche les stages en gestion d'actifs."""
from connecteur_jjf import recuperer_offres_jjf, candidats_gestion_actifs

try:
    offres = recuperer_offres_jjf()
except Exception as erreur:
    print(f"[ERREUR] impossible de lire le flux : {erreur}")
else:
    stages = [o for o in offres if o["contrat"].lower() == "stage"]
    candidats = candidats_gestion_actifs(offres)
    print(f"[OK] {len(offres)} offres dans le flux, dont {len(stages)} stages.")
    print(f"Stages en société de gestion / gestion d'actifs : {len(candidats)}\n")
    for o in candidats:
        print(f"- {o['societe']} | {o['titre']} | {o['lieu']} | {o['url']}")
