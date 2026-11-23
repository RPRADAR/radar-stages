"""Diagnostic Workday : montre ce que le site Workday répond VRAIMENT, pour comprendre pourquoi aucune offre n'est trouvée."""
import requests

SITES = ["ameriprise.wd5.myworkdayjobs.com/Ameriprise", "gam.wd3.myworkdayjobs.com/GAM"]
EN_TETES = {"User-Agent": "RadarStages/1.0 (veille personnelle de stages)", "Accept": "application/json",
            "Content-Type": "application/json", "Accept-Language": "en-US"}
for identifiant in SITES:
    hote, _, site = identifiant.partition("/")
    url = f"https://{hote}/wday/cxs/{hote.split('.')[0]}/{site}/jobs"
    print("=" * 80)
    print(url)
    for terme in ["", "intern"]:
        try:
            r = requests.post(url, headers=EN_TETES, timeout=30,
                              json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": terme})
        except Exception as e:
            print(f"  recherche « {terme} » : ERREUR RÉSEAU {e}")
            continue
        print(f"  recherche « {terme} » : code HTTP {r.status_code}, type {r.headers.get('Content-Type', '?')[:40]}, {len(r.content)} octets")
        try:
            d = r.json()
            postes = d.get("jobPostings") or []
            print(f"     clés de la réponse : {sorted(d)[:8]} | total annoncé : {d.get('total')} | postes reçus : {len(postes)}")
            for p in postes[:5]:
                print(f"       - {str(p.get('title'))[:60]} | {p.get('locationsText')} | {p.get('postedOn')}")
        except Exception:
            print("     réponse non JSON, début :", r.text[:300].replace("\n", " "))
