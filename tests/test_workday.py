"""Tests du connecteur Workday avec de fausses réponses (sans Internet)."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import connecteurs
import scoring as s
import workday as wd

ID = "ameriprise.wd5.myworkdayjobs.com/Ameriprise"
BASE = "https://ameriprise.wd5.myworkdayjobs.com/wday/cxs/ameriprise/Ameriprise"

POSTES = {
    "intern": [
        {"title": "Investment Analyst Intern", "externalPath": "/job/London/Investment-Analyst-Intern_R1001", "locationsText": "London, United Kingdom",
         "postedOn": "Posted 3 Days Ago", "bulletFields": ["R1001"]},
        {"title": "Sales Support Intern", "externalPath": "/job/Multiple/Sales-Support-Intern_R1002", "locationsText": "2 Locations",
         "postedOn": "Posted Today", "bulletFields": ["R1002"]},
        {"title": "Financial Advisor Intern", "externalPath": "/job/Minneapolis/Advisor-Intern_R1003", "locationsText": "Minneapolis, MN",
         "postedOn": "Posted 5 Days Ago", "bulletFields": ["R1003"]},
        {"title": "Senior Portfolio Manager", "externalPath": "/job/London/Senior-PM_R1004", "locationsText": "London", "postedOn": "Posted Today", "bulletFields": ["R1004"]},
        {"title": "Apprentice Analyst Intern", "externalPath": "/job/London/Apprentice_R1005", "locationsText": "London", "postedOn": "Posted Today", "bulletFields": ["R1005"]},
    ],
    "London intern": [
        {"title": "Investment Analyst Intern", "externalPath": "/job/London/Investment-Analyst-Intern_R1001", "locationsText": "London, United Kingdom",
         "postedOn": "Posted 3 Days Ago", "bulletFields": ["R1001"]},   # doublon : même offre trouvée par une autre recherche
    ],
}
DETAILS = {
    "/job/London/Investment-Analyst-Intern_R1001": {"jobPostingInfo": {"jobDescription": "&lt;p&gt;Support the equity research team: analyse companies and funds, "
        "build financial models and portfolio reports.&lt;/p&gt;", "startDate": "2027-05-04", "externalUrl": "https://ameriprise.wd5.myworkdayjobs.com/en-US/Ameriprise/job/London/Investment-Analyst-Intern_R1001"}},
    "/job/Multiple/Sales-Support-Intern_R1002": {"jobPostingInfo": {"jobDescription": "<p>Support the institutional sales team for our funds and client reporting.</p>",
        "location": "Paris, France", "additionalLocations": ["Luxembourg, Luxembourg"]}},
    "/job/Minneapolis/Advisor-Intern_R1003": {"jobPostingInfo": {"jobDescription": "<p>Help financial advisors with client portfolios.</p>"}},
}


class Rep:
    def __init__(self, data): self.data = data
    def raise_for_status(self): pass
    def json(self): return self.data


class Faux:
    def __init__(self): self.posts, self.gets = [], []
    def post(self, url, json=None, **kw):
        self.posts.append(json["searchText"])
        liste = POSTES.get(json["searchText"], [])
        return Rep({"total": len(liste), "jobPostings": liste[json["offset"]:json["offset"] + 20]})
    def get(self, url, **kw):
        self.gets.append(url)
        return Rep(DETAILS[url.replace(BASE, "")])


class TestWorkday(unittest.TestCase):
    def setUp(self):
        wd.CACHE_DESCRIPTION = None
        self.faux = Faux()

    def collecter(self, robots=lambda u: True):
        return wd.collecter_workday(ID, "Columbia Threadneedle", post=self.faux.post, get=self.faux.get, robots=robots)

    def test_titres_stage_uniquement_et_doublons(self):
        titres = sorted(o["titre"] for o in self.collecter())
        self.assertEqual(titres, ["Financial Advisor Intern", "Investment Analyst Intern", "Sales Support Intern"])  # ni "Senior PM" ni "Apprentice"

    def test_details(self):
        o = {x["id_source"]: x for x in self.collecter()}
        a = o["workday:ameriprise.wd5.myworkdayjobs.com:R1001"]
        self.assertIn("Start date: 2027-05-04", a["description"]); self.assertIn("equity research", a["description"])
        self.assertEqual(a["lieu"], "London, United Kingdom"); self.assertTrue(a["url"].endswith("Investment-Analyst-Intern_R1001"))
        self.assertRegex(a["date_publication"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(o["workday:ameriprise.wd5.myworkdayjobs.com:R1002"]["lieu"], "Paris, France | Luxembourg, Luxembourg")   # "2 Locations" remplacé

    def test_notation(self):
        societes = s.charger_societes()
        r = {o["titre"]: s.analyser(o, societes) for o in self.collecter()}
        self.assertTrue(r["Investment Analyst Intern"]["retenue"]); self.assertEqual(r["Investment Analyst Intern"]["debut"], "Mai 2027")
        self.assertTrue(r["Sales Support Intern"]["retenue"])
        self.assertFalse(r["Financial Advisor Intern"]["retenue"]); self.assertIn("localisation", r["Financial Advisor Intern"]["rejet"])

    def test_robots_interdit(self):
        self.assertEqual(self.collecter(robots=lambda u: False), [])
        self.assertEqual(self.faux.posts, [])                      # aucune requête envoyée

    def test_cache_evite_de_relire(self):
        wd.CACHE_DESCRIPTION = lambda i: "Description déjà connue" if i.endswith("R1001") else ""
        self.collecter()
        self.assertFalse(any("R1001" in u for u in self.faux.gets))
        self.assertTrue(any("R1002" in u for u in self.faux.gets))  # offre inconnue : lue

    def test_enregistre_dans_les_connecteurs(self):
        self.assertIs(connecteurs.CONNECTEURS["workday"], wd.collecter_workday)


if __name__ == "__main__":
    unittest.main(verbosity=2)
