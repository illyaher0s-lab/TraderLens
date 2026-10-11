from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


CENT = Decimal("0.01")
ZERO_MONEY = Decimal("0.00")


@dataclass(frozen=True)
class DividendEvent:
    """Validated per-share cash dividend with its source references."""

    symbol: str
    ann_date: date
    record_date: date
    ex_date: date
    pay_date: date
    div_cash: Decimal
    source_refs: tuple[str, ...]

    @property
    def key(self) -> tuple[str, date]:
        # One announced cash plan per symbol and announcement date.
        return self.symbol, self.ann_date

    @property
    def event_id(self) -> str:
        return f"{self.symbol}:{self.ann_date.isoformat()}"


class DividendLedger:
    """Minimal entitlement, receivable, and payment ledger for a backtest.

    ``div_cash`` is CNY per share. Holdings are captured at record-date close,
    receivables are booked on ex-date, and payments are posted after the pay-date
    session's fills. Cash amounts use Decimal and round half up to fen.
    """

    def __init__(self, events: Iterable[Mapping[str, object]]):
        by_key: dict[tuple[str, date], DividendEvent] = {}
        refs_by_key: dict[tuple[str, date], list[str]] = {}

        for raw in events:
            event = self._parse_event(raw)
            existing = by_key.get(event.key)
            if existing is None:
                by_key[event.key] = event
                refs_by_key[event.key] = list(event.source_refs)
                continue

            if self._details(existing) != self._details(event):
                raise ValueError(
                    f"conflicting dividend event for {event.symbol} announced "
                    f"on {event.ann_date.isoformat()}"
                )
            refs = refs_by_key[event.key]
            for ref in event.source_refs:
                if ref not in refs:
                    refs.append(ref)

        self.events = tuple(
            DividendEvent(
                symbol=item.symbol,
                ann_date=item.ann_date,
                record_date=item.record_date,
                ex_date=item.ex_date,
                pay_date=item.pay_date,
                div_cash=item.div_cash,
                source_refs=tuple(refs_by_key[key]),
            )
            for key, item in sorted(by_key.items(), key=lambda pair: pair[0])
        )
        self._entitled_quantity: dict[str, int] = {}
        self._receivables: dict[str, Decimal] = {}
        self._settled: set[str] = set()

    @staticmethod
    def _details(event: DividendEvent) -> tuple[date, date, date, Decimal]:
        return event.record_date, event.ex_date, event.pay_date, event.div_cash

    @classmethod
    def _parse_event(cls, raw: Mapping[str, object]) -> DividendEvent:
        if not isinstance(raw, Mapping):
            raise ValueError("dividend event must be a mapping")

        symbol = raw.get("ts_code")
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("dividend event requires a non-empty ts_code")

        ann_date = cls._parse_date(raw.get("ann_date"), "ann_date")
        record_date = cls._parse_date(raw.get("record_date"), "record_date")
        ex_date = cls._parse_date(raw.get("ex_date"), "ex_date")
        pay_date = cls._parse_date(raw.get("pay_date"), "pay_date")
        if not ann_date <= record_date <= ex_date <= pay_date:
            raise ValueError(
                "dividend dates must satisfy ann_date <= record_date <= ex_date <= pay_date"
            )

        try:
            div_cash = Decimal(str(raw.get("div_cash")))
        except (InvalidOperation, ValueError):
            raise ValueError("div_cash must be a finite positive CNY-per-share amount") from None
        if not div_cash.is_finite() or div_cash <= 0:
            raise ValueError("div_cash must be a finite positive CNY-per-share amount")

        source_ref = raw.get("source_ref")
        if not isinstance(source_ref, str) or not source_ref.strip():
            raise ValueError("dividend event requires a non-empty source_ref")

        return DividendEvent(
            symbol=symbol.strip(),
            ann_date=ann_date,
            record_date=record_date,
            ex_date=ex_date,
            pay_date=pay_date,
            div_cash=div_cash,
            source_refs=(source_ref.strip(),),
        )

    @staticmethod
    def _parse_date(value: object, field_name: str) -> date:
        if isinstance(value, datetime):
            raise ValueError(f"{field_name} must be a date, not a datetime")
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass
        raise ValueError(f"{field_name} must be a valid ISO date")

    def validate_for_backtest(
        self,
        start_date: date,
        end_date: date,
        trading_dates: Iterable[date],
    ) -> None:
        trading_set = set(trading_dates)
        for event in self.events:
            if event.record_date < start_date <= event.ex_date:
                raise ValueError(
                    f"dividend {event.event_id} has a record date before the backtest; "
                    "opening entitlement holdings are unavailable"
                )
            if event.ex_date < start_date <= event.pay_date:
                raise ValueError(
                    f"dividend {event.event_id} has an ex-date before the backtest; "
                    "opening receivable is unavailable"
                )
            for field_name, event_date in (
                ("record_date", event.record_date),
                ("ex_date", event.ex_date),
            ):
                if start_date <= event_date <= end_date and event_date not in trading_set:
                    raise ValueError(
                        f"dividend {event.event_id} {field_name} is not a trading date"
                    )

    def settle_due_at_open(self, current_date: date, portfolio) -> None:
        """Settle non-trading-day pay dates before the first later session's fills."""
        for event in self.events:
            if event.pay_date < current_date:
                self._settle(event, portfolio)

    def process_eod(self, current_date: date, portfolio) -> None:
        """Process record, ex, and exact pay dates after the session's orders."""
        for event in self.events:
            if event.record_date == current_date:
                position = portfolio.positions.get(event.symbol)
                self._entitled_quantity[event.event_id] = (
                    position.quantity if position is not None else 0
                )

        for event in self.events:
            if event.ex_date == current_date:
                quantity = self._entitled_quantity.get(event.event_id, 0)
                amount = (event.div_cash * quantity).quantize(
                    CENT, rounding=ROUND_HALF_UP
                )
                self._receivables[event.event_id] = amount

        for event in self.events:
            if event.pay_date == current_date:
                self._settle(event, portfolio)

    def _settle(self, event: DividendEvent, portfolio) -> None:
        if event.event_id in self._settled or event.event_id not in self._receivables:
            return
        amount = self._receivables.pop(event.event_id)
        cash = Decimal(str(portfolio.cash)) + amount
        portfolio.cash = float(cash)
        self._settled.add(event.event_id)

    def total_receivable(self) -> Decimal:
        return sum(self._receivables.values(), ZERO_MONEY)

    def total_value(self, portfolio) -> Decimal:
        cash = Decimal(str(portfolio.cash))
        market_value = Decimal(str(portfolio.market_value()))
        return cash + market_value + self.total_receivable()

    def provenance_lines(self) -> list[str]:
        return [
            f"Dividend input {event.event_id}; sources: "
            f"{', '.join(event.source_refs)}"
            for event in self.events
        ]
