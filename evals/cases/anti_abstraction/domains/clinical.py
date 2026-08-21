UNAVAILABLE_MESSAGE = "Record unavailable. Contact the responsible team before continuing."


def clinical_review_message(record):
    return UNAVAILABLE_MESSAGE if record.needs_review else "Record ready"
