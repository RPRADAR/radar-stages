"""Test réel Workday : vérifie que le robot sait lire les sites carrières Workday (Columbia Threadneedle via Ameriprise, GAM)."""
import logging
import enrichissement
from workday import collecter_workday

logging.basicConfig(level=logging.INFO, format="   (%(levelname)s) %(message)s")
SITES = [("Columbia Threadneedle", "ameriprise.wd5.myworkdayjobs.com/Ameriprise"),
         ("GAM Investments", "gam.wd3.myworkdayjobs.com/GAM")]
for nom, identifiant in SITES:
    print("=" * 80)
    print(nom, "->", identifiant)
    base = "https://" + identifiant.split("/")[0] + "/wday/cxs/"
    print("robots.txt :", "AUTORISE" if enrichissement.robots_autorise(base) else "INTERDIT (source ignorée)")
    try:
        offres = collecter_workday(identifiant, nom)
    except Exception as erreur:
        print(f"[ERREUR] {type(erreur).__name__} : {erreur}")
        continue
    print(f"[OK] {len(offres)} stages candidats trouvés")
    for o in offres[:8]:
        print(f"  - {o['titre'][:60]} | lieu : {o['lieu'][:40] or '?'} | description : {len(o['description'])} caractères")
