from .exchange_rate import exchange_rate_service


async def calculate_cost(
    price: float,
    currency: str,
    payment_method: str,
    c2c_rate: float | None,
    api_key: str = "",
) -> dict:
    currency = currency.upper()
    if payment_method == "alipay":
        rate = 1.0 if currency == "CNY" else (await exchange_rate_service.rates(currency, api_key))["CNY"]
        cny_cost = price * rate
        return {
            "payment_method": "alipay",
            "original_price": price,
            "original_currency": currency,
            "conversion_rate": rate,
            "converted_amount": cny_cost,
            "fee_rate": 0,
            "usdt_charge": None,
            "c2c_rate": None,
            "cny_cost": round(cny_cost, 2),
            "formula": f"{price:.2f} {currency} × {rate:.4f} = ¥{cny_cost:.2f}",
        }

    if currency == "CNY":
        raise ValueError("CNY subscriptions cannot use bank-card payment")
    usd_rate = 1.0 if currency == "USD" else (await exchange_rate_service.rates(currency, api_key))["USD"]
    usd_amount = price * usd_rate
    usdt_charge = usd_amount * 1.03
    return {
        "payment_method": "bank_card",
        "original_price": price,
        "original_currency": currency,
        "conversion_rate": usd_rate,
        "converted_amount": round(usd_amount, 2),
        "fee_rate": 0.03,
        "usdt_charge": round(usdt_charge, 4),
        "c2c_rate": None,
        "cny_cost": None,
        "formula": f"{price:.2f} {currency} × {usd_rate:.4f} × 1.03 = {usdt_charge:.4f} USDT",
        "required_usdt": round(usdt_charge, 4),
    }
