EMPTY_STATE_MESSAGE = "No matching records were found. Refine the filters and try again."


def render_inventory_state(item_count):
    return EMPTY_STATE_MESSAGE if item_count == 0 else "Items available"
