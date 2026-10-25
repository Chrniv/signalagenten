"""What we trade and what we use as research proxies. Stocks and funds on Avanza only."""

# Stockholm large caps that are or have been in OMXS30. Yahoo has no delisted
# stocks, so this list is survivorship-biased; the stock strategies are judged
# against an equal-weight buy-and-hold of the SAME list to neutralise part of that.
STOCKS = [
    "ABB.ST", "ALFA.ST", "ASSA-B.ST", "ATCO-A.ST", "ATCO-B.ST", "AZN.ST", "BOL.ST",
    "ELUX-B.ST", "ERIC-B.ST", "ESSITY-B.ST", "EVO.ST", "GETI-B.ST", "HEXA-B.ST",
    "HM-B.ST", "INVE-B.ST", "KINV-B.ST", "NDA-SE.ST", "NIBE-B.ST", "SAAB-B.ST",
    "SAND.ST", "SBB-B.ST", "SCA-B.ST", "SEB-A.ST", "SHB-A.ST", "SINCH.ST",
    "SKA-B.ST", "SKF-B.ST", "SSAB-A.ST", "SWED-A.ST", "TEL2-B.ST",
    "TELIA.ST", "VOLV-B.ST", "EPI-A.ST", "LIFCO-B.ST", "ADDT-B.ST", "INDU-C.ST",
    "LUND-B.ST", "AXFO.ST", "TREL-B.ST", "SECU-B.ST",
]

# Research proxies for the funds. First ticker that returns data wins.
# Funds are total-return (dividends reinvested), so total-return indices are preferred.
FUND_PROXIES = {
    # Avanza Sweden / Avanza Zero: Swedish all-cap index fund
    "SE_EQ": {
        "candidates": ["^OMXS30GI", "^OMXSGI", "^OMX"],
        "currency": "SEK",
        "price_index_div_yield": 0.030,   # added only if we fall back to a PRICE index (assumption)
        "fund_fee": 0.0015,               # Avanza Sweden 0.15 %/yr (fund brochure 2026-06-17)
    },
    # Avanza Global (developed markets). S&P 500 TR in SEK as long-history proxy (assumption).
    "GLOBAL_EQ": {
        "candidates": ["^SP500TR", "^GSPC"],
        "currency": "USD",
        "price_index_div_yield": 0.018,
        "fund_fee": 0.0015,               # assumption; check the actual fund's fee at Gate 3
    },
}

FX = {"USD": "SEK=X", "EUR": "EURSEK=X"}      # Yahoo: SEK per 1 unit of foreign currency
BENCHMARK = "^OMX"                            # OMXS30 price index, for reference

# Extra tickers we only probe, to learn what Yahoo has for later (not used by strategies yet).
PROBE = ["^OMXSPI", "IWDA.AS", "URTH", "ACWI", "XACT-OMXS30.ST", "XACTOMXS30.ST"]


def all_tickers() -> list[str]:
    out = list(STOCKS)
    for p in FUND_PROXIES.values():
        out += p["candidates"]
    out += list(FX.values()) + [BENCHMARK] + PROBE
    return list(dict.fromkeys(out))
