"""Test réel : lit le flux Junior Job Finance et note TOUS les stages.
Tu vois ce qui est retenu, et pourquoi le reste est rejeté."""
from collections import Counter
from connecteur_jjf import recuperer_offres_jjf, candidats_gestion_actifs
from scoring import analyser, charger_societes, SEUIL_NOTIFICATION

offres = recuperer_offres_jjf()
societes = charger_societes()
stages = [o for o in offres if o["contrat"].lower() == "stage"]
notes = [(o, analyser(o, societes)) for o in stages]

retenues = sorted([n for n in notes if n[1]["retenue"]], key=lambda n: -n[1]["score"])
print(f"{len(stages)} stages lus, {len(retenues)} retenus (note >= {SEUIL_NOTIFICATION}/100).\n")
for o, r in retenues:
    print(f"[{r['score']}/100] {o['societe']} | {o['titre']} | {r['ville']} | {r['categorie']} | début : {r['debut'] or 'inconnu'}")
    print(f"         {o['url']}")
    for a in r["alertes"]:
        print(f"         ! {a}")

print("\nMotifs de rejet les plus fréquents :")
for motif, nb in Counter(r["rejet"].split(" (")[0] for _, r in notes if not r["retenue"]).most_common(6):
    print(f"  {nb} x {motif}")

print("\nStages en gestion d'actifs REJETÉS (à vérifier, pour détecter une erreur de ma part) :")
for o in candidats_gestion_actifs(offres):
    r = analyser(o, societes)
    if not r["retenue"]:
        print(f"- {o['societe']} | {o['titre']} -> {r['rejet']}")
