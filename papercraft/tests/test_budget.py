from decimal import Decimal

import pytest

from papercraft.runtime.budget import (
    BudgetExceededError,
    BudgetLedger,
    UnknownModelPricingError,
)


def test_budget_reserves_commits_and_refunds_without_crossing_cap():
    ledger = BudgetLedger(limit_usd=Decimal("0.10"))
    reservation = ledger.reserve(
        call_id="one",
        provider="openai",
        model="gpt-5.6-sol",
        estimated_input_tokens=1000,
        max_output_tokens=1000,
    )
    assert reservation.maximum_cost_usd == Decimal("0.035000")
    assert ledger.remaining_usd == Decimal("0.065000")
    ledger.cancel("one")
    assert ledger.remaining_usd == Decimal("0.10")

    ledger.reserve(
        call_id="two",
        provider="openai",
        model="gpt-5.6-sol",
        estimated_input_tokens=1000,
        max_output_tokens=1000,
    )
    record = ledger.commit("two", input_tokens=500, output_tokens=100)
    assert record.cost_usd == Decimal("0.005500")
    assert ledger.snapshot().spent_usd == Decimal("0.005500")


def test_budget_hard_stops_unknown_or_unaffordable_calls():
    ledger = BudgetLedger(limit_usd=Decimal("0.01"))
    with pytest.raises(BudgetExceededError):
        ledger.reserve(
            call_id="large",
            provider="anthropic",
            model="claude-opus-4-8",
            estimated_input_tokens=1000,
            max_output_tokens=1000,
        )
    with pytest.raises(UnknownModelPricingError):
        ledger.reserve(
            call_id="unknown",
            provider="openai",
            model="unpriced-model",
            estimated_input_tokens=1,
            max_output_tokens=1,
        )
