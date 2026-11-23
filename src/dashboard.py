"""
Tableau de bord Radar stages Asset Management (Streamlit, gratuit, sur ton ordinateur).
Lancement : double-clic sur "Ouvrir_le_tableau_de_bord.bat"
"""
import io

import pandas as pd
import streamlit as st

import donnees_dashboard as dd

st.set_page_config(page_title="Radar stages Asset Management", page_icon="📡", layout="wide")
st.title("📡 Radar stages — Asset Management")

# --- Données : on télécharge la base la plus récente du robot au premier affichage ---
if "base_telechargee" not in st.session_state:
    st.session_state["base_telechargee"] = True
    ok, message = dd.telecharger_base()
    st.session_state["message_base"] = (ok, message)
if st.sidebar.button("🔄 Actualiser depuis GitHub"):
    st.session_state["message_base"] = dd.telecharger_base()
    st.rerun()
ok, message = st.session_state.get("message_base", (True, ""))
if not dd.CHEMIN_BASE.exists():
    st.error(f"Aucune base disponible. {message}")
    st.stop()
if not ok:
    st.sidebar.warning(message + " Affichage de la dernière copie locale.")

derniere, historique = dd.etat_robot()
if derniere:
    st.caption(f"Dernière vérification du robot : {derniere['date']} — {derniere['lues']} offres lues, "
               f"{derniere['nouvelles']} nouvelles — état : {derniere['statut']}"
               + (f" — erreurs : {derniere['erreurs']}" if derniere["erreurs"] else ""))

# --- Filtres ---
st.sidebar.header("Filtres")
inclure_inactives = st.sidebar.checkbox("Inclure les offres disparues", value=False)
inclure_rejetees = st.sidebar.checkbox("Inclure les offres rejetées (note < 60)", value=False)
offres = dd.charger_offres(inclure_inactives=inclure_inactives, inclure_rejetees=inclure_rejetees)
df = pd.DataFrame(offres)
if df.empty:
    st.info("Aucune offre pour le moment. Le robot en détectera dès qu'une offre pertinente sera publiée.")
    st.stop()

texte = st.sidebar.text_input("Recherche (poste, entreprise...)")
score_min = st.sidebar.slider("Score minimum", 0, 100, 60 if not inclure_rejetees else 0)
choix = {}
for colonne in ["Entreprise", "Ville", "Catégorie", "Statut"]:
    choix[colonne] = st.sidebar.multiselect(colonne, sorted(df[colonne].dropna().unique()))

filtre = df["Score"] >= score_min
if texte:
    filtre &= df[["Poste", "Entreprise"]].apply(lambda c: c.str.contains(texte, case=False, na=False)).any(axis=1)
for colonne, valeurs in choix.items():
    if valeurs:
        filtre &= df[colonne].isin(valeurs)
df = df[filtre]

vue = st.radio("Classer par", ["Plus récentes", "Pertinence", "Entreprise", "Ville", "Catégorie"], horizontal=True)
tris = {"Plus récentes": (["_tri_detection"], [False]), "Pertinence": (["Score"], [False]),
        "Entreprise": (["Entreprise", "Score"], [True, False]), "Ville": (["Ville", "Score"], [True, False]),
        "Catégorie": (["Catégorie", "Score"], [True, False])}
cols, asc = tris[vue]
df = df.sort_values(cols, ascending=asc).set_index("id")

c1, c2, c3 = st.columns(3)
c1.metric("Offres affichées", len(df))
c2.metric("À postuler", int((df["Statut"] == dd.STATUTS[0]).sum()))
c3.metric("Candidatures envoyées", int((df["Statut"] == dd.STATUTS[1]).sum()))

TOUTES = ["Score", "Entreprise", "Poste", "Ville", "Catégorie", "Classe d'actifs", "Début",
          "Publication", "Détectée le", "Statut", "Lien", "À vérifier"]
PAR_DEFAUT = ["Score", "Publication", "Entreprise", "Poste", "Ville", "Catégorie", "Classe d'actifs",
              "Début", "Détectée le", "Statut", "Lien", "À vérifier"]
prefs = dd.charger_preferences()
enregistrees = [c for c in prefs.get("colonnes", []) if c in TOUTES]
defaut = enregistrees or PAR_DEFAUT
colonnes = st.sidebar.multiselect("Colonnes affichées (dans l'ordre choisi)", TOUTES, default=defaut) or defaut
if colonnes != enregistrees:
    dd.sauver_preferences({"colonnes": colonnes})  # l'ordre est retenu à la prochaine ouverture
modifie = st.data_editor(
    df[colonnes], use_container_width=True, hide_index=True, key=f"tableau_{vue}",
    disabled=[c for c in colonnes if c != "Statut"],
    column_config={
        "Statut": st.column_config.SelectboxColumn("Statut", options=dd.STATUTS, required=True),
        "Lien": st.column_config.LinkColumn("Lien", display_text="Ouvrir l'annonce"),
        "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
    })
if st.button("💾 Enregistrer les statuts de candidature"):
    statuts = dd.charger_statuts()
    for identifiant, statut in modifie["Statut"].items():
        statuts[identifiant] = statut
    dd.sauver_statuts(statuts)
    st.success("Statuts enregistrés sur ton ordinateur.")

# --- Export ---
export = df[colonnes]
d1, d2 = st.columns(2)
d1.download_button("⬇️ Exporter en CSV", export.to_csv(index=False, sep=";").encode("utf-8-sig"),
                   "offres_stages.csv", "text/csv")
tampon = io.BytesIO()
export.to_excel(tampon, index=False, engine="openpyxl")
d2.download_button("⬇️ Exporter en Excel", tampon.getvalue(), "offres_stages.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with st.expander("📧 Historique des emails envoyés par le robot"):
    st.dataframe(pd.DataFrame(historique), use_container_width=True, hide_index=True)
