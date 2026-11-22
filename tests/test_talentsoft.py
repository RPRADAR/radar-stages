"""Tests du connecteur Talentsoft (Candriam) avec des flux fabriqués sur le modèle des vrais flux, sans Internet."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import connecteurs
import scoring as s
import talentsoft as ts

H = "jobs.candriam.com"
PAGE_FLUX = f"""<html><body><h1>RSS and other feeds</h1><h2>Contract type</h2><ul>
<li><a href="https://{H}/handlers/offerRss.ashx?LCID=2057&Rss_Contract=2642"><img alt="x"/> Permanent</a></li>
<li><a href="https://{H}/handlers/offerRss.ashx?LCID=2057&Rss_Contract=2644"><img alt="x"/> Internship</a></li>
<li><a href="https://{H}/handlers/offerRss.ashx?LCID=2057&Rss_Contract=2640"><img alt="x"/> Contract of apprenticeship</a></li>
<li><a href="https://{H}/handlers/offerRss.ashx?LCID=2057&Rss_Contract=2647"><img alt="x"/> VIE</a></li></ul>
<h2>Country</h2><ul>
<li><a href="https://{H}/handlers/offerRss.ashx?LCID=2057&Rss_JobCountry=79"><img alt="x"/> France</a></li>
<li><a href="https://{H}/handlers/offerRss.ashx?LCID=2057&Rss_JobCountry=119"><img alt="x"/> Luxembourg</a></li>
<li><a href="https://{H}/handlers/offerRss.ashx?LCID=2057&Rss_JobCountry=91"><img alt="x"/> The Netherlands</a></li></ul></body></html>"""


def item(id_, ref, titre, desc, date="Tue, 10 Nov 2026 15:59:21 Z"):
    return (f"<item><link>https://{H}/Pages/Offre/detailoffre.aspx?idOffre={id_}&amp;idOrigine=502&amp;LCID=2057</link>"
            f"<category>Internship</category><title>{ref} - {titre}</title><description>{desc}</description><pubDate>{date}</pubDate></item>")


def rss(*items):
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>x</title>' + "".join(items) + "</channel></rss>").encode()


D456 = ("&lt;b&gt;Business unit : &lt;/b&gt;Investment Management/Investment Management&lt;br /&gt;&lt;b&gt;Contract type : &lt;/b&gt;Internship&lt;br /&gt;"
        "&lt;b&gt;Position description : &lt;/b&gt;&lt;br /&gt;Directly reporting to the Client Portfolio Manager of the Alternative Investments Platform, "
        "the CPM Assistant will closely work with the fund managers. Develop marketing content for the funds, liaise with portfolio managers "
        "and Client Relationship Managers, update the funds&#8217; marketing materials, respond to client enquiries and RFPs.&lt;br /&gt;")
D452 = ("&lt;b&gt;Business unit : &lt;/b&gt;Investment Management/Multi-Asset&lt;br /&gt;&lt;b&gt;Contract type : &lt;/b&gt;Internship&lt;br /&gt;"
        "&lt;b&gt;Position description : &lt;/b&gt;&lt;br /&gt;The intern will conduct due diligence on Private Asset and Hedge funds, monitor existing funds "
        "and write investment memos for the investment committee.&lt;br /&gt;")
D450 = ("&lt;b&gt;Business unit : &lt;/b&gt;Sales and Distribution/Client Relations&lt;br /&gt;&lt;b&gt;Contract type : &lt;/b&gt;Internship&lt;br /&gt;"
        "&lt;b&gt;Position description : &lt;/b&gt;&lt;br /&gt;Starting in February 2027, as an Intern in Client Relationship Support, you will join "
        "Candriam&#8217;s Dutch Sales team and support institutional asset management client meetings.&lt;br /&gt;")
D453 = ("&lt;b&gt;Business unit : &lt;/b&gt;Investment Management/Sustainable Investing&lt;br /&gt;&lt;b&gt;Contract type : &lt;/b&gt;Internship&lt;br /&gt;"
        "&lt;b&gt;Position description : &lt;/b&gt;&lt;br /&gt;The team is seeking an intern to support ESG and impact methodologies.&lt;br /&gt;")

FLUX = {
    f"https://{H}/handlers/offerRss.ashx?LCID=2057&Rss_Contract=2644": rss(
        item(456, "2026-456", "Client Portfolio Manager Alternative Intern F/M", D456),
        item(453, "2026-453", "Climate &amp; Biodiversity Analyst Intern F/M", D453),
        item(452, "2026-452", "Fund Analyst - External Multi Management Intern F/M", D452),
        item(450, "2026-450", "Client Relationship Support Intern F/M", D450)),
    f"https://{H}/handlers/offerRss.ashx?LCID=2057&Rss_JobCountry=79": rss(
        item(456, "2026-456", "x", ""), item(453, "2026-453", "x", ""), item(452, "2026-452", "x", "")),
    f"https://{H}/handlers/offerRss.ashx?LCID=2057&Rss_JobCountry=119": rss(),
}


class Rep:
    def __init__(self, contenu, code=200):
        self.content, self.status_code = contenu, code
        self.text = contenu.decode() if isinstance(contenu, bytes) else contenu
        self.url = ""
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(self.status_code)


def faux_get(url, **kw):
    if url.endswith("/job/all-rss-feeds.aspx"):
        return Rep(PAGE_FLUX)
    if url in FLUX:
        return Rep(FLUX[url])
    return Rep(b"", 404)


class TestTalentsoft(unittest.TestCase):
    def setUp(self):
        import unittest.mock as m
        patch = m.patch("talentsoft.requests.get", side_effect=faux_get)
        patch.start()
        self.addCleanup(patch.stop)

    def test_decouverte(self):
        contrats, pays = ts.decouvrir_flux(H, faux_get)
        self.assertIn("Internship", contrats); self.assertIn("France", pays)
        self.assertTrue(contrats["Internship"].endswith("Rss_Contract=2644"))

    def test_lecture_flux(self):
        o = ts.lire_flux(FLUX[f"https://{H}/handlers/offerRss.ashx?LCID=2057&Rss_Contract=2644"])[0]
        self.assertEqual((o["id"], o["reference"], o["titre"], o["date"]), ("456", "2026-456", "Client Portfolio Manager Alternative Intern F/M", "2026-11-10"))
        self.assertIn("Business unit : Investment Management", o["description"]); self.assertNotIn("<b>", o["description"])

    def test_collecte_et_pays(self):
        offres = {o["id_source"]: o for o in connecteurs.recuperer_offres("talentsoft", H, "Candriam")}
        self.assertEqual(len(offres), 4)                              # seuls les stages (pas l'alternance, ni le VIE)
        self.assertEqual(offres[f"talentsoft:{H}:456"]["lieu"], "France")
        self.assertEqual(offres[f"talentsoft:{H}:450"]["lieu"], "Hors zone ciblée")
        self.assertEqual(offres[f"talentsoft:{H}:456"]["contrat"], "Stage")

    def test_notation_candriam(self):
        societes = s.charger_societes()
        r = {o["id_source"].split(":")[-1]: s.analyser(o, societes) for o in self._offres()}
        self.assertTrue(r["456"]["retenue"]); self.assertEqual(r["456"]["categorie"], "Investment Management")
        self.assertTrue(r["452"]["retenue"])
        # analyste ESG dans l'unité « Investment Management » : retenu, mais moins bien noté (catégorie déduite de la description)
        self.assertTrue(r["453"]["retenue"]); self.assertLess(r["453"]["score"], r["456"]["score"])
        self.assertTrue(any("déduite de la description" in a for a in r["453"]["alertes"]))
        self.assertFalse(r["450"]["retenue"]); self.assertIn("localisation", r["450"]["rejet"])   # Pays-Bas

    def _offres(self):
        return ts.collecter_talentsoft(H, "Candriam")

    def test_site_sans_flux(self):
        with self.assertRaises(RuntimeError):
            ts.decouvrir_flux("site.exemple", lambda *a, **k: Rep(b"", 404))


if __name__ == "__main__":
    unittest.main(verbosity=2)
