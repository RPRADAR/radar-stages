"""Test du filet de sécurité (sans vrai email)."""
import sys, unittest, unittest.mock as m
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import alerte_panne as a

ENV = {"SMTP_HOST": "smtp.exemple.com", "SMTP_PORT": "465", "SMTP_USER": "u", "SMTP_PASSWORD": "p",
       "EMAIL_FROM": "robot@exemple.com", "EMAIL_TO": "moi@exemple.com",
       "GITHUB_REPOSITORY": "compte/radar-stages", "GITHUB_RUN_ID": "123", "GITHUB_SERVER_URL": "https://github.com"}


class TestAlertePanne(unittest.TestCase):
    def test_contenu(self):
        objet, texte = a.composer(ENV)
        self.assertIn("a planté", objet); self.assertIn("https://github.com/compte/radar-stages/actions/runs/123", texte)
        self.assertIn("Aucun message RAS", texte)

    def test_envoi(self):
        with m.patch("alerte_panne.smtplib.SMTP_SSL") as smtp:
            a.envoyer(ENV)
        instance = smtp.return_value.__enter__.return_value
        instance.login.assert_called_once_with("u", "p")
        message = instance.send_message.call_args[0][0]
        self.assertEqual((message["To"], message["From"]), ("moi@exemple.com", "robot@exemple.com"))

    def test_config_manquante(self):
        with self.assertRaises(RuntimeError):
            a.envoyer({"SMTP_HOST": "x"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
