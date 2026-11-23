"""
Filet de sécurité : envoie un email si le robot a PLANTÉ avant même de pouvoir t'écrire
(par exemple un fichier manquant sur GitHub). N'utilise que des outils de base de Python,
donc il fonctionne même si le reste du code est cassé.
"""
import os
import smtplib
import ssl
from email.message import EmailMessage

REQUIS = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM", "EMAIL_TO"]


def composer(env):
    lien = ""
    if env.get("GITHUB_REPOSITORY") and env.get("GITHUB_RUN_ID"):
        lien = f"{env.get('GITHUB_SERVER_URL', 'https://github.com')}/{env['GITHUB_REPOSITORY']}/actions/runs/{env['GITHUB_RUN_ID']}"
    texte = ("La vérification horaire n'a pas pu s'exécuter : le robot a planté avant de lire les sources.\n"
             "Aucun message RAS n'est envoyé, et aucune offre n'a été vérifiée pendant ce lancement.\n\n"
             + (f"Détail de l'erreur (lignes en rouge) : {lien}\n\n" if lien else "")
             + "Cause fréquente : un fichier de code manque sur GitHub après une mise à jour. "
               "Consulte le guide de maintenance, partie 3, ou envoie-moi les lignes rouges.")
    return "⚠️ Veille Asset Management – le robot a planté", texte


def envoyer(env=None):
    env = env or os.environ
    manquants = [k for k in REQUIS if not env.get(k)]
    if manquants:
        raise RuntimeError("Configuration email incomplète : " + ", ".join(manquants))
    objet, texte = composer(env)
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = objet, env["EMAIL_FROM"], env["EMAIL_TO"]
    msg.set_content(texte)
    port, contexte = int(env["SMTP_PORT"]), ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(env["SMTP_HOST"], port, context=contexte, timeout=30) as s:
            s.login(env["SMTP_USER"], env["SMTP_PASSWORD"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(env["SMTP_HOST"], port, timeout=30) as s:
            s.starttls(context=contexte)
            s.login(env["SMTP_USER"], env["SMTP_PASSWORD"])
            s.send_message(msg)


if __name__ == "__main__":
    envoyer()
    print("Email d'alerte de panne envoyé.")
