"""Decimal-only rate calculation, independent of Django and InvenTree."""

from decimal import Decimal, InvalidOperation, localcontext


class ConfigurationError(ValueError):
    """Invalid configuration or unavailable exchange rate."""


def positive(value):
    """Accept bounded, positive, finite decimal values only."""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ConfigurationError("Enter a valid positive exchange rate.") from None
    if not number.is_finite() or not Decimal("1e-12") <= number <= Decimal("1e12"):
        raise ConfigurationError("Rates must be between 0.000000000001 and 1000000000000.")
    return number


def defaults(individual):
    return {
        "global_currency": "USD",
        "rows": {
            "USD": {"mode": "manual", "direction": "foreign_to_lyd", "value": "10"},
            **(
                {c: {"mode": "auto", "via": "USD"} for c in ("GBP", "EUR", "CNY")}
                if individual
                else {}
            ),
        },
    }


def validate(config, individual, valid_codes):
    """Normalize inputs and validate explicit and implicit dependency chains."""
    if not isinstance(config, dict) or set(config) != {"global_currency", "rows"}:
        raise ConfigurationError("Expected a global currency and currency rows.")
    codes = set(valid_codes) - {"LYD"}
    anchor = config["global_currency"]
    if not isinstance(anchor, str) or anchor not in codes:
        raise ConfigurationError("Choose a valid global intermediary other than LYD.")
    source = config["rows"]
    if not isinstance(source, dict) or not source or len(source) > 200:
        raise ConfigurationError("Configure between 1 and 200 currency rows.")
    rows = {}
    for code, row in source.items():
        if code not in codes or not isinstance(row, dict):
            raise ConfigurationError(f"Invalid currency row: {code}.")
        mode = row.get("mode")
        if mode == "manual":
            if set(row) != {"mode", "direction", "value"}:
                raise ConfigurationError(f"{code}: a manual rate needs a direction and value.")
            if row["direction"] not in ("foreign_to_lyd", "lyd_to_foreign"):
                raise ConfigurationError(f"{code}: invalid rate direction.")
            rows[code] = {
                "mode": mode,
                "direction": row["direction"],
                "value": format(positive(row["value"]), "f"),
            }
        elif mode == "auto":
            if set(row) != {"mode", "via"}:
                raise ConfigurationError(f"{code}: select an intermediary currency.")
            via = row["via"]
            if not isinstance(via, str) or via not in codes:
                raise ConfigurationError(f"{code}: invalid intermediary currency.")
            rows[code] = {"mode": mode, "via": via}
        else:
            raise ConfigurationError(f"{code}: select manual or automatic mode.")
    if anchor not in rows or rows[anchor]["mode"] != "manual":
        raise ConfigurationError("The global intermediary must have a manual rate.")
    if not individual and set(rows) != {anchor}:
        raise ConfigurationError("This plugin permits only the global manual rate.")
    for start in rows:
        chain = []
        current = start
        while True:
            if current in chain:
                raise ConfigurationError("Circular dependency: " + " → ".join(chain + [current]))
            chain.append(current)
            row = rows.get(current, {"mode": "auto", "via": anchor})
            if row["mode"] == "manual":
                break
            current = row["via"]
    return {"global_currency": anchor, "rows": rows}


def online_currencies(config, targets):
    """Only request currencies used in automatic edges, excluding manual-only currencies."""
    needed, visited = set(), set()

    def visit(code):
        if code == "LYD" or code in visited:
            return
        visited.add(code)
        row = config["rows"].get(code, {"mode": "auto", "via": config["global_currency"]})
        if row["mode"] == "auto":
            needed.update((code, row["via"]))
            visit(row["via"])

    for target in targets:
        visit(target)
    return needed


def calculate(config, targets, online):
    """Return foreign units per LYD; online rates share any common numeraire."""
    resolved = {"LYD": Decimal(1)}
    visiting = set()

    def resolve(code):
        if code in resolved:
            return resolved[code]
        if code in visiting:
            raise ConfigurationError(f"Circular dependency involving {code}.")
        visiting.add(code)
        row = config["rows"].get(code, {"mode": "auto", "via": config["global_currency"]})
        if row["mode"] == "manual":
            value = positive(row["value"])
            rate = 1 / value if row["direction"] == "foreign_to_lyd" else value
        else:
            via = row["via"]
            if code not in online or via not in online:
                raise ConfigurationError(
                    f"The original online provider has no rate for {via} → {code}."
                )
            rate = resolve(via) * positive(online[code]) / positive(online[via])
        visiting.remove(code)
        resolved[code] = rate
        return rate

    with localcontext() as context:
        context.prec = 36
        for target in sorted(set(targets)):
            resolve(target)
    return resolved


def rebase(lyd_rates, base, targets):
    """Convert a LYD vector to InvenTree's chosen base, without binary floats."""
    wanted = set(targets) | {base}
    if not wanted.issubset(lyd_rates):
        raise ConfigurationError(
            "No complete last-valid rate table is available for these currencies."
        )
    with localcontext() as context:
        context.prec = 36
        denominator = positive(lyd_rates[base])
        result = {code: positive(lyd_rates[code]) / denominator for code in wanted}
    # django-money uses DecimalField(max_digits=20, decimal_places=6).
    for code, value in result.items():
        if value < Decimal("0.000001") or value >= Decimal("1e14"):
            raise ConfigurationError(f"{base} → {code} is outside InvenTree's storage precision.")
    result[base] = Decimal(1)
    return result
