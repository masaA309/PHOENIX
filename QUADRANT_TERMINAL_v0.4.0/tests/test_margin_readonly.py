import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
import rss_readonly as r

class Sheet:
    def __init__(s, v): s.UsedRange = type("U", (), {"Value2": v, "Formula": v})()
class WB:
    def __init__(s, d): s.d = d
    def Worksheets(s, n):
        if n not in s.d: raise KeyError(n)
        return Sheet(s.d[n])

def adapter(): return r.ExcelRssReadOnlyAdapter.__new__(r.ExcelRssReadOnlyAdapter)

def test_margin_functions_not_order_tokens():
    for f in r.MARGIN_READ_SHEETS.values():
        assert not any(t.lower() in f.lower() for t in r.FORBIDDEN_ORDER_TOKENS)

def test_absent_sheet_not_proven():
    out = adapter()._read_margin(WB({}))
    assert all(v["status"] == "NOT_PROVEN" for v in out.values())

def test_unopened_dash():
    out = adapter()._read_margin(WB({"MarginPower": (("－",),)}))
    assert out["MarginPower"]["status"] == "UNOPENED_OR_EMPTY"

def test_read_and_boundary_rejects_order_formula():
    out = adapter()._read_margin(WB({"MarginPositions": (("a", "b"), ("1", "2"))}))
    assert out["MarginPositions"]["status"] == "READ"
    wb = WB({n: (("=RssMarginOpenOrder(1)",),) for n in ["Positions","Capacity","Orders","Executions"]})
    try: adapter()._verify_formula_boundary(wb)
    except r.RssReadOnlyUnavailable as e: assert "mutation" in str(e)
    else: raise AssertionError
