"""Tests de la couche de données du tableau de bord (sans Internet)."""
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import pandas as pd
import radar
import donnees_dashboard as dd

BON = {"societe": "Amundi", "plateforme": "jjf", "id_source": "jjf:u1", "titre": "Assistant gestion Actions", "lieu": "Paris",
       "url": "https://exemple.fr/1", "description": "", "date_publication": "2026-11-17",
       "famille": "Gestion d'actifs", "structure": "Société de gestion", "contrat": "Stage"}
MAUVAIS = dict(BON, id_source="jjf:u2", societe="HSBC", titre="Assistant trader fixed income", structure="Banque")


class TestDashboard(unittest.TestCase):
    def setUp(self):
        dossier = Path(tempfile.mkdtemp())
        self.db, self.csv = dossier / "b.db", dossier / "c.csv"
        radar.executer(self.db, [("jjf", lambda: [dict(BON), dict(MAUVAIS)])], lambda *a: None, {"amundi"}, verifier_liens=False)

    def test_lecture_offres(self):
        o = dd.charger_offres(self.db, self.csv)
        self.assertEqual(len(o), 1); self.assertEqual(o[0]["Entreprise"], "Amundi")
        self.assertEqual(o[0]["Statut"], "À postuler"); self.assertEqual(o[0]["Lien"], "https://exemple.fr/1")
        self.assertEqual(len(dd.charger_offres(self.db, self.csv, inclure_rejetees=True)), 2)

    def test_statuts_conserves(self):
        dd.sauver_statuts({"jjf:u1": "Candidature envoyée"}, self.csv)
        self.assertEqual(dd.charger_offres(self.db, self.csv)[0]["Statut"], "Candidature envoyée")
        dd.sauver_statuts({"jjf:u1": "À postuler"}, self.csv)
        self.assertEqual(dd.charger_statuts(self.csv), {})

    def test_etat_robot(self):
        derniere, hist = dd.etat_robot(self.db)
        self.assertEqual(derniere["statut"], "ok"); self.assertEqual(hist[0]["Type"], "offres")

    def test_preferences_colonnes(self):
        chemin = self.csv.parent / "p.json"
        self.assertEqual(dd.charger_preferences(chemin), {})
        dd.sauver_preferences({"colonnes": ["Publication", "Score"]}, chemin)
        self.assertEqual(dd.charger_preferences(chemin)["colonnes"], ["Publication", "Score"])

    def test_export_excel_csv(self):
        df = pd.DataFrame(dd.charger_offres(self.db, self.csv))
        import io
        t = io.BytesIO(); df.to_excel(t, index=False, engine="openpyxl")
        self.assertGreater(len(t.getvalue()), 1000)
        self.assertIn("Amundi", df.to_csv(index=False, sep=";"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
