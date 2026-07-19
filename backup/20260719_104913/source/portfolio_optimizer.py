from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import math
import sys
from typing import Any

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"
DATA_DIR = ROOT_DIR / "data"
INPUT_FILE = REPORT_DIR / "price_watchlist.csv"
LEARNING_FILE = REPORT_DIR / "learning_summary.json"
MARKET_REGIME_FILE = REPORT_DIR / "market_regime.json"
OUTPUT_FILE = REPORT_DIR / "portfolio_optimized_candidates.csv"
SUMMARY_FILE = REPORT_DIR / "portfolio_optimizer_summary.json"
REPORT_FILE = REPORT_DIR / "portfolio_optimizer_report.txt"
ACCOUNT_CAPITAL = 300_000
DEFAULT_WIN_RATE = 0.55
MAX_PER_SECTOR = 2

TICKER_SECTOR_MAP = {
    "1605.T":"エネルギー","3405.T":"素材・化学","3436.T":"半導体・電子部品",
    "3697.T":"情報通信・サービス","4005.T":"素材・化学","4902.T":"電機・精密",
    "5406.T":"鉄鋼・非鉄","6724.T":"電機・精密","6988.T":"電機・精密",
    "9001.T":"運輸","9101.T":"海運","9107.T":"海運","9501.T":"電力・ガス",
    "9984.T":"情報通信・サービス",
}

def configure_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        value=float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default

def load_json(path: Path) -> dict[str, Any]:
    if not path.exists(): return {}
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data,dict) else {}
    except (OSError,json.JSONDecodeError): return {}

def read_csv(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig","utf-8","cp932"):
        try: return pd.read_csv(path,encoding=enc)
        except UnicodeDecodeError: continue
    return pd.read_csv(path)

def infer_sector(ticker: str, name: str) -> str:
    if ticker in TICKER_SECTOR_MAP: return TICKER_SECTOR_MAP[ticker]
    rules=(("銀行","金融・保険"),("証券","金融・保険"),("電力","電力・ガス"),("ガス","電力・ガス"),
           ("郵船","海運"),("汽船","海運"),("鉄道","運輸"),("化学","素材・化学"),("電工","電機・精密"),
           ("電機","電機・精密"),("半導体","半導体・電子部品"),("ソフトバンク","情報通信・サービス"),
           ("自動車","自動車"),("製薬","医薬品"),("食品","食品"))
    for key,sector in rules:
        if key in name: return sector
    return "未分類"

def learned_win_rate() -> float:
    data=load_json(LEARNING_FILE)
    for key in ("win_rate","winning_rate","learned_win_rate"):
        val=safe_float(data.get(key),-1)
        if val>=0: return val/100 if val>1 else val
    result=data.get("result",{}) if isinstance(data.get("result"),dict) else {}
    val=safe_float(result.get("win_rate"),-1)
    return (val/100 if val>1 else val) if val>=0 else DEFAULT_WIN_RATE

def regime_multiplier() -> float:
    regime=str(load_json(MARKET_REGIME_FILE).get("regime","SIDEWAYS")).upper()
    return {"BULL":1.08,"SIDEWAYS":1.0,"BEAR":0.88}.get(regime,1.0)

def optimize() -> tuple[pd.DataFrame,dict[str,Any]]:
    if not INPUT_FILE.exists(): raise FileNotFoundError(f"入力ファイルがありません: {INPUT_FILE}")
    data=read_csv(INPUT_FILE)
    required={"銘柄","ticker","AI判断点","PHOENIX_SCORE","Trade判定","押し目価格","利確価格","損切価格"}
    missing=required-set(data.columns)
    if missing: raise ValueError("必要な列がありません: "+", ".join(sorted(missing)))
    for c in ("AI判断点","PHOENIX_SCORE","押し目価格","利確価格","損切価格"):
        data[c]=pd.to_numeric(data[c],errors="coerce")
    data=data[data["Trade判定"].astype(str).str.upper().isin(["BUY","WATCH"])].dropna(subset=list(required-{"銘柄","ticker","Trade判定"})).copy()
    win=max(0.35,min(0.75,learned_win_rate()))
    regime=regime_multiplier()
    data["セクター"]=[infer_sector(str(t),str(n)) for t,n in zip(data["ticker"],data["銘柄"])]
    loss=(data["押し目価格"]-data["損切価格"]).clip(lower=0.01)
    profit=(data["利確価格"]-data["押し目価格"]).clip(lower=0)
    data["リスクリワード"]=(profit/loss).clip(upper=10).round(3)
    data["期待値R"]=(win*data["リスクリワード"]-(1-win)).round(3)
    trade=data["Trade判定"].astype(str).str.upper().map({"BUY":100,"WATCH":70}).fillna(50)
    data["ExpectedScore"]=(data["AI判断点"]*0.32+data["PHOENIX_SCORE"]*0.28+trade*0.15+(data["期待値R"].clip(-1,5)+1)/6*100*0.25)*regime
    data["ExpectedScore"]=data["ExpectedScore"].clip(0,100).round(2)
    data=data.sort_values(["ExpectedScore","AI判断点","PHOENIX_SCORE"],ascending=False).reset_index(drop=True)
    counts={}; penalties=[]
    for sector in data["セクター"]:
        count=counts.get(sector,0); penalties.append(max(0,count-(MAX_PER_SECTOR-1))*8.0); counts[sector]=count+1
    data["分散ペナルティ"]=penalties
    data["OptimizerScore"]=(data["ExpectedScore"]-data["分散ペナルティ"]).clip(0,100).round(2)
    data=data.sort_values("OptimizerScore",ascending=False).reset_index(drop=True)
    data["Optimizer順位"]=range(1,len(data)+1)
    total=max(0.0001,float(data["OptimizerScore"].clip(lower=1).sum()))
    data["推奨配分比率"]=(data["OptimizerScore"].clip(lower=1)/total).round(4)
    cols=["Optimizer順位","銘柄","ticker","セクター","Trade判定","AI判断点","PHOENIX_SCORE","リスクリワード","期待値R","ExpectedScore","分散ペナルティ","OptimizerScore","推奨配分比率"]
    data=data[cols+[c for c in data.columns if c not in cols]]
    diversification="A" if data["セクター"].nunique()>=min(4,len(data)) else "B"
    summary={"version":"PHOENIX v6.4","generated_at":now_text(),"input_count":len(data),"learned_win_rate":round(win*100,2),"average_expected_score":round(safe_float(data["ExpectedScore"].mean()),2),"average_expected_r":round(safe_float(data["期待値R"].mean()),3),"diversification_grade":diversification,"sector_count":int(data["セクター"].nunique()),"top_tickers":data.head(5)["ticker"].astype(str).tolist()}
    return data,summary

def save(data: pd.DataFrame,summary: dict[str,Any]) -> None:
    REPORT_DIR.mkdir(parents=True,exist_ok=True)
    data.to_csv(OUTPUT_FILE,index=False,encoding="utf-8-sig")
    SUMMARY_FILE.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    REPORT_FILE.write_text("PHOENIX v6.4 PORTFOLIO OPTIMIZER\n"+now_text()+"\n"+"="*120+"\n"+data.head(20).to_string(index=False)+"\n",encoding="utf-8")

def main() -> None:
    configure_console()
    try:
        data,summary=optimize(); save(data,summary)
        print("="*120); print("PHOENIX v6.4 PORTFOLIO OPTIMIZER"); print("="*120)
        print(f"候補数         : {summary['input_count']}件")
        print(f"学習勝率       : {summary['learned_win_rate']:.2f}%")
        print(f"平均期待値R    : {summary['average_expected_r']:+.3f}")
        print(f"平均期待値Score: {summary['average_expected_score']:.2f}")
        print(f"分散評価       : {summary['diversification_grade']}")
        print(data[["Optimizer順位","銘柄","ticker","セクター","ExpectedScore","OptimizerScore","期待値R"]].head(15).to_string(index=False))
        print(f"保存完了: {OUTPUT_FILE}")
    except Exception as error:
        print(f"エラー: {error}"); raise SystemExit(1)

if __name__ == "__main__": main()
