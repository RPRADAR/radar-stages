"""Tests de la notation : bonnes offres retenues, mauvaises rejetées."""
import sys, unittest
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import scoring as s

CONNUES = s.charger_societes()
AUJ = date(2026, 11, 18)


def analyse(**o):
    return s.analyser(o, CONNUES, AUJ)


class TestScoring(unittest.TestCase):
    def test_amundi_gestion_sous_mandat(self):
        r = analyse(societe="Amundi", titre="Gestion Sous Mandat Assistant Gérant", lieu="Paris",
                    contrat="Stage", structure="Société de gestion", famille="Banque privée & Patrimoine")
        self.assertTrue(r["retenue"]); self.assertEqual(r["categorie"], "Investment Management")
        self.assertEqual(r["statut_date"], "inconnue")

    def test_amundi_sales_strategy(self):
        r = analyse(societe="Amundi", titre="Assistant Sales Strategy – Distribution & Wealth",
                    lieu="Non précisé", contrat="Stage", structure="Société de gestion")
        self.assertTrue(r["retenue"]); self.assertEqual(r["categorie"], "Sales Asset Management")

    def test_blackrock_sales_juin(self):
        r = analyse(societe="BlackRock", titre="Client & Product Intern", lieu="Paris",
                    description="Internship starting June 2027. Support sales teams, prepare client meetings, analyse ETF and multi-asset investment products.")
        self.assertGreaterEqual(r["score"], 85); self.assertEqual(r["debut"], "Juin 2027")
        self.assertEqual(r["categorie"], "Sales Asset Management")

    def test_avril_accepte(self):
        r = analyse(societe="Carmignac", titre="Portfolio Management Intern", lieu="Paris",
                    description="Stage de 6 mois, début avril 2027, au sein de l'équipe de gestion de fonds actions.")
        self.assertTrue(r["retenue"]); self.assertEqual(r["debut"], "Avril 2027")

    def test_debut_trop_tot_rejete(self):
        r = analyse(societe="Amundi", titre="Assistant gestion Actions", lieu="Paris", contrat="Stage",
                    structure="Société de gestion", description="Début janvier 2027, durée 6 mois.")
        self.assertFalse(r["retenue"]); self.assertIn("hors avril-août", r["rejet"])

    def test_debut_septembre_rejete(self):
        r = analyse(societe="Schroders", titre="Equity Research Intern", lieu="London",
                    description="Internship starting September 2027 in our fund management business.")
        self.assertFalse(r["retenue"])

    def test_exclusions(self):
        for titre, motif in [("Assistant trader fixed income", "trading"), ("Analyste M&A", "M&A"),
                             ("Structuration Produits Structurés Action", "produits structurés"),
                             ("Family Office", "banque privée"), ("Global Markets - Sales", "Global Markets")]:
            r = analyse(societe="X", titre=titre, lieu="Paris", contrat="Stage", structure="Société de gestion")
            self.assertFalse(r["retenue"], titre); self.assertIn(motif, r["rejet"])

    def test_pas_un_stage(self):
        r = analyse(societe="Amundi", titre="Gérant Obligataire", contrat="CDI/CDD", structure="Société de gestion", lieu="Paris")
        self.assertFalse(r["retenue"])
        r = analyse(societe="Amundi", titre="Sales Alternance - Distribution", lieu="Paris", description="Contrat d'alternance")
        self.assertFalse(r["retenue"])

    def test_mot_cle_seul_ne_suffit_pas(self):
        r = analyse(societe="SaaSCorp", titre="Sales Intern", lieu="London",
                    description="Internship selling our cloud software to retail customers. Start June 2027.")
        self.assertFalse(r["retenue"]); self.assertLessEqual(r["score"], 40)

    def test_banque_sans_preuve_am(self):
        r = analyse(societe="BNP Paribas", titre="Sales Intern", lieu="Paris",
                    description="Internship in corporate banking supporting relationship managers.")
        self.assertFalse(r["retenue"])

    def test_stage_non_pertinent_gestion(self):
        r = analyse(societe="Sycomore Asset Management", titre="Stagiaire Communication Digitale, Vidéo & Création de Contenus - 6 mois",
                    lieu="Paris", structure="Société de gestion", contrat="Stage")
        self.assertFalse(r["retenue"])

    def test_ville_hors_zone(self):
        r = analyse(societe="Amundi", titre="Assistant gestion Actions", lieu="Rennes", contrat="Stage", structure="Société de gestion")
        self.assertFalse(r["retenue"]); self.assertIn("localisation hors des 4 villes", r["rejet"])

    def test_extraction_dates(self):
        self.assertEqual(s.extraire_debut("Start date: June 2027", AUJ), (2027, 6))
        self.assertEqual(s.extraire_debut("Stage Mars 2027 | Paris", AUJ), (2027, 3))
        self.assertEqual(s.extraire_debut("You may apply online", AUJ), None)
        self.assertEqual(s.extraire_debut("début en mai", AUJ), (2027, 5))
        self.assertEqual(s.extraire_debut("Pas de date", AUJ), None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
