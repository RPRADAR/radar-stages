"""Tests sans Internet du détecteur de plateformes."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import detecter_plateformes as d


class Faux:
    def __init__(self, code, data): self.status_code, self.data = code, data
    def json(self): return self.data


class TestDetecteur(unittest.TestCase):
    def test_variantes(self):
        self.assertIn("amundi", d.variantes("Amundi Luxembourg"))
        v = d.variantes("La Financière de l'Échiquier (LFDE)")
        self.assertIn("lfde", v)
        self.assertIn("lafinancieredelechiquier", v)
        self.assertIn("mginvestments", d.variantes("M&G Investments"))
        self.assertTrue(all(len(x) >= 3 for x in d.variantes("DWS")))

    def test_detection_greenhouse(self):
        def faux_get(url, **kw):
            if "greenhouse" in url and "/carmignac/" in url:
                return Faux(200, {"jobs": [{"title": "Sales Intern", "location": {"name": "Paris"}},
                                           {"title": "Analyst", "location": {"name": "Londres"}}]})
            return Faux(404, {})
        with patch("detecter_plateformes.requests.get", side_effect=faux_get):
            r = d.tester(("Carmignac", "greenhouse", "carmignac"))
            self.assertEqual((r["nb_offres"], r["nb_stages"]), (2, 1))
            self.assertIsNone(d.tester(("Carmignac", "lever", "carmignac")))

    def test_erreur_reseau_ignoree(self):
        with patch("detecter_plateformes.requests.get", side_effect=Exception("coupure")):
            self.assertIsNone(d.tester(("X", "ashby", "xxx")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
