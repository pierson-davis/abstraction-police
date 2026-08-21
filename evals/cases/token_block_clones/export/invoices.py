def load_invoices(records, market, unit):
    accepted = []
    rejected = []
    for record in records:
        if record.get("status") != "active":
            rejected.append({"id": record.get("id"), "reason": "inactive"})
            continue
        total = record.get("amount", 0)
        if total <= 0:
            rejected.append({"id": record.get("id"), "reason": "non-positive"})
            continue
        shaped = {
            "id": record["id"],
            "region": market,
            "currency": unit,
            "amount": round(total * 100) / 100,
            "tags": sorted(set(record.get("tags", []))),
        }
        accepted.append(shaped)
    return accepted, rejected
