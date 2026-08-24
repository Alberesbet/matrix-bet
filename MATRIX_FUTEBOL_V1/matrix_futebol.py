import os, time, csv, statistics, requests
from datetime import datetime
from pathlib import Path

BASE="https://api.sportmonks.com/v3/football"
DATA=Path(__file__).parent/"data"; DATA.mkdir(exist_ok=True)
HIST=DATA/"historico.csv"

CONFIG={
 "stake":10.0, "odd_min":1.45, "odd_max":3.50,
 "prob_min":0.55, "intervalo":300, "modo":"SIMULACAO"
}

def api(path, params=None):
    token=os.getenv("SPORTMONKS_TOKEN","").strip()
    if not token: raise RuntimeError("SPORTMONKS_TOKEN não configurado.")
    p=dict(params or {}); p["api_token"]=token
    r=requests.get(BASE+path,params=p,timeout=25,headers={"Accept":"application/json"})
    r.raise_for_status(); return r.json()

def jogos_hoje():
    d=datetime.now().strftime("%Y-%m-%d")
    return api(f"/fixtures/between/{d}/{d}",{"include":"participants;league;state"}).get("data",[])

def odds(fid):
    return api(f"/odds/pre-match/fixtures/{fid}",{"include":"market;bookmaker"}).get("data",[])

def times(f):
    h=a=None
    for p in f.get("participants") or []:
        loc=str((p.get("meta") or {}).get("location") or "").lower()
        if loc=="home": h=p.get("name")
        elif loc=="away": a=p.get("name")
    return h or "Casa",a or "Fora"

def mercado_1x2(rows):
    g={"HOME":[],"DRAW":[],"AWAY":[]}
    alias={"1":"HOME","HOME":"HOME","X":"DRAW","DRAW":"DRAW","2":"AWAY","AWAY":"AWAY"}
    for o in rows:
        desc=str(o.get("market_description") or (o.get("market") or {}).get("name") or "").upper()
        if o.get("market_id")!=1 and "MATCH WINNER" not in desc and "1X2" not in desc: continue
        k=alias.get(str(o.get("label") or o.get("name") or "").upper())
        try: v=float(o.get("value"))
        except: continue
        if k and v>1: g[k].append(v)
    out={}
    for k,vals in g.items():
        if vals: out[k]={"odd":statistics.median(vals)}
    total=sum(1/v["odd"] for v in out.values()) or 1
    for v in out.values():
        v["prob"]=(1/v["odd"])/total
    return out

def registrar(row):
    novo=not HIST.exists()
    with HIST.open("a",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=row.keys())
        if novo:w.writeheader()
        w.writerow(row)

def analisar():
    jogos=jogos_hoje()
    print(f"\nMATRIX - FUTEBOL | {len(jogos)} jogos encontrados")
    for f in jogos:
        if not f.get("has_odds"): continue
        h,a=times(f); fid=f.get("id")
        try:m=mercado_1x2(odds(fid))
        except Exception as e:
            print(h,"x",a,"| erro:",e); continue
        cand=[(k,v) for k,v in m.items() if CONFIG["odd_min"]<=v["odd"]<=CONFIG["odd_max"] and v["prob"]>=CONFIG["prob_min"]]
        if not cand: continue
        k,v=max(cand,key=lambda x:x[1]["prob"])
        print(f"SINAL | {h} x {a} | {k} | odd {v['odd']:.2f} | prob. normalizada {v['prob']:.1%}")
        registrar({"data":datetime.now().isoformat(timespec="seconds"),"fixture_id":fid,"jogo":f"{h} x {a}",
                   "selecao":k,"odd":round(v["odd"],3),"prob":round(v["prob"],4),
                   "stake":CONFIG["stake"],"modo":CONFIG["modo"],"status":"SINAL"})

def main():
    print("=== MATRIX - FUTEBOL V1 ===")
    print("Modo SIMULAÇÃO. Execução de apostas reais desativada.")
    while True:
        try: analisar()
        except KeyboardInterrupt: break
        except Exception as e: print("ERRO:",e)
        time.sleep(CONFIG["intervalo"])

if __name__=="__main__": main()
