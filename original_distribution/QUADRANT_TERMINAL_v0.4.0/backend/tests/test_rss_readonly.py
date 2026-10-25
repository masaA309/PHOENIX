from rss_readonly import ExcelRssReadOnlyAdapter, FORBIDDEN_ORDER_TOKENS, READ_ONLY_FUNCTIONS


def test_position_parser_maps_official_headers():
    rows = [
        ["=RssPositionList()"],
        ["銘柄コード", "銘柄名称", "口座区分", "保有数量", "発注数量", "平均取得価額", "時価", "前日比", "前日比率", "時価評価額", "評価損益額", "評価損益率"],
        ["7203", "トヨタ自動車", "特定", 100, 0, 2900, 3000, 25, 0.84, 300000, 10000, 3.45],
    ]
    positions, watchlist = ExcelRssReadOnlyAdapter._parse_positions(rows)
    assert positions[0]["ticker"] == "7203.T"
    assert positions[0]["account_type"] == "特定"
    assert positions[0]["pnl"] == 10000
    assert watchlist[0]["score"] is None


def test_account_is_estimated_from_read_only_fields():
    rows = [
        ["=RssCapacityList()"],
        ["現物買付可能額", "信用口座_保証金余裕額"],
        [500000, 0],
    ]
    positions = [{"market_value": 300000, "pnl": 10000, "day_change": 25, "qty": 100}]
    account = ExcelRssReadOnlyAdapter._parse_account(rows, positions)
    assert account["equity"] == 800000
    assert account["buying_power"] == 500000
    assert account["unrealized_pnl"] == 10000
    assert account["day_pnl"] == 2500


def test_readonly_function_allowlist_and_mutation_denylist_are_disjoint():
    assert READ_ONLY_FUNCTIONS
    for allowed in READ_ONLY_FUNCTIONS:
        assert all(token.lower() not in allowed.lower() for token in FORBIDDEN_ORDER_TOKENS)
