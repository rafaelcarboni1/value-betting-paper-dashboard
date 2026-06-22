#!/usr/bin/env python3
"""Renderiza a tela inicial mínima do dashboard do paper trading.

Lê public.paper_trade_dashboard e gera dashboard/index.html estático.
Sem charts, sem filtros: só banca + aposta aberta + contadores básicos.

Uso:
  python3 scripts/render_paper_dashboard.py
"""
from __future__ import annotations

import html
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = ROOT
OUTPUT_PATH = DASHBOARD_DIR / "index.html"


def _load_env() -> dict:
    env: dict = {}
    candidates = [
        ROOT / ".env.local",
        ROOT / ".env",
        ROOT.parent / ".env.local",
        ROOT.parent / ".env",
        Path.cwd() / ".env.local",
        Path.cwd() / ".env",
    ]
    for env_file in candidates:
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip())
            if env:
                break
    for k, v in os.environ.items():
        if k.startswith("SUPABASE_"):
            env.setdefault(k, v)
    return env


def _fetch_dashboard_row(env: dict) -> dict | None:
    ref = env["SUPABASE_PROJECT_REF"]
    pw = env["SUPABASE_DB_PASSWORD"]
    dsn = (
        f"host=db.{ref}.supabase.co port=5432 dbname=postgres "
        f"user=postgres password={pw} sslmode=require"
    )
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute(
        """
        select home_team, away_team, odd_taken, value_percent, stake_amount,
               bankroll_current, settled_total, won_total, lost_total,
               clv_avg, clv_positive_count, meta_progress_label,
               bet_result, match_status, kickoff_at, policy,
               threshold_percent, stake_cap_percent
        from public.paper_trade_dashboard
        limit 1
        """
    )
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _fmt_pct(value, mult: float = 100.0, decimals: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value) * mult:.{decimals}f}%"


def _fmt_units(value) -> str:
    if value is None:
        return "—"
    return f"{float(value):+.2f}u"


def _render(row: dict | None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not row:
        body = """
        <section class="card">
          <h2>Sem dados ainda</h2>
          <p>O paper trading ainda não tem aposta aberta nem aposta liquidada.</p>
        </section>
        """
    else:
        open_match = (
            f"{row['home_team']} x {row['away_team']}"
            if row.get("home_team")
            else "—"
        )
        kickoff = row["kickoff_at"].strftime("%Y-%m-%d %H:%M UTC") if row.get("kickoff_at") else "—"
        body = f"""
        <section class="grid">
          <div class="card">
            <h2>Banca</h2>
            <div class="big">{row['bankroll_current']:.2f}u</div>
            <div class="meta">política {row['policy']} · threshold {float(row['threshold_percent'])*100:.0f}% · cap stake {float(row['stake_cap_percent'])*100:.2f}%</div>
          </div>
          <div class="card">
            <h2>Meta 30 liquidadas</h2>
            <div class="big">{row['meta_progress_label']}</div>
            <div class="meta">CLV positivo: {row['clv_positive_count']} · CLV médio: {_fmt_pct(row['clv_avg'])}</div>
          </div>
          <div class="card">
            <h2>Apostas liquidadas</h2>
            <div class="big">{row['settled_total']}</div>
            <div class="meta">won: {row['won_total']} · lost: {row['lost_total']}</div>
          </div>
          <div class="card highlight">
            <h2>Aposta aberta</h2>
            <div class="match">{html.escape(open_match)}</div>
            <div class="meta">kickoff: {kickoff}</div>
            <table class="kv">
              <tr><th>Seleção</th><td>{html.escape(row['bet_result'] or 'open')}</td></tr>
              <tr><th>Odd tomada</th><td>Pinnacle @{float(row['odd_taken']):.2f}</td></tr>
              <tr><th>Value estimado</th><td>{_fmt_pct(row['value_percent'])}</td></tr>
              <tr><th>Stake</th><td>{float(row['stake_amount']):.2f}u</td></tr>
              <tr><th>Status</th><td>{html.escape(row['match_status'] or '—')}</td></tr>
            </table>
          </div>
        </section>
        <p class="foot">Gerado em {now}. Construção completa do dashboard bloqueada até 15 liquidadas com CLV positivo.</p>
        """

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Paper Trading — Tela Inicial</title>
<style>
  :root {{
    --bg: #0f1115;
    --card: #161a22;
    --text: #e7ecf3;
    --muted: #8a93a6;
    --accent: #7fd1ff;
    --line: #232a36;
  }}
  body {{ margin: 0; background: var(--bg); color: var(--text); font-family: -apple-system, "SF Pro Display", "Inter", sans-serif; }}
  header {{ padding: 28px 32px; border-bottom: 1px solid var(--line); }}
  header h1 {{ margin: 0 0 4px; font-size: 22px; }}
  header .sub {{ color: var(--muted); font-size: 13px; }}
  main {{ padding: 24px 32px; max-width: 1200px; margin: 0 auto; }}
  .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }}
  .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 18px; }}
  .card.highlight {{ border-color: var(--accent); }}
  .card h2 {{ margin: 0 0 12px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }}
  .card .big {{ font-size: 28px; font-weight: 600; }}
  .card .match {{ font-size: 18px; font-weight: 600; margin-bottom: 6px; }}
  .card .meta {{ margin-top: 8px; font-size: 12px; color: var(--muted); }}
  table.kv {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; }}
  table.kv th {{ text-align: left; color: var(--muted); font-weight: 500; width: 130px; padding: 6px 0; }}
  table.kv td {{ padding: 6px 0; border-top: 1px solid var(--line); }}
  .foot {{ color: var(--muted); font-size: 12px; margin-top: 24px; }}
  @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr 1fr; }} }}
  @media (max-width: 600px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
  <header>
    <h1>Paper Trading — Tela Inicial</h1>
    <div class="sub">elo_home_only · home_only · threshold 10% · quarter_kelly cap 1.5%</div>
  </header>
  <main>
    {body}
  </main>
</body>
</html>
"""


def main() -> int:
    env = _load_env()
    if "SUPABASE_PROJECT_REF" not in env or "SUPABASE_DB_PASSWORD" not in env:
        print("env SUPABASE ausente", file=sys.stderr)
        return 1
    row = _fetch_dashboard_row(env)
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(_render(row), encoding="utf-8")
    print(f"rendered: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())