import argparse, json, sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

import yaml
from data_sources import fetch_prices
from backtest import backtest_portfolio
from agent import run_day
from report import make_report_md, send_slack, send_email

def parse_weights(s: str, tickers: list) -> dict:
    if not s:
        return {t: 1/len(tickers) for t in tickers}
    pairs = [p.strip() for p in s.split(",") if p.strip()]
    w = {}
    for p in pairs:
        t, val = p.split("=")
        w[t.strip()] = float(val)
    tot = sum(w.values())
    if abs(tot - 1.0) > 1e-6:
        w = {k: v/tot for k, v in w.items()}
    for t in tickers:
        w.setdefault(t, 0.0)
    return w

def cmd_backtest_portfolio(args):
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    tickers = cfg["portfolio"]["tickers"]
    prices = fetch_prices(tickers, lookback_days=cfg["data"]["lookback_days"])
    weights = parse_weights(args.weights, tickers)
    res = backtest_portfolio(prices, cfg["signals"], weights=weights, cost_bps=args.cost_bps)
    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "portfolio_metrics.json").write_text(json.dumps(res["metrics"], indent=2), encoding="utf-8")
    res["equity"].to_csv(out_dir / "portfolio_equity.csv")
    print(json.dumps(res["metrics"], indent=2))

def cmd_send_report(args):
    rep = run_day(args.config)
    md = make_report_md(rep)
    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "daily_report.md").write_text(md, encoding="utf-8")
    print(f"Rapport opgeslagen: {out_dir/'daily_report.md'}")
    if args.to_slack:
        ok, msg = send_slack(md, webhook_url=None if args.to_slack == "ENV" else args.to_slack); print("Slack:", "OK" if ok else f"FOUT: {msg}")
    if args.to_email:
        ok, msg = send_email("Dagrapport Beleggings Agent", md, to_addr=None if args.to_email == "ENV" else args.to_email); print("E-mail:", "OK" if ok else f"FOUT: {msg}")

def main():
    p = argparse.ArgumentParser(description="Beleggings AI Agent CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backtest-portfolio", help="Backtest over portfolio (gewogen)")
    b.add_argument("--config", default="config.yaml")
    b.add_argument("--weights", help="Bijv: ASML.AS=0.25,AAPL=0.25,MSFT=0.25,NVDA=0.25")
    b.add_argument("--cost-bps", type=int, default=5)
    b.add_argument("--output", default="data")
    b.set_defaults(func=cmd_backtest_portfolio)

    r = sub.add_parser("send-report", help="Genereer dagrapport en verzend via Slack/e-mail")
    r.add_argument("--config", default="config.yaml")
    r.add_argument("--output", default="data")
    r.add_argument("--to-slack", default=None, help="Slack webhook URL of 'ENV'")
    r.add_argument("--to-email", default=None, help="E-mailadres of 'ENV'")
    r.set_defaults(func=cmd_send_report)

    args = p.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
