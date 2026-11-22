import pytest
from messages import fmt_money, build_messages

@pytest.mark.parametrize('amount,currency,want', [
    (5000.49,'INR','₹5,000.49'), (6000.75,'INR','₹6,000.75'),
    (0.25,'INR','₹0.25'), (-0.25,'INR','-₹0.25'),
    (1234567.5,'INR','₹12,34,567.50'), (5000,'INR','₹5,000'),
    (5000.49,'USD','$5,000.49'), (1234567.5,'USD','$1,234,567.50'),
    (1.01,'EUR','€1.01'), (1.1,'GBP','£1.10'), (1.25,'AED','AED 1.25'),
    (5000,'USD','$5,000'),
])
def test_money_preserves_minor_units(amount,currency,want):
    assert fmt_money(amount,currency)==want

@pytest.mark.parametrize('tier', ['reminder','firm','escalation','final'])
@pytest.mark.parametrize('currency,want', [('INR','₹5,000.49'),('USD','$5,000.49'),('EUR','€5,000.49'),('GBP','£5,000.49'),('AED','AED 5,000.49')])
def test_all_draft_tiers_preserve_actual_decimal_amount(tier,currency,want):
    bill={'customer':'Acme','invoice_no':'INV-40','amount':5000.49,'due_date':'2026-10-15','tier':tier,'days_overdue':38}
    result=build_messages([bill],currency=currency)[0]
    assert result['amount']==5000.49
    assert all(want in result[key] for key in ['subject','email','whatsapp'])
    assert bill['amount']==5000.49


def test_large_finite_amount_keeps_formatting_without_decimal_context_overflow():
    assert fmt_money(1e30, 'USD') == '$1,000,000,000,000,000,000,000,000,000,000'
