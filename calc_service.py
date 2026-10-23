import requests

def convert_currency(amount: float, from_curr: str = "USD", to_curr: str = "INR") -> dict:
    try:
        amount = float(amount)
    except Exception:
        amount = 0.0
    from_curr = from_curr.upper().strip()
    to_curr = to_curr.upper().strip()
    url = f"https://open.er-api.com/v6/latest/{from_curr}"

    try:
        resp = requests.get(url, timeout=6)
        resp.raise_for_status()
        data = resp.json()

        if data.get("result") != "success":
            return {"error": f"Currency exchange rate API error: {data.get('error-type', 'unknown')}"}

        rates = data.get("rates", {})
        if to_curr not in rates:
            return {"error": f"Target currency '{to_curr}' not found."}

        rate = rates[to_curr]
        converted = round(amount * rate, 2)
        return {
            "amount": amount,
            "from": from_curr,
            "to": to_curr,
            "rate": rate,
            "result": converted,
            "formatted": f"{amount:,.2f} {from_curr} = {converted:,.2f} {to_curr} (Rate: {rate})"
        }
    except Exception as e:
        return {"error": f"Currency conversion failed: {e}"}

def calculate_emi(principal: float, annual_rate: float, tenure_years: float) -> dict:
    try:
        p = float(principal)
        r = (float(annual_rate) / 12) / 100  # Monthly interest rate
        n = int(float(tenure_years) * 12)    # Total monthly installments

        if r == 0:
            emi = p / n
        else:
            emi = (p * r * ((1 + r) ** n)) / (((1 + r) ** n) - 1)

        total_payment = emi * n
        total_interest = total_payment - p

        return {
            "principal": round(p, 2),
            "annual_rate": annual_rate,
            "tenure_months": n,
            "monthly_emi": round(emi, 2),
            "total_interest": round(total_interest, 2),
            "total_payment": round(total_payment, 2),
            "formatted": f"Monthly EMI: ₹{round(emi, 2):,.2f} | Total Interest: ₹{round(total_interest, 2):,.2f} | Total Payable: ₹{round(total_payment, 2):,.2f}"
        }
    except Exception as e:
        return {"error": f"EMI calculation error: {e}"}
