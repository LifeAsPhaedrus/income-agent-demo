"""Conservative fee estimates, never taxes or guaranteed earnings."""

import math


def estimate(p, amount=None):
    budget = p.get("budget") or {}
    src = p.get("source", "Freelancer")
    kind = budget.get("type")
    currency = budget.get("currency")
    gross = amount if amount is not None else budget.get("maximum")
    result = {
        "gross_basis": "Proposed bid"
        if amount is not None
        else "Advertised maximum (not guaranteed)",
        "gross_amount": gross,
        "currency": currency,
        "unit": "hour"
        if kind == "hourly"
        else "project"
        if kind == "fixed"
        else "month"
        if kind == "monthly"
        else "unknown",
        "fee_amount": None,
        "net_amount": None,
        "fee_policy": "Unknown",
        "note": "Before taxes, withdrawal/FX charges, expenses and unpaid time. Not guaranteed earnings.",
        "policy_url": None,
    }
    valid = type(gross) in (int, float) and math.isfinite(gross) and gross > 0
    if src == "Freelancer":
        result["policy_url"] = "https://www.freelancer.com/feesandcharges"
        result["fee_policy"] = (
            "10% for hourly; fixed price 10% or US$5 minimum, whichever is greater"
        )
        if valid and (kind == "hourly" or kind == "fixed" and currency == "USD"):
            fee = max(5, gross * 0.1) if kind == "fixed" else gross * 0.1
            result.update(fee_amount=round(fee, 2), net_amount=round(gross - fee, 2))
        elif kind == "fixed" and currency != "USD":
            result["note"] += (
                " USD minimum cannot be converted without a verified exchange rate."
            )
    elif src == "Remotive":
        result.update(
            gross_amount=None,
            fee_policy="Job-board lead; employer/pay arrangement must be checked",
            policy_url="https://remotive.com/terms-of-use",
        )
        result["note"] = (
            "Salary shown as source text; fee deductions, pay period and actual take-home unverified. No paid Remotive subscription purchased."
        )
    elif src == "Contra":
        result.update(
            fee_policy="Contra fees and payment method require verification",
            policy_url="https://contra.com/pricing",
        )
    return result


def label(e):
    if e["net_amount"] is None:
        return "Estimated take-home: unknown. " + e["fee_policy"] + ". " + e["note"]
    return f"{e['gross_basis']}: {e['currency']} {e['gross_amount']:.2f}/{e['unit']} − estimated fee {e['fee_amount']:.2f} = {e['net_amount']:.2f} before taxes and other costs."
