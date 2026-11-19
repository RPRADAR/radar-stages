"""Tests automatiques sans Internet : on fournit de fausses réponses aux connecteurs."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import connecteurs


class FauxJson:
    def __init__(self, data): self.data = data
    def raise_for_status(self): pass
    def json(self): return self.data


class TestConnecteurs(unittest.TestCase):
    def test_greenhouse(self):
        faux = {"jobs": [{"id": 1, "title": "Sales Intern", "absolute_url": "https://x/1",
                          "location": {"name": "Paris"}, "first_published": "2026-11-18T09:00:00Z",
                          "content": "&lt;p&gt;Stage &lt;b&gt;Sales&lt;/b&gt; en gestion d&#39;actifs&lt;/p&gt;"}]}
        with patch("connecteurs.requests.get", return_value=FauxJson(faux)):
            o = connecteurs.recuperer_offres("greenhouse", "x", "Test")[0]
        self.assertEqual(o["titre"], "Sales Intern")
        self.assertEqual(o["lieu"], "Paris")
        self.assertEqual(o["date_publication"], "2026-11-18")
        self.assertEqual(o["description"], "Stage Sales en gestion d'actifs")

    def test_lever(self):
        faux = [{"id": "abc", "text": "Portfolio Management Intern", "hostedUrl": "https://y/abc",
                 "categories": {"location": "London"}, "createdAt": 1795000000000,
                 "descriptionPlain": "Internship"}]
        with patch("connecteurs.requests.get", return_value=FauxJson(faux)):
            o = connecteurs.recuperer_offres("lever", "y", "Test")[0]
        self.assertEqual(o["id_source"], "lever:abc")
        self.assertEqual(o["lieu"], "London")
        self.assertTrue(o["date_publication"].startswith("20"))

    def test_ashby(self):
        faux = {"jobs": [{"id": "z", "title": "Equity Research Intern", "location": "Geneva",
                          "jobUrl": "https://z", "descriptionPlain": "desc", "publishedAt": "2026-11-17T08:00:00Z"}]}
        with patch("connecteurs.requests.get", return_value=FauxJson(faux)):
            o = connecteurs.recuperer_offres("ashby", "z", "Test")[0]
        self.assertEqual(o["date_publication"], "2026-11-17")

    def test_smartrecruiters(self):
        liste = {"content": [{"id": "9", "name": "Fund Sales Intern", "ref": "https://api/9",
                              "location": {"city": "Luxembourg", "country": "lu"}, "releasedDate": "2026-11-16T10:00:00Z"}]}
        detail = {"jobAd": {"sections": {"jobDescription": {"text": "<p>Mission</p>"}}}}
        reponses = [FauxJson(liste), FauxJson(detail)]
        with patch("connecteurs.requests.get", side_effect=reponses):
            o = connecteurs.recuperer_offres("smartrecruiters", "s", "Test")[0]
        self.assertEqual(o["lieu"], "Luxembourg, lu")
        self.assertEqual(o["description"], "Mission")

    def test_plateforme_inconnue(self):
        with self.assertRaises(ValueError):
            connecteurs.recuperer_offres("inconnue", "x", "Test")


if __name__ == "__main__":
    unittest.main(verbosity=2)
