"""Fabrication et envoi des emails (offres, RAS, erreur) par SMTP sécurisé."""
import html
import os
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage

try:
    from zoneinfo import ZoneInfo
    FUSEAU = ZoneInfo("Europe/Paris")
except Exception:  # sans base de fuseaux horaires : on affiche l'heure UTC
    FUSEAU = timezone.utc

OBJET_OFFRES = "🚨 Nouvelle(s) offre(s) de stage en Asset Management"
OBJET_RAS = "RAS – Veille Asset Management"
OBJET_ERREUR = "⚠️ Veille Asset Management – vérification impossible"
OBJET_PARTIEL = "⚠️ Veille Asset Management – vérification incomplète (pas de RAS)"


def heure_paris(dt=None):
    dt = dt or datetime.now(timezone.utc)
    return dt.astimezone(FUSEAU).strftime("%d/%m/%Y à %H:%M") + " (heure de Paris)"


def _date_fr(iso):
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return "Non précisée"


def _resume(description):
    """Début utile de la description : on saute la présentation de l'entreprise et on part des missions."""
    texte = re.sub(r"\s+", " ", description or "").strip()
    m = re.search(r"\b(vos missions|missions?|your responsibilities|responsabilit[ée]s|what you.ll do)\b\s*:?", texte, re.I)
    return texte[m.end():].strip() if m and m.end() < len(texte) - 80 else texte


def _lignes_offre(o):
    import json
    resume = _resume(o["description"])
    resume = (resume[:300].rsplit(" ", 1)[0] + "…") if len(resume) > 300 else resume
    resume = resume or "Description complète non disponible dans la source : ouvre l'annonce pour la lire."
    raisons = json.loads(o["raisons"] or "[]")
    alertes = json.loads(o["alertes"] or "[]")
    texte = [
        "🚨 NOUVELLE OFFRE DE STAGE" + (" (republiée)" if o["republiee"] else ""),
        f"Entreprise : {(o['societe'] or '').upper()}",
        f"Poste : {o['titre']}",
        f"Ville : {o['ville']}",
        f"Catégorie : {o['categorie'] or 'Non précisée'}",
        f"Classe d'actifs : {o['classe_actifs']}",
        f"Date de publication : {_date_fr(o['date_publication'])}",
        f"Date de début : {o['debut'] or 'Non précisée'}",
        f"Score de pertinence : {o['score']}/100",
        f"Résumé : {resume}",
        "Pourquoi cette offre correspond :",
    ] + [f"  • {r}" for r in raisons]
    if alertes:
        texte.append("À vérifier :")
        texte += [f"  • {a}" for a in alertes]
    texte.append(f"Lien direct vers l'annonce : {o['url']}")
    return texte


def _note_ignorees(ignorees):
    return ("\n\nℹ️ Sources temporairement ignorées (sans gravité) : " + " ; ".join(ignorees)) if ignorees else ""


def composer_offres(offres, erreurs=(), ignorees=()):
    blocs = [_lignes_offre(o) for o in offres]
    texte = ("\n" + "-" * 40 + "\n").join("\n".join(b) for b in blocs)
    if erreurs:
        texte += "\n\n⚠️ Sources en erreur pendant cette vérification : " + " ; ".join(erreurs)
    texte += _note_ignorees(ignorees)
    texte += f"\n\nDernière vérification : {heure_paris()}"
    corps = ""
    for b in blocs:
        corps += "<div style='border:1px solid #ddd;border-radius:8px;padding:12px;margin:12px 0'>"
        corps += "".join(f"<div>{html.escape(l)}</div>" if not l.startswith("Lien direct")
                         else f"<div>Lien direct vers l'annonce : <a href='{html.escape(l.split(': ', 1)[1])}'>ouvrir l'annonce</a></div>"
                         for l in b)
        corps += "</div>"
    if erreurs:
        corps += f"<p>⚠️ Sources en erreur : {html.escape(' ; '.join(erreurs))}</p>"
    return OBJET_OFFRES, texte, f"<html><body style='font-family:Arial,sans-serif'>{corps}<p>Dernière vérification : {heure_paris()}</p></body></html>"


def composer_ras(ignorees=()):
    texte = ("RAS.\nAucune nouvelle offre de stage correspondant à tes critères n'a été détectée lors de cette dernière vérification."
             f"{_note_ignorees(ignorees)}\n"
             f"Dernière vérification : {heure_paris()}.")
    return OBJET_RAS, texte, "<html><body style='font-family:Arial,sans-serif'>" + html.escape(texte).replace("\n", "<br>") + "</body></html>"


def composer_erreur(erreurs, partiel=False):
    intro = ("La vérification n'a été que PARTIELLE : au moins une source n'a pas pu être lue. Aucun message RAS n'est envoyé."
             if partiel else "La surveillance n'a pas pu être effectuée lors de cette vérification.")
    texte = intro + "\n\nNature de l'erreur :\n" + "\n".join(f"  • {e}" for e in erreurs) + f"\n\nHeure : {heure_paris()}"
    return (OBJET_PARTIEL if partiel else OBJET_ERREUR), texte, "<html><body style='font-family:Arial,sans-serif'>" + html.escape(texte).replace("\n", "<br>") + "</body></html>"


def config_depuis_env():
    requis = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_FROM", "EMAIL_TO"]
    manquants = [k for k in requis if not os.environ.get(k)]
    if manquants:
        raise RuntimeError("Configuration email incomplète, il manque : " + ", ".join(manquants))
    return {k: os.environ[k] for k in requis}


def envoyer(objet, texte, corps_html, config=None):
    cfg = config or config_depuis_env()
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = objet, cfg["EMAIL_FROM"], cfg["EMAIL_TO"]
    msg.set_content(texte)
    msg.add_alternative(corps_html, subtype="html")
    port = int(cfg["SMTP_PORT"])
    contexte = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(cfg["SMTP_HOST"], port, context=contexte, timeout=30) as s:
            s.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg["SMTP_HOST"], port, timeout=30) as s:
            s.starttls(context=contexte)
            s.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
            s.send_message(msg)
