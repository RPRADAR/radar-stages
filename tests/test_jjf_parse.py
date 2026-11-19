"""Test sans Internet : on lit un extrait réel du flux RSS de Junior Job Finance."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import connecteur_jjf as j

XML = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>x</title>
<item><title>Assistant gestion Actions -Équipe Actions France — Amundi</title>
<link>https://jobs.amundi.com/offre-de-emploi/emploi-stage-assistant-gestion-actions_117466.aspx</link>
<description>Gestion d'actifs · Société de gestion · Paris · Stage</description>
<pubDate>Tue, 17 Nov 2026 04:51:33 GMT</pubDate></item>
<item><title>Assistant Sales Strategy – Distribution &amp; Wealth — Amundi</title>
<link>https://jobs.amundi.com/offre-de-emploi/emploi-stage-assistant-sales-strategy_117476.aspx</link>
<description>Banque privée &amp; Patrimoine · Société de gestion · Non précisé · Stage</description>
<pubDate>Tue, 17 Nov 2026 04:51:33 GMT</pubDate></item>
<item><title>Gérant Obligataire — Indosuez Wealth Management</title>
<link>https://groupecreditagricole.jobs/x</link>
<description>Gestion d'actifs · Banque d'affaires indépendante · Paris 8 · CDI/CDD</description>
<pubDate>Tue, 17 Nov 2026 04:51:33 GMT</pubDate></item>
<item><title>Family Office — Rothschild &amp; Co</title>
<link>https://rothschildandco.wd3.myworkdayjobs.com/x</link>
<description>Banque privée &amp; Patrimoine · Banque d'affaires indépendante · Paris · Stage</description>
<pubDate>Sat, 14 Nov 2026 04:52:47 GMT</pubDate></item>
<item><title>Assistant Trader Trésorerie LT — Natixis</title>
<link>https://recrutement.bpce.fr/y</link>
<description>Marchés financiers · Banque de financement &amp; d'investissement · Paris · Stage</description>
<pubDate>Sat, 14 Nov 2026 04:52:47 GMT</pubDate></item>
</channel></rss>"""


class TestJJF(unittest.TestCase):
    def test_lecture(self):
        offres = j.lire_flux(XML.encode("utf-8"))
        self.assertEqual(len(offres), 5)
        o = offres[0]
        self.assertEqual((o["societe"], o["lieu"], o["contrat"]), ("Amundi", "Paris", "Stage"))
        self.assertEqual(o["titre"], "Assistant gestion Actions -Équipe Actions France")
        self.assertEqual(o["structure"], "Société de gestion")
        self.assertEqual(o["date_publication"], "2026-11-17")
        self.assertEqual(offres[1]["titre"], "Assistant Sales Strategy – Distribution & Wealth")

    def test_filtre(self):
        offres = j.lire_flux(XML.encode("utf-8"))
        noms = [o["titre"] for o in j.candidats_gestion_actifs(offres)]
        self.assertEqual(len(noms), 2)                     # les 2 stages Amundi
        self.assertFalse(any("Gérant" in n for n in noms))  # CDI/CDD exclu
        self.assertFalse(any("Family Office" in n for n in noms))  # banque privée exclue
        self.assertFalse(any("Trader" in n for n in noms))  # trading exclu


if __name__ == "__main__":
    unittest.main(verbosity=2)
