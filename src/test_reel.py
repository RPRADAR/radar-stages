"""
Test réel : vérifie que ton PC arrive à lire de vraies offres sur Internet.
On teste sur des entreprises quelconques (ce n'est pas de l'asset management),
uniquement pour vérifier que le code et ta connexion fonctionnent.
"""
from connecteurs import recuperer_offres

TESTS = [
    ("greenhouse", "stripe", "Stripe (test)"),
    ("lever", "spotify", "Spotify (test)"),
]

for plateforme, identifiant, nom in TESTS:
    try:
        offres = recuperer_offres(plateforme, identifiant, nom)
        print(f"[OK] {plateforme} / {nom} : {len(offres)} offres lues")
        if offres:
            o = offres[0]
            print(f"     exemple : {o['titre']} | {o['lieu']} | {o['url']}")
    except Exception as erreur:
        print(f"[ERREUR] {plateforme} / {nom} : {erreur}")
