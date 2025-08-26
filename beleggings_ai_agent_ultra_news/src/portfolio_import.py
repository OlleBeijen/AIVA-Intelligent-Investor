import pandas as pd
from io import StringIO

def parse_positions_csv(file_bytes: bytes) -> pd.DataFrame:
    s = file_bytes.decode("utf-8", errors="ignore")
    df = pd.read_csv(StringIO(s))
    cols = {c.lower().strip(): c for c in df.columns}
    if "ticker" not in [c.lower() for c in df.columns] or "qty" not in [c.lower() for c in df.columns]:
        raise ValueError("CSV moet minimaal kolommen 'ticker' en 'qty' bevatten.")
    df = df.rename(columns={cols.get("ticker","ticker"): "ticker", cols.get("qty","qty"): "qty"})
    if "avg_price" in cols: df = df.rename(columns={cols["avg_price"]: "avg_price"})
    if "currency" in cols:  df = df.rename(columns={cols["currency"]: "currency"})
    df["ticker"] = df["ticker"].astype(str).str.strip()
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0.0)
    return df[["ticker","qty"] + [c for c in ["avg_price","currency"] if c in df.columns]]