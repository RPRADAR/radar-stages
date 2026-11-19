"""Tests du robot complet, sans Internet et sans vrai email : fausses sources, faux envoi."""
import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import base_donnees as bd
import emailing
import radar

BON = {"societe": "Amundi", "plateforme": "jjf", "id_source": "jjf:u1", "titre": "Assistant gestion Actions", "lieu": "Paris",
       "url": "https://exemple.fr/1", "description": "", "date_publication": "2026-11-17",
       "famille": "Gestion d'actifs", "structure": "Société de gestion", "contrat": "Stage"}
MAUVAIS = dict(BON, id_source="jjf:u2", societe="HSBC", titre="Assistant trader fixed income", url="https://exemple.fr/2",
               structure="Banque", contrat="Stage")
ALTERNANCE = dict(BON, id_source="jjf:u3", titre="Gestion de portefeuille", contrat="Alternance", url="https://exemple.fr/3")


class Envoi:
    def __init__(self, echec=False): self.mails, self.echec = [], echec
    def __call__(self, objet, texte, corps):
        if self.echec: raise RuntimeError("SMTP indisponible")
        self.mails.append((objet, texte))


def source(offres):
    return lambda: [dict(o) for o in offres]


def source_en_panne():
    raise ConnectionError("site inaccessible")


class TestRobot(unittest.TestCase):
    def setUp(self):
        self.db = Path(tempfile.mkdtemp()) / "t.db"
        self.societes = {"amundi"}

    def run_(self, sources, envoi):
        return radar.executer(self.db, sources, envoi, self.societes, verifier_liens=False)

    def test_nouvelle_offre_puis_ras(self):
        e = Envoi()
        r1 = self.run_([("jjf", source([BON, MAUVAIS, ALTERNANCE]))], e)
        self.assertEqual(r1["type_email"], "offres"); self.assertEqual(r1["nb_a_notifier"], 1)
        self.assertEqual(e.mails[0][0], emailing.OBJET_OFFRES)
        self.assertIn("Entreprise : AMUNDI", e.mails[0][1]); self.assertIn("Score de pertinence", e.mails[0][1])
        self.assertIn("https://exemple.fr/1", e.mails[0][1]); self.assertNotIn("trader", e.mails[0][1].lower())
        r2 = self.run_([("jjf", source([BON, MAUVAIS, ALTERNANCE]))], e)   # rien de neuf -> RAS, et pas de doublon
        self.assertEqual(r2["type_email"], "ras"); self.assertEqual(e.mails[1][0], emailing.OBJET_RAS)
        self.assertIn("Dernière vérification", e.mails[1][1])

    def test_panne_totale_pas_de_ras(self):
        e = Envoi()
        r = self.run_([("jjf", source_en_panne)], e)
        self.assertEqual(r["type_email"], "erreur"); self.assertEqual(e.mails[0][0], emailing.OBJET_ERREUR)
        self.assertIn("site inaccessible", e.mails[0][1]); self.assertNotEqual(e.mails[0][0], emailing.OBJET_RAS)

    def test_panne_partielle_jamais_ras(self):
        e = Envoi()
        r = self.run_([("jjf", source([])), ("lever:x", source_en_panne)], e)
        self.assertEqual(r["type_email"], "partiel"); self.assertNotEqual(e.mails[0][0], emailing.OBJET_RAS)

    def test_panne_partielle_avec_offre(self):
        e = Envoi()
        r = self.run_([("jjf", source([BON])), ("lever:x", source_en_panne)], e)
        self.assertEqual(r["type_email"], "offres"); self.assertIn("Sources en erreur", e.mails[0][1])

    def test_echec_envoi_reessaye_ensuite(self):
        r1 = self.run_([("jjf", source([BON]))], Envoi(echec=True))
        self.assertFalse(r1["envoye"])
        e = Envoi()
        r2 = self.run_([("jjf", source([BON]))], e)     # l'offre n'avait pas été marquée "envoyée"
        self.assertEqual(r2["type_email"], "offres"); self.assertEqual(len(e.mails), 1)

    def test_republication_et_modification(self):
        e = Envoi()
        self.run_([("jjf", source([BON]))], e)
        r = self.run_([("jjf", source([]))], e)                       # l'offre disparaît
        self.assertEqual(r["type_email"], "ras")
        r = self.run_([("jjf", source([BON]))], e)                    # elle revient : republiée -> renotifiée
        self.assertEqual((r["republiees"], r["type_email"]), (1, "offres"))
        self.assertIn("(republiée)", e.mails[-1][1])
        r = self.run_([("jjf", source([dict(BON, description="Nouvelle description")]))], e)
        self.assertEqual(r["modifiees"], 1)                           # modification détectée, pas de nouvel email d'offre
        self.assertEqual(r["type_email"], "ras")

    def test_doublon_entre_sources(self):
        e = Envoi()
        autre = dict(BON, id_source="smartrecruiters:99", url="https://autre.fr/99", plateforme="smartrecruiters")
        r = self.run_([("jjf", source([BON])), ("smartrecruiters:amundi", source([autre]))], e)
        self.assertEqual((r["nouvelles"], r["doublons"], r["nb_a_notifier"]), (1, 1, 1))
        conn = bd.ouvrir(self.db)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM offres").fetchone()[0], 1)
        self.assertIn("autre.fr", conn.execute("SELECT urls_alt FROM offres").fetchone()[0])

    def test_historique(self):
        e = Envoi()
        self.run_([("jjf", source([BON]))], e); self.run_([("jjf", source([BON]))], e)
        conn = bd.ouvrir(self.db)
        self.assertEqual([r["type"] for r in conn.execute("SELECT type FROM emails ORDER BY id")], ["offres", "ras"])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM verifications").fetchone()[0], 2)

    def test_mode_essai_ne_marque_rien(self):
        self.run_([("jjf", source([BON]))], None)
        e = Envoi()
        self.assertEqual(self.run_([("jjf", source([BON]))], e)["type_email"], "offres")

    def test_config_manquante(self):
        for k in ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM", "EMAIL_TO"]:
            os.environ.pop(k, None)
        with self.assertRaises(RuntimeError):
            emailing.config_depuis_env()


if __name__ == "__main__":
    unittest.main(verbosity=2)
