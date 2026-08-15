from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT_CSV = ROOT / "data" / "nikkei225_membership_20y.csv"


CURRENT_COMPONENTS_TEXT = r"""
ticker|company_name
4151|KYOWA KIRIN CO., LTD.
4502|TAKEDA PHARMACEUTICAL CO., LTD.
4503|ASTELLAS PHARMA INC.
4506|SUMITOMO PHARMA CO., LTD.
4507|SHIONOGI & CO., LTD.
4519|CHUGAI PHARMACEUTICAL CO., LTD.
4523|EISAI CO., LTD.
4568|DAIICHI SANKYO CO., LTD.
4578|OTSUKA HOLDINGS CO., LTD.
285A|KIOXIA HOLDINGS CORP.
4062|IBIDEN CO., LTD.
6479|MINEBEA MITSUMI INC.
6501|HITACHI, LTD.
6503|MITSUBISHI ELECTRIC CORP.
6504|FUJI ELECTRIC CO., LTD.
6506|YASKAWA ELECTRIC CORP.
6526|SOCIONEXT INC.
6645|OMRON CORP.
6701|NEC CORP.
6702|FUJITSU LTD.
6723|RENESAS ELECTRONICS CORP.
6724|SEIKO EPSON CORP.
6752|PANASONIC HOLDINGS CORP.
6753|SHARP CORP.
6758|SONY GROUP CORP.
6762|TDK CORP.
6770|ALPS ALPINE CO., LTD.
6841|YOKOGAWA ELECTRIC CORP.
6857|ADVANTEST CORP.
6861|KEYENCE CORP.
6902|DENSO CORP.
6920|LASERTEC CORP.
6954|FANUC CORP.
6963|ROHM CO., LTD.
6971|KYOCERA CORP.
6976|TAIYO YUDEN CO., LTD.
6981|MURATA MANUFACTURING CO., LTD.
7735|SCREEN HOLDINGS CO., LTD.
7751|CANON INC.
7752|RICOH CO., LTD.
8035|TOKYO ELECTRON LTD.
543A|ARCHION CORP.
7201|NISSAN MOTOR CO., LTD.
7202|ISUZU MOTORS LTD.
7203|TOYOTA MOTOR CORP.
7211|MITSUBISHI MOTORS CORP.
7261|MAZDA MOTOR CORP.
7267|HONDA MOTOR CO., LTD.
7269|SUZUKI MOTOR CORP.
7270|SUBARU CORP.
7272|YAMAHA MOTOR CO., LTD.
4543|TERUMO CORP.
4902|KONICA MINOLTA, INC.
6146|DISCO CORP.
7731|NIKON CORP.
7733|OLYMPUS CORP.
7741|HOYA CORP.
9432|NTT, INC.
9433|KDDI CORP.
9434|SOFTBANK CORP.
9984|SOFTBANK GROUP CORP.
5831|SHIZUOKA FINANCIAL GROUP, INC.
7186|YOKOHAMA FINANCIAL GROUP, INC.
8304|AOZORA BANK, LTD.
8306|MITSUBISHI UFJ FINANCIAL GROUP, INC.
8308|RESONA HOLDINGS, INC.
8309|SUMITOMO MITSUI TRUST GROUP, INC.
8316|SUMITOMO MITSUI FINANCIAL GROUP, INC.
8331|THE CHIBA BANK, LTD.
8354|FUKUOKA FINANCIAL GROUP, INC.
8411|MIZUHO FINANCIAL GROUP, INC.
8253|CREDIT SAISON CO., LTD.
8591|ORIX CORP.
8697|JAPAN EXCHANGE GROUP, INC.
8601|DAIWA SECURITIES GROUP INC.
8604|NOMURA HOLDINGS, INC.
8630|SOMPO HOLDINGS, INC.
8725|MS&AD INSURANCE GROUP HOLDINGS, INC.
8750|DAIICHI LIFE GROUP, INC.
8766|TOKIO MARINE HOLDINGS, INC.
8795|T&D HOLDINGS, INC.
1332|NISSUI CORP.
2002|NISSHIN SEIFUN GROUP INC.
2269|MEIJI HOLDINGS CO., LTD.
2282|NH FOODS LTD.
2501|SAPPORO BREWERIES LTD.
2502|ASAHI GROUP HOLDINGS, LTD.
2503|KIRIN HOLDINGS CO., LTD.
2801|KIKKOMAN CORP.
2802|AJINOMOTO CO., INC.
2871|NICHIREI CORP.
2914|JAPAN TOBACCO INC.
3086|J.FRONT RETAILING CO., LTD.
3092|ZOZO, INC.
3099|ISETAN MITSUKOSHI HOLDINGS LTD.
3382|SEVEN & I HOLDINGS CO., LTD.
7453|RYOHIN KEIKAKU CO., LTD.
7532|PAN PACIFIC INTERNATIONAL HOLDINGS CORP.
8233|TAKASHIMAYA CO., LTD.
8252|MARUI GROUP CO., LTD.
8267|AEON CO., LTD.
9843|NITORI HOLDINGS CO., LTD.
9983|FAST RETAILING CO., LTD.
2413|M3, INC.
2432|DENA CO., LTD.
3659|NEXON CO., LTD.
3697|SHIFT INC.
4307|NOMURA RESEARCH INSTITUTE, LTD.
4324|DENTSU GROUP INC.
4385|MERCARI, INC.
4661|ORIENTAL LAND CO., LTD.
4689|LY CORP.
4704|TREND MICRO INC.
4751|CYBERAGENT, INC.
4755|RAKUTEN GROUP, INC.
6098|RECRUIT HOLDINGS CO., LTD.
6178|JAPAN POST HOLDINGS CO., LTD.
6532|BAYCURRENT, INC.
7974|NINTENDO CO., LTD.
9602|TOHO CO., LTD
9735|SECOM CO., LTD.
9766|KONAMI GROUP CORP.
1605|INPEX CORP.
3401|TEIJIN LTD.
3402|TORAY INDUSTRIES, INC.
3861|OJI HOLDINGS CORP.
3405|KURARAY CO., LTD.
3407|ASAHI KASEI CORP.
4004|RESONAC HOLDINGS CORP.
4005|SUMITOMO CHEMICAL CO., LTD.
4021|NISSAN CHEMICAL CORP.
4042|TOSOH CORP.
4043|TOKUYAMA CORP.
4061|DENKA CO., LTD.
4063|SHIN-ETSU CHEMICAL CO., LTD.
4183|MITSUI CHEMICALS, INC.
4188|MITSUBISHI CHEMICAL GROUP CORP.
4208|UBE CORP.
4452|KAO CORP.
4901|FUJIFILM HOLDINGS CORP.
4911|SHISEIDO CO., LTD.
6988|NITTO DENKO CORP.
5019|IDEMITSU KOSAN CO., LTD.
5020|ENEOS HOLDINGS, INC.
5101|THE YOKOHAMA RUBBER CO., LTD.
5108|BRIDGESTONE CORP.
5201|AGC INC.
5214|NIPPON ELECTRIC GLASS CO., LTD.
5233|TAIHEIYO CEMENT CORP.
5301|TOKAI CARBON CO., LTD.
5332|TOTO LTD.
5333|NGK CORP.
5401|NIPPON STEEL CORP.
5406|KOBE STEEL, LTD.
5411|JFE HOLDINGS, INC.
3436|SUMCO CORP.
5706|MITSUI KINZOKU CO., LTD.
5711|MITSUBISHI MATERIALS CORP.
5713|SUMITOMO METAL MINING CO., LTD.
5714|DOWA HOLDINGS CO., LTD.
5801|FURUKAWA ELECTRIC CO., LTD.
5802|SUMITOMO ELECTRIC IND., LTD.
5803|FUJIKURA LTD.
2768|SOJITZ CORP.
8001|ITOCHU CORP.
8002|MARUBENI CORP.
8015|TOYOTA TSUSHO CORP.
8031|MITSUI & CO., LTD.
8053|SUMITOMO CORP.
8058|MITSUBISHI CORP.
1721|COMSYS HOLDINGS CORP.
1801|TAISEI CORP.
1802|OBAYASHI CORP.
1803|SHIMIZU CORP.
1808|HASEKO CORP.
1812|KAJIMA CORP.
1925|DAIWA HOUSE IND. CO., LTD.
1928|SEKISUI HOUSE, LTD.
1963|JGC HOLDINGS CORP.
5631|THE JAPAN STEEL WORKS, LTD.
6103|OKUMA CORP.
6113|AMADA CO., LTD.
6273|SMC CORP.
6301|KOMATSU LTD.
6302|SUMITOMO HEAVY IND., LTD.
6305|HITACHI CONST. MACH. CO., LTD.
6326|KUBOTA CORP.
6361|EBARA CORP.
6367|DAIKIN INDUSTRIES, LTD.
6471|NSK LTD.
6472|NTN CORP.
6473|JTEKT CORP.
7004|KANADEVIA CORP.
7011|MITSUBISHI HEAVY IND., LTD.
7013|IHI CORP.
7012|KAWASAKI HEAVY IND., LTD.
7832|BANDAI NAMCO HOLDINGS INC.
7911|TOPPAN HOLDINGS INC.
7912|DAI NIPPON PRINTING CO., LTD.
7951|YAMAHA CORP.
3289|TOKYU FUDOSAN HOLDINGS CORP.
8801|MITSUI FUDOSAN CO., LTD.
8802|MITSUBISHI ESTATE CO., LTD.
8804|TOKYO TATEMONO CO., LTD.
8830|SUMITOMO REALTY & DEVELOPMENT CO., LTD.
9001|TOBU RAILWAY CO., LTD.
9005|TOKYU CORP.
9007|ODAKYU ELECTRIC RAILWAY CO., LTD.
9008|KEIO CORP.
9009|KEISEI ELECTRIC RAILWAY CO., LTD.
9020|EAST JAPAN RAILWAY CO.
9021|WEST JAPAN RAILWAY CO.
9022|CENTRAL JAPAN RAILWAY CO., LTD.
9064|YAMATO HOLDINGS CO., LTD.
9147|NIPPON EXPRESS HOLDINGS, INC.
9101|NIPPON YUSEN K.K.
9104|MITSUI O.S.K.LINES, LTD.
9107|KAWASAKI KISEN KAISHA, LTD.
9201|JAPAN AIRLINES CO., LTD.
9202|ANA HOLDINGS INC.
9501|TOKYO ELECTRIC POWER COMPANY HOLDINGS, INC.
9502|CHUBU ELECTRIC POWER CO., INC.
9503|THE KANSAI ELECTRIC POWER CO., INC.
9531|TOKYO GAS CO., LTD.
9532|OSAKA GAS CO., LTD.
"""


CHANGE_EVENTS_TEXT = r"""
date|deleted_name|deleted_code|added_name|added_code
Apr/1/2026|GS Yuasa|6674|Kioxia Holdings|285A
Apr/1/2026|CASIO COMPUTER|6952|ARCHION|543A
Apr/1/2026|HINO MOTORS|7205|Pan Pacific International Holdings|7532
Nov/11/2025|Nidec|6594|Ibiden|4062
Oct/1/2025|Citizen Watch|7762|SHIFT|3697
Jul/4/2025|NTT Data Group|9613|Rohm|6963
Apr/1/2025|Mitsubishi Logistics|9301|BayCurrent|6532
Apr/1/2025|Nippon Paper Industries|3863|Nomura Research Institute|4307
Apr/1/2025|DIC|4631|Ryohin Keikaku|7453
Apr/1/2025|Takara Holdings|2531|ZOZO|3092
Apr/1/2025|Sumitomo Osaka Cement|5232|Disco|6146
Apr/1/2025|Pacific Metals|5541|Socionext|6526
Apr/1/2025|Nippon Sheet Glass|5202|Mercari|4385
Apr/1/2025|Mitsui E&S|7003|Lasertec|6920
Apr/1/2025|Matsui Securities|8628|Nitori Holdings|9843
Apr/1/2025|Toyobo|3101|Oriental Land|4661
Apr/1/2025|Nippon Light Metal Holdings|5703|Renesas Electronics|6723
Apr/1/2025|Toho Zinc|5707|Japan Airlines|9201
Oct/4/2022|Maruha Nichiro|1333|Shizuoka Financial Group|5831
Oct/4/2022|Unitika|3103|SMC|6273
Oct/4/2022|Oki Electric Industry|6703|HOYA|7741
Sep/29/2022|Shizuoka Bank|8355|Nidec|6594
Apr/4/2022|Shinsei Bank|8303|ORIX Corporation|8591
Jan/5/2022|||Nippon Express Holdings|9147
Dec/29/2021|Nippon Express|9062||
Dec/2/2021|Nisshinbo Holdings|3105|KEYENCE|6861
Dec/2/2021|Toyo Seikan Group Holdings|5901|Murata Manufacturing|6981
Dec/2/2021|SKY Perfect JSAT Holdings|9412|Nintendo|7974
Dec/2/2021|NTT Docomo|9437|Sharp|6753
Oct/29/2020|FamilyMart|8028|NEXON|3659
Oct/1/2020|Nippon Kayaku|4272|SoftBank|9434
Jul/29/2020|Sony Financial Holdings|8729|Japan Exchange Group|8697
Oct/1/2019|Tokyo Dome|9681|M3|2413
Aug/1/2019|Chiyoda|6366|BANDAI NAMCO Holdings|7832
Mar/27/2019|Showa Shell Sekiyu|5002|Idemitsu Kosan|5019
Mar/18/2019|Pioneer|6773|OMRON|6645
Dec/26/2018|Nisshin Steel|5413|DIC|4631
Oct/1/2018|Furukawa|5715|CyberAgent|4751
Oct/1/2018|Hokuetsu Kishu Paper|3865|Recruit Holdings|6098
Oct/1/2018|Meidensha|6508|Japan Post Holdings|6178
Aug/1/2017|Toshiba|6502|Seiko Epson|6724
Jan/24/2017|Mitsumi Electric|6767|Otsuka Holdings|4578
Oct/3/2016|Nippon Soda|4041|Rakuten|4755
Aug/29/2016|UNY Group Holdings|8270|FamilyMart|8028
Aug/1/2016|Sharp|6753|Yamaha Motor|7272
Apr/4/2016|||Concordia Financial Group|7186
Mar/29/2016|The Bank of Yokohama|8332||
Oct/1/2015|Nitto Boseki|3110|Haseko Corporation|1808
Oct/1/2015|Heiwa Real Estate|8803|DeNA|2432
Apr/2/2014|||Maruha Nichiro|1333
Mar/27/2014|Maruha Nichiro Holdings|1334||
Oct/2/2013|Mitsubishi Paper Mills Ltd.|3864|Tokyu Fudosan Holdings Corporation|3289
Sep/26/2013|Tokyu Land Corporation|8815|Nitto Denko Corporation|6988
Apr/2/2013|||Nippon Paper Industries|3863
Mar/27/2013|Nippon Paper Group|3893||
Sep/26/2012|||Nisshin Steel Holdings|5413
Sep/26/2012|||Nippon Light Metal Holdings|5703
Sep/26/2012|Sumitomo Metal Industries|5405|Tokuyama|4043
Oct/2/2012|Nisshin Steel|5407||
Oct/2/2012|Nippon Light Metal|5701||
Sep/28/2011|CSK|9737|Amada|6113
Sep/28/2011|Mizuho Trust & Banking|8404|Aozora Bank|8304
Sep/28/2011|Mizuho Securities|8606|Sony Financial Holdings|8729
Sep/28/2011|Sanyo Electric|6764|Yaskawa Electric|6506
Sep/28/2011|Panasonic Electric Works|6991|Dainippon Screen Mfg.|7735
Sep/28/2011|Sumitomo Trust & Banking|8403|Dai-ichi Life Insurance|8750
Oct/1/2010|Clarion|6796|Tokyo Tatemono|8804
Sep/28/2010|Mitsubishi Rayon|3404|Nippon Electric Glass|5214
Sep/28/2010|||JX Holdings|5020
Sep/28/2010|||NKSJ Holdings|8630
Sep/28/2010|Nippon Oil|5001|Nisshin Steel|5407
Sep/28/2010|Nippon Mining Holdings|5016||
Sep/28/2010|Sompo Japan Insurance|8755||
Jan/22/2010|||Central Japan Railway|9022
Jan/20/2010|Japan Airlines|9205||
Apr/2/2009|||Meiji Holdings|2269
Apr/2/2009|Meiji Seika Kaisha|2202|Maruha Nichiro Holdings|1334
Apr/2/2009|Meiji Dairies|2261||
Apr/2/2009|Kumagai Gumi|1861|Pacific Metals|5541
Apr/2/2009|Toagosei|4045|Hitachi Construction Machinery|6305
Jul/28/2008|Mitsubishi UFJ Nicos|8583|Matsui Securities|8628
Jul/28/2008|||Isetan Mitsukoshi Holdings|3099
Jul/28/2008|||Mitsui Sumitomo Insurance Group Holdings|8725
Jul/28/2008|Mitsukoshi|2779|Uny|8270
Jul/28/2008|Isetan|8238||
Jul/28/2008|Mitsui Sumitomo Insurance|8752||
Mar/26/2008|||Fukuoka Financial Group|8354
Jan/23/2008|Nikko Cordial|8603||
Mar/26/2008|Nisshin OilliO Group|2602|J. Front Retailing|3086
Mar/26/2008|Topy Industries|7231|SUMCO|3436
Apr/3/2007|||Sky Perfect Jsat|9412
Mar/27/2007|Sky Perfect Communications|4795||
"""


DATE_PATTERNS = (
    "%b/%d/%Y",
    "%b/%-d/%Y",
)


@dataclass(frozen=True)
class EventRow:
    event_date: date
    deleted_name: str
    deleted_code: str
    added_name: str
    added_code: str


def normalize_code(code: str) -> str:
    code = code.strip()
    if not code:
        return ""
    if code.endswith(".T"):
        return code
    return f"{code}.T"


def clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip())


def parse_date(value: str) -> date:
    text = value.strip()
    for pattern in DATE_PATTERNS:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date: {value!r}")


def parse_current_components(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    reader = csv.DictReader(io.StringIO(text.strip()), delimiter="|")
    for record in reader:
        ticker = normalize_code(record.get("ticker", ""))
        company_name = clean_name(record.get("company_name", ""))
        if ticker:
            rows.append((ticker, company_name))
    return rows


def parse_change_events(text: str) -> list[EventRow]:
    rows: list[EventRow] = []
    reader = csv.DictReader(io.StringIO(text.strip()), delimiter="|")
    for record in reader:
        event_date = parse_date(record.get("date", ""))
        rows.append(
            EventRow(
                event_date=event_date,
                deleted_name=clean_name(record.get("deleted_name", "")),
                deleted_code="" if record.get("deleted_code", "").strip() in {"", "--"} else normalize_code(record.get("deleted_code", "")),
                added_name=clean_name(record.get("added_name", "")),
                added_code="" if record.get("added_code", "").strip() in {"", "--"} else normalize_code(record.get("added_code", "")),
            )
        )
    return rows


def build_timeline(
    current_components: list[tuple[str, str]],
    change_rows: list[EventRow],
) -> tuple[list[dict[str, str]], dict[str, set[str]], dict[str, str], date]:
    start_date = date(2006, 8, 1)
    end_date = date(2026, 8, 11)

    current_map = {ticker: name for ticker, name in current_components}
    expected_current_tickers = set(current_map)

    events_by_date: dict[date, list[EventRow]] = {}
    for row in change_rows:
        events_by_date.setdefault(row.event_date, []).append(row)

    ordered_dates = sorted(events_by_date)
    if not ordered_dates:
        raise ValueError("No change history rows were parsed")
    if ordered_dates[-1] > end_date:
        raise ValueError("Change history extends beyond the verification end date")

    active_map = dict(current_map)
    for event_date in sorted(ordered_dates, reverse=True):
        if event_date < start_date:
            break
        for row in events_by_date[event_date]:
            if row.added_code:
                active_map.pop(row.added_code, None)
        for row in events_by_date[event_date]:
            if row.deleted_code:
                active_map[row.deleted_code] = row.deleted_name

    start_snapshot = dict(active_map)
    start_snapshot_tickers = set(start_snapshot)

    rows: list[dict[str, str]] = []
    open_rows: dict[str, dict[str, str]] = {}

    for ticker, name in sorted(start_snapshot.items()):
        open_rows[ticker] = {
            "ticker": ticker,
            "company_name": name,
            "member_from": start_date.isoformat(),
            "member_until": "",
        }

    def close_ticker(ticker: str, event_date: date) -> None:
        row = open_rows.get(ticker)
        if row is None:
            return
        row["member_until"] = event_date.isoformat()
        rows.append(row)
        del open_rows[ticker]

    for event_date in sorted(ordered_dates):
        if event_date <= start_date:
            continue
        for row in events_by_date[event_date]:
            if row.deleted_code:
                close_ticker(row.deleted_code, event_date)
        for row in events_by_date[event_date]:
            if row.added_code:
                if row.added_code in open_rows:
                    raise ValueError(f"Ticker reopened without closing first: {row.added_code} on {event_date}")
                open_rows[row.added_code] = {
                    "ticker": row.added_code,
                    "company_name": row.added_name,
                    "member_from": event_date.isoformat(),
                    "member_until": "",
                }

    rows.extend(sorted(open_rows.values(), key=lambda item: (item["ticker"], item["member_from"])))
    rows.sort(key=lambda item: (item["ticker"], item["member_from"]))

    periods_by_ticker: dict[str, list[tuple[date, date | None]]] = {}
    for item in rows:
        ticker = item["ticker"]
        member_from = datetime.strptime(item["member_from"], "%Y-%m-%d").date()
        member_until = datetime.strptime(item["member_until"], "%Y-%m-%d").date() if item["member_until"] else None
        periods_by_ticker.setdefault(ticker, []).append((member_from, member_until))
        periods = periods_by_ticker[ticker]
        if len(periods) >= 2:
            prev_from, prev_until = periods[-2]
            if prev_until is not None and member_from < prev_until:
                raise ValueError(f"Overlapping periods for {ticker}: {prev_from}..{prev_until} overlaps {member_from}")

    final_active = {ticker: row["company_name"] for ticker, row in open_rows.items()}
    current_matches = set(final_active) == expected_current_tickers
    end_count = len(final_active)
    start_count = len(start_snapshot_tickers)
    no_overlaps = True
    for ticker, periods in periods_by_ticker.items():
        for first, second in zip(periods, periods[1:]):
            _, first_until = first
            second_from, _ = second
            if first_until is not None and second_from < first_until:
                no_overlaps = False
                break
        if not no_overlaps:
            break

    verification = {
        "start_count": start_count,
        "end_count": end_count,
        "current_matches": current_matches,
        "no_overlaps": no_overlaps,
    }
    return rows, verification, final_active, start_date


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ticker", "company_name", "member_from", "member_until"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    current_components = parse_current_components(CURRENT_COMPONENTS_TEXT)
    change_rows = parse_change_events(CHANGE_EVENTS_TEXT)
    rows, verification, current_names, start_date = build_timeline(current_components, change_rows)
    write_csv(rows, OUTPUT_CSV)
    print(f"wrote {len(rows)} rows to {OUTPUT_CSV}")
    print(f"2006-08-01 active count: {verification['start_count']}")
    print(f"2026-08-11 active count: {verification['end_count']}")
    print(f"current set matches official snapshot: {verification['current_matches']}")
    print(f"no overlapping periods per ticker: {verification['no_overlaps']}")


if __name__ == "__main__":
    main()
