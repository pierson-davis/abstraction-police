UNAVAILABLE_MESSAGE = "Record unavailable. Contact the responsible team before continuing."


def billing_hold_message(account):
    return UNAVAILABLE_MESSAGE if account.is_on_hold else "Account ready"
