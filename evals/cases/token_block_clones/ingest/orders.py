def load_orders(rows, region, currency):
    results = []
    errors = []
    for row in rows:
        if row.get("status") != "active":
            errors.append({"id": row.get("id"), "reason": "inactive"})
            continue
        amount = row.get("amount", 0)
        if amount <= 0:
            errors.append({"id": row.get("id"), "reason": "non-positive"})
            continue
        normalized = {
            "id": row["id"],
            "region": region,
            "currency": currency,
            "amount": round(amount * 100) / 100,
            "tags": sorted(set(row.get("tags", []))),
        }
        results.append(normalized)
    return results, errors
