"""Petit test : vérifie que Python et la liste des sociétés fonctionnent."""
import csv
from pathlib import Path

fichier = Path(__file__).resolve().parent.parent / "data" / "companies.csv"
with open(fichier, encoding="utf-8-sig") as f:
    lignes = list(csv.DictReader(f))

noms = [l["nom"].lower() for l in lignes]
doublons = {n for n in noms if noms.count(n) > 1}

print(f"Sociétés dans la liste : {len(lignes)}")
print(f"Doublons : {sorted(doublons) if doublons else 'aucun'}")
for pays in sorted({l['pays'] for l in lignes}):
    print(f"  {pays} : {sum(1 for l in lignes if l['pays']==pays)}")
print("OK : le projet est bien installé.")
