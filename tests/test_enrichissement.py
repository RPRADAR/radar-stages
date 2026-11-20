"""Tests de l'enrichissement (lecture des pages d'annonces) avec de fausses pages, sans Internet."""
import sqlite3, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import base_donnees as bd
import enrichissement as en
import radar
import scoring as s

ENTITE = ("Premier gérant d'actifs européen, Amundi propose à ses clients particuliers, institutionnels et entreprises "
          "une gamme complète de solutions d'épargne et d'investissement en gestion active et passive. Filiale du groupe "
          "Crédit Agricole, Amundi est cotée en Bourse et gère aujourd'hui près de 2 300 milliards d'euros d'encours.")


def page(debut, missions="Assister l'équipe commerciale sur la préparation des rendez-vous clients et suivre la performance des fonds."):
    return f"""<html><body><nav>Accueil Mon compte</nav>
    <div><h3>Types de métiers</h3><ul><li>Gestion d'Actifs (46)</li><li>CDD (3)</li><li>CDI (35)</li><li>Stage (77)</li><li>VIE (9)</li></ul></div>
    <div>Vous êtes ici : Accueil › Liste des offres › Détail de l'offre</div>
    <h1>Détail de l'offre</h1><h2>Informations générales</h2><h3>Entité</h3><p>{ENTITE}</p>
    <h2>Description du poste</h2><h3>Type de contrat</h3><p>Stage</p>
    <h3>Date prévue de prise de fonction</h3><p>{debut}</p><h3>Missions</h3><p>{missions}</p>
    <footer>Mentions légales Cookies</footer></body></html>"""


def offre(id_, titre, lieu="Paris"):
    return {"societe": "Amundi", "plateforme": "jjf", "id_source": id_, "titre": titre, "lieu": lieu, "url": f"https://jobs.exemple.com/{id_}",
            "description": "", "date_publication": "2026-11-17", "famille": "Gestion d'actifs", "structure": "Société de gestion", "contrat": "Stage"}


class Envoi:
    def __init__(self): self.mails = []
    def __call__(self, objet, texte, corps): self.mails.append((objet, texte))


class TestEnrichissement(unittest.TestCase):
    def setUp(self):
        self.db = Path(tempfile.mkdtemp()) / "t.db"
        self.societes = s.charger_societes()

    def test_extraction_sans_bruit(self):
        t = en.extraire_description(page("12/01/2027"))
        self.assertIn("12/01/2027", t); self.assertIn("Missions", t)
        self.assertNotIn("CDI (35)", t); self.assertNotIn("Mentions légales", t); self.assertNotIn("Mon compte", t)

    def test_extraction_json_ld(self):
        html = ('<html><script type="application/ld+json">{"@type":"JobPosting","description":"&lt;p&gt;Stage gestion de portefeuille, '
                'début 03/05/2027. Analyse des fonds actions.&lt;/p&gt;","datePosted":"2026-11-10"}</script><body>menu</body></html>')
        t = en.extraire_description(html)
        self.assertIn("gestion de portefeuille", t); self.assertIn("2026-11-10", t)

    def test_la_page_corrige_la_note_provisoire(self):
        pages = {"https://jobs.exemple.com/A": page("12/01/2027"), "https://jobs.exemple.com/B": page("04/05/2027")}
        e = Envoi()
        src = lambda: [offre("A", "Assistant Sales Strategy – Distribution & Wealth"), offre("B", "Gestion Sous Mandat Assistant Gérant")]
        r = radar.executer(self.db, [("jjf", src)], e, self.societes, verifier_liens=False, enrichir=True, telecharger=lambda u: pages[u])
        self.assertEqual(r["nb_a_notifier"], 1)                          # A (début janvier) est écartée après lecture de la page
        texte = e.mails[0][1]
        self.assertIn("Gestion Sous Mandat", texte); self.assertNotIn("Sales Strategy", texte)
        self.assertIn("Date de début : Mai 2027", texte)
        self.assertIn("Assister l'équipe commerciale", texte)             # le résumé part des missions
        self.assertNotIn("Premier gérant", texte)
        conn = bd.ouvrir(self.db)
        a = conn.execute("SELECT retenue, rejet FROM offres WHERE id_source='A'").fetchone()
        self.assertEqual(a["retenue"], 0); self.assertIn("hors avril-août", a["rejet"])

    def test_pas_de_nouvelle_lecture_et_note_conservee(self):
        appels = []
        def fetch(u): appels.append(u); return page("04/05/2027")
        src = lambda: [offre("B", "Gestion Sous Mandat Assistant Gérant")]
        e = Envoi()
        radar.executer(self.db, [("jjf", src)], e, self.societes, verifier_liens=False, enrichir=True, telecharger=fetch)
        score1 = bd.ouvrir(self.db).execute("SELECT score FROM offres").fetchone()[0]
        r2 = radar.executer(self.db, [("jjf", src)], e, self.societes, verifier_liens=False, enrichir=True, telecharger=fetch)
        self.assertEqual(len(appels), 1)                                  # la page n'est lue qu'une fois
        self.assertEqual(bd.ouvrir(self.db).execute("SELECT score FROM offres").fetchone()[0], score1)
        self.assertEqual(r2["type_email"], "ras")                         # et l'offre n'est pas renvoyée

    def test_page_illisible_n_empeche_pas_l_envoi(self):
        def fetch(u): raise ConnectionError("403")
        src = lambda: [offre("B", "Gestion Sous Mandat Assistant Gérant")]
        e = Envoi()
        r = radar.executer(self.db, [("jjf", src)], e, self.societes, verifier_liens=False, enrichir=True, telecharger=fetch)
        self.assertEqual(r["nb_a_notifier"], 1)
        self.assertIn("Date de début non indiquée", e.mails[0][1])        # alerte "à vérifier" conservée
        self.assertEqual(bd.ouvrir(self.db).execute("SELECT tentatives FROM offres").fetchone()[0], 1)

    def test_pages_linkedin_et_indeed_jamais_lues(self):
        with self.assertRaises(ValueError):
            en.telecharger_page("https://www.linkedin.com/jobs/view/123/")
        with self.assertRaises(ValueError):
            en.telecharger_page("https://fr.indeed.com/viewjob?jk=abc")

    def test_migration_ancienne_base(self):
        conn = bd.ouvrir(self.db)
        for colonne in ("meta", "enrichie", "tentatives"):      # on fabrique une base "ancienne version"
            conn.execute(f"ALTER TABLE offres DROP COLUMN {colonne}")
        conn.commit(); conn.close()
        conn = bd.ouvrir(self.db)   # ne doit pas planter : les colonnes manquantes sont ajoutées
        colonnes = {r[1] for r in conn.execute("PRAGMA table_info(offres)")}
        self.assertTrue({"meta", "enrichie", "tentatives"} <= colonnes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
