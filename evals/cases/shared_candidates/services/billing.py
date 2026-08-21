EMPTY_STATE_MESSAGE = "No matching records were found. Refine the filters and try again."


def render_invoice_state(invoice_count):
    return EMPTY_STATE_MESSAGE if invoice_count == 0 else "Invoices available"
