"""Tests de la lecture des alertes LinkedIn / Indeed (emails fabriqués, sans données personnelles)."""
import sys, tempfile, unittest
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import alertes_email as a
import base_donnees as bd
import radar
import scoring as s

NBSP = "\u00a0"
LINKEDIN = f"""Votre alerte Emploi pour Stagiaire (Paris)
De nouvelles offres d’emploi correspondent à vos préférences.
Gérer les alertes : https://www.linkedin.com/comm/jobs/alerts?x=1

Sales Intern
BlackRock
Paris

Cette entreprise recrute activement
Voir l’offre d’emploi : https://www.linkedin.com/comm/jobs/view/1111111111/?trackingId=abc&refId=def

---------------------------------------------------------

2027 Internship – GWM International Germany & Austria UHNW – Zurich
UBS
Zurich

Cette entreprise recrute activement
Voir l’offre d’emploi : https://www.linkedin.com/comm/jobs/view/2222222222/?trackingId=abc

---------------------------------------------------------

Portfolio Management Intern
Schroders
London

1{NBSP}relation
Voir l’offre d’emploi : https://www.linkedin.com/comm/jobs/view/3333333333/?trackingId=abc
"""

INDEED = """Alerte Emploi Indeed
2 nouveaux emplois stage gestion
Voir les résultats correspondants sur Indeed : https://fr.indeed.com/jobs?q=stage

Stage - Assistant sales asset management F/H
PRO BTP GROUPE - Paris 11e (75)
Candidature simplifiée
Stage à pourvoir dès avril 2027 pour 6 mois. Mettre à jour des questionnaires de Due Diligence des fonds.
il y a 2 jours
https://fr.indeed.com/rc/clk/dl?jk=aaaabbbbcccc1111&from=ja&tk=zzz

Stage - Assistant sales asset management F/H
PRO BTP GROUPE - Paris 11e (75)
Stage à pourvoir dès janvier 2027. Due Diligence des fonds.
il y a 1 jour
https://fr.indeed.com/pagead/clk/dl?mo=r&ad=-XYZ&alid=123
"""


def mail(expediteur, texte, date="Wed, 18 Nov 2026 09:05:45 +0000"):
    m = EmailMessage()
    m["From"], m["Subject"], m["Date"] = expediteur, "alerte", date
    m.set_content(texte)
    return m


class TestAlertes(unittest.TestCase):
    def test_linkedin(self):
        offres = a.analyser_linkedin(LINKEDIN)
        self.assertEqual(len(offres), 3)
        self.assertEqual((offres[0]["titre"], offres[0]["societe"], offres[0]["lieu"]), ("Sales Intern", "BlackRock", "Paris"))
        self.assertEqual(offres[0]["url"], "https://www.linkedin.com/jobs/view/1111111111/")
        self.assertEqual(offres[0]["id_source"], "linkedin:1111111111")
        self.assertEqual((offres[2]["titre"], offres[2]["societe"], offres[2]["lieu"]), ("Portfolio Management Intern", "Schroders", "London"))

    def test_indeed(self):
        offres = a.analyser_indeed(INDEED, datetime(2026, 11, 18, tzinfo=timezone.utc))
        self.assertEqual(len(offres), 2)
        o = offres[0]
        self.assertEqual((o["societe"], o["lieu"]), ("PRO BTP GROUPE", "Paris 11e (75)"))
        self.assertEqual(o["url"], "https://fr.indeed.com/viewjob?jk=aaaabbbbcccc1111")
        self.assertEqual(o["date_publication"], "2026-11-16")
        self.assertIn("avril 2027", o["description"]); self.assertNotIn("Candidature simplifiée", o["description"])
        self.assertTrue(offres[1]["id_source"].startswith("indeed:h"))  # offre sponsorisée : identifiant calculé
        self.assertEqual(offres[1]["id_source"], a.analyser_indeed(INDEED)[1]["id_source"])  # stable d'un email à l'autre

    def test_reconnaissance_expediteur(self):
        self.assertEqual(len(a.offres_depuis_message(mail("Alertes LinkedIn Jobs <jobalerts-noreply@linkedin.com>", LINKEDIN))[0]), 3)
        self.assertTrue(a.offres_depuis_message(mail("Indeed <donotreply@jobalert.indeed.com>", INDEED))[1])
        offres, reconnu = a.offres_depuis_message(mail("newsletter@exemple.com", "Bonjour, promo !"))
        self.assertEqual((offres, reconnu), ([], False))
        # email transféré à la main : l'expéditeur est toi, mais le contenu est reconnu
        offres, reconnu = a.offres_depuis_message(mail("moi@gmail.com", "---------- Forwarded message ---------\nFrom: jobalerts-noreply@linkedin.com\n\n" + LINKEDIN))
        self.assertTrue(reconnu); self.assertEqual(len(offres), 3)

    def test_notation_des_alertes(self):
        societes = s.charger_societes()
        li = {o["id_source"]: s.analyser(o, societes) for o in a.analyser_linkedin(LINKEDIN)}
        self.assertTrue(li["linkedin:1111111111"]["retenue"])       # Sales Intern chez BlackRock, Paris
        self.assertFalse(li["linkedin:2222222222"]["retenue"])      # UBS gestion de fortune (hors cahier des charges)
        self.assertTrue(li["linkedin:3333333333"]["retenue"])       # Portfolio Management Intern chez Schroders
        ind = a.analyser_indeed(INDEED, datetime(2026, 11, 18, tzinfo=timezone.utc))
        r_avril, r_janvier = s.analyser(ind[0], societes), s.analyser(ind[1], societes)
        self.assertTrue(r_avril["retenue"]); self.assertEqual(r_avril["debut"], "Avril 2027")
        self.assertFalse(r_janvier["retenue"]); self.assertIn("hors avril-août", r_janvier["rejet"])

    def test_alertes_ne_font_pas_disparaitre_les_offres(self):
        db = Path(tempfile.mkdtemp()) / "t.db"
        offre = a.analyser_linkedin(LINKEDIN)[0]
        envoi = lambda *x: None
        radar.executer(db, [(radar.SOURCE_ALERTES, lambda: [dict(offre)])], envoi, s.charger_societes(), verifier_liens=False)
        radar.executer(db, [(radar.SOURCE_ALERTES, lambda: [])], envoi, s.charger_societes(), verifier_liens=False)  # plus d'email récent
        conn = bd.ouvrir(db)
        self.assertEqual(conn.execute("SELECT actif FROM offres").fetchone()[0], 1)

    def test_exact_vs_groupe(self):
        societes = s.charger_societes()
        base = {"titre": "Sales Intern", "lieu": "Paris", "description": ""}
        self.assertTrue(s.analyser(dict(base, societe="BlackRock"), societes)["retenue"])
        self.assertFalse(s.analyser(dict(base, societe="BNP Paribas"), societes)["retenue"])  # groupe bancaire : filiale de gestion à confirmer
        self.assertFalse(s.analyser(dict(base, societe="Entreprise Inconnue SA"), societes)["retenue"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
