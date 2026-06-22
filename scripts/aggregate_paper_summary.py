#!/usr/bin/env python3
"""Agrega snapshot semanal do paper trading e popula paper_trade_summary.

Lê:
  - public.bets_log (mode='paper')
  - public.value_bets
  - public.paper_trade_clv
  - public.paper_trade_state

Escreve:
  - public.paper_trade_summary (uma linha por período, upsert)

Uso:
  python3 scripts/aggregate_paper_summary.py
  python3 scripts/aggregate_paper_summary.py --period-start 2026-06-15 --period-end 2026-06-21

Dependências: supabase >= 1.0, python-dotenv opcional.
Requer as envs SUPABASE_DB_URL ou SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY.
Não grava chaves em disco.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone

try:
    from supabase import create_client  # type: ignore
except Exception as exc:  # pragma: no cover
    print(f"supabase lib ausente: {exc}", file=sys.stderr)
    sys.exit(1)


def _client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY ausentes no ambiente")
    return create_client(url, key)


def _week_bounds(today: date) -> tuple[date, date]:
    """Semana anterior (segunda -> domingo)."""
    weekday = today.weekday()  # 0 = segunda
    last_sunday = today.fromordinal(today.toordinal() - weekday - 1)
    last_monday = last_sunday.fromordinal(last_sunday.toordinal() - 6)
    return last_monday, last_sunday


def _fetch_period(client, period_start: date, period_end: date) -> dict:
    """Lê bets_log e clv para o período e calcula agregados."""
    # state
    state = (
        client.table("paper_trade_state")
        .select("bankroll_current,bankroll_initial")
        .eq("id", 1)
        .execute()
    ).data
    bankroll_current = float(state[0]["bankroll_current"]) if state else 100.0

    # bets_log dentro do período
    bets = (
        client.table("bets_log")
        .select("id,value_bet_id,mode,result,profit_loss,placed_at,settled_at,stake_amount,odd_taken")
        .eq("mode", "paper")
        .execute()
    ).data or []

    def _in_period(row, field: str) -> bool:
        ts = row.get(field)
        if not ts:
            return False
        d = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
        return period_start <= d <= period_end

    period_bets = [b for b in bets if _in_period(b, "placed_at")]

    won = sum(1 for b in period_bets if b.get("result") == "won")
    lost = sum(1 for b in period_bets if b.get("result") == "lost")
    settled_total = won + lost
    profit_units = sum(
        float(b.get("profit_loss") or 0)
        for b in period_bets
        if b.get("result") in ("won", "lost")
    )

    # abertas no início/fim do período
    open_start = sum(
        1
        for b in bets
        if (b.get("result") == "open")
        and (b.get("placed_at") and datetime.fromisoformat(b["placed_at"].replace("Z", "+00:00")).date() < period_start)
    )
    open_end = sum(1 for b in bets if b.get("result") == "open")

    # clv: tenta ler; se tabela vazia, deixa null/0
    clv_avg = None
    clv_pos = 0
    try:
        clv_rows = (
            client.table("paper_trade_clv")
            .select("clv_percent,bets_log_id")
            .execute()
        ).data or []
        if clv_rows:
            values = [float(r["clv_percent"]) for r in clv_rows if r.get("clv_percent") is not None]
            clv_avg = sum(values) / len(values) if values else None
            clv_pos = sum(1 for v in values if v > 0)
    except Exception:
        clv_avg = None
        clv_pos = 0

    meta_progress = f"{settled_total} / 30 liquidadas; {clv_pos} com CLV positivo"

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "open_at_start": open_start,
        "open_at_end": open_end,
        "settled_total": settled_total,
        "won_total": won,
        "lost_total": lost,
        "profit_units": round(profit_units, 2),
        "clv_avg": round(clv_avg, 5) if clv_avg is not None else None,
        "clv_positive_count": clv_pos,
        "meta_progress": meta_progress,
        "bankroll_after": bankroll_current,
    }


def _upsert_summary(client, row: dict) -> None:
    client.table("paper_trade_summary").upsert(
        row, on_conflict="period_start,period_end"
    ).execute()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period-start", type=str, default=None)
    ap.add_argument("--period-end", type=str, default=None)
    args = ap.parse_args()

    today = datetime.now(timezone.utc).date()
    if args.period_start and args.period_end:
        period_start = date.fromisoformat(args.period_start)
        period_end = date.fromisoformat(args.period_end)
    else:
        period_start, period_end = _week_bounds(today)

    client = _client()
    row = _fetch_period(client, period_start, period_end)
    _upsert_summary(client, row)
    print(json.dumps(row, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())