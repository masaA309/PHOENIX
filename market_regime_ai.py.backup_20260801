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
AI_JUDGEMENT_FILE = REPORT_DIR / "ai_judgement.csv"
MARKET_RISK_FILE = DATA_DIR / "market_risk_latest.json"
OUTPUT_JSON = REPORT_DIR / "market_regime.json"
OUTPUT_CSV = REPORT_DIR / "market_regime_history.csv"
OUTPUT_TEXT = REPORT_DIR / "market_regime_report.txt"

REGIME_SETTINGS = {
    "BULL": {"strategy": "AGGRESSIVE", "capital_usage_percent": 100.0, "max_positions": 5, "entry_score_adjustment": -5.0, "risk_per_trade_multiplier": 1.10, "stop_multiplier": 1.10, "target_multiplier": 1.20},
    "SIDEWAYS": {"strategy": "BALANCED", "capital_usage_percent": 70.0, "max_positions": 3, "entry_score_adjustment": 0.0, "risk_per_trade_multiplier": 0.85, "stop_multiplier": 1.00, "target_multiplier": 1.00},
    "BEAR": {"strategy": "DEFENSIVE", "capital_usage_percent": 35.0, "max_positions": 1, "entry_score_adjustment": 10.0, "risk_per_trade_multiplier": 0.50, "stop_multiplier": 0.85, "target_multiplier": 0.80},
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
        if value is None or pd.isna(value): return default
        number=float(str(value).replace(",", "").replace("%", "").strip())
        return number if math.isfinite(number) else default
    except (TypeError, ValueError): return default

def read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists(): return pd.DataFrame()
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try: return pd.read_csv(path, encoding=enc)
        except Exception: pass
    return pd.DataFrame()

def load_json(path: Path) -> dict[str, Any]:
    if not path.exists(): return {}
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError): return {}

def find_column(df: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    mapping={str(c).strip().lower(): c for c in df.columns}
    for name in names:
        if name.lower() in mapping: return mapping[name.lower()]
    return None

def numeric_series(df: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    col=find_column(df,names)
    if col is None: return pd.Series(dtype=float)
    return pd.to_numeric(df[col], errors="coerce").dropna()

def text_series(df: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    col=find_column(df,names)
    if col is None: return pd.Series(dtype=str)
    return df[col].fillna("").astype(str).str.strip().str.upper()

def ratio(condition: pd.Series) -> float:
    return float(condition.mean()*100.0) if len(condition) else 50.0

def analyse() -> dict[str, Any]:
    df=read_csv_safe(AI_JUDGEMENT_FILE)
    risk=load_json(MARKET_RISK_FILE)
    risk_score=safe_float(risk.get("score", risk.get("market_risk_score", 50)),50)

    change=numeric_series(df,("前日比%","前日比", "change_percent", "騰落率"))
    rsi=numeric_series(df,("RSI","rsi"))
    price=numeric_series(df,("現在価格","価格","終値","基準価格"))
    ma25=numeric_series(df,("MA25","ma25"))
    ma75=numeric_series(df,("MA75","ma75"))
    macd=text_series(df,("MACD判定","MACD", "macd_signal"))

    advance_ratio=ratio(change>0) if len(change) else 50.0
    avg_change=float(change.mean()) if len(change) else 0.0
    avg_rsi=float(rsi.mean()) if len(rsi) else 50.0
    macd_buy_ratio=ratio(macd.str.contains("BUY|買", regex=True)) if len(macd) else 50.0
    above_ma25_ratio=ratio(price.reset_index(drop=True)>ma25.reset_index(drop=True)) if len(price) and len(price)==len(ma25) else 50.0
    above_ma75_ratio=ratio(price.reset_index(drop=True)>ma75.reset_index(drop=True)) if len(price) and len(price)==len(ma75) else 50.0

    breadth_score=(advance_ratio-50)*0.50 + (above_ma25_ratio-50)*0.35 + (above_ma75_ratio-50)*0.25 + (macd_buy_ratio-50)*0.35
    momentum_score=(avg_rsi-50)*0.90 + avg_change*3.0
    risk_penalty=max(risk_score-50,0)*0.45
    total_score=max(-100.0,min(100.0,breadth_score+momentum_score-risk_penalty))

    if total_score>=12 and risk_score<70: regime="BULL"
    elif total_score<=-8 or risk_score>=75: regime="BEAR"
    else: regime="SIDEWAYS"

    confidence=min(99.0,55.0+abs(total_score)*1.5+abs(advance_ratio-50)*0.25)
    settings=dict(REGIME_SETTINGS[regime])
    reasons=[f"上昇銘柄比率 {advance_ratio:.1f}%",f"MA25上比率 {above_ma25_ratio:.1f}%",f"MA75上比率 {above_ma75_ratio:.1f}%",f"MACD BUY比率 {macd_buy_ratio:.1f}%",f"平均RSI {avg_rsi:.1f}",f"Market Risk {risk_score:.0f}"]
    return {"version":"PHOENIX v6.3","generated_at":now_text(),"regime":regime,"confidence":round(confidence,2),"score":round(total_score,2),"strategy":settings["strategy"],"metrics":{"stock_count":int(len(df)),"advance_ratio":round(advance_ratio,2),"average_change_percent":round(avg_change,3),"above_ma25_ratio":round(above_ma25_ratio,2),"above_ma75_ratio":round(above_ma75_ratio,2),"macd_buy_ratio":round(macd_buy_ratio,2),"average_rsi":round(avg_rsi,2),"market_risk_score":round(risk_score,2)},"settings":settings,"reasons":reasons,"source":str(AI_JUDGEMENT_FILE)}

def save_result(result: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8",newline="\n")
    row={"generated_at":result["generated_at"],"regime":result["regime"],"confidence":result["confidence"],"score":result["score"],"strategy":result["strategy"],**result["metrics"],**result["settings"]}
    history=read_csv_safe(OUTPUT_CSV)
    history=pd.concat([history,pd.DataFrame([row])],ignore_index=True).tail(1000)
    history.to_csv(OUTPUT_CSV,index=False,encoding="utf-8-sig")
    lines=["PHOENIX v6.3 MARKET REGIME AI",result["generated_at"],"="*100,f"市場状態       : {result['regime']}",f"信頼度         : {result['confidence']:.2f}%",f"Regime Score   : {result['score']:+.2f}",f"推奨戦略       : {result['strategy']}",f"最大保有数     : {result['settings']['max_positions']}件",f"資金使用率     : {result['settings']['capital_usage_percent']:.0f}%",""]+[f"・{x}" for x in result["reasons"]]
    OUTPUT_TEXT.write_text("\n".join(lines)+"\n",encoding="utf-8")

def main() -> None:
    configure_console(); print("="*100); print("PHOENIX v6.3 MARKET REGIME AI"); print("="*100)
    result=analyse(); save_result(result)
    print(f"市場状態       : {result['regime']}"); print(f"信頼度         : {result['confidence']:.2f}%"); print(f"Regime Score   : {result['score']:+.2f}"); print(f"推奨戦略       : {result['strategy']}"); print(f"最大保有数     : {result['settings']['max_positions']}件"); print(f"資金使用率     : {result['settings']['capital_usage_percent']:.0f}%")
    for reason in result["reasons"]: print(f"・{reason}")
    print(f"保存完了       : {OUTPUT_JSON}"); print(f"履歴保存       : {OUTPUT_CSV}")
if __name__ == "__main__": main()
