from modules import configFunctions

config_location = "/config/config.yml"
config = configFunctions.get_config(config_location)

def calculate_term_length(server, amount, is_4k):
    config = configFunctions.get_config(config_location)
    plex_config = config.get(f"PLEX-{server}", {})
    pricing_section = plex_config.get('4k' if is_4k == 'Yes' else '1080p', {})

    one_month_price = pricing_section.get('1Month', 0)
    three_month_price = pricing_section.get('3Month', 0)
    six_month_price = pricing_section.get('6Month', 0)
    twelve_month_price = pricing_section.get('12Month', 0)

    # Check if the amount matches exactly any known subscription length
    if amount == twelve_month_price:
        return 12
    elif amount == six_month_price:
        return 6
    elif amount == three_month_price:
        return 3
    elif amount == one_month_price:
        return 1

    # Check if the amount covers multiple years
    if twelve_month_price != 0:
        if amount > twelve_month_price:
            years_paid_for = amount / twelve_month_price
            if years_paid_for.is_integer():
                return int(years_paid_for * 12)  # Convert years to months

    # Mixed payment scenario: Iteratively calculate possible month combinations
    term_length = 0
    remaining_amount = amount

    # Check for the maximum number of full 12-month subscriptions first
    while remaining_amount >= twelve_month_price:
        term_length += 12
        remaining_amount -= twelve_month_price

    # Check for the maximum number of full 6-month subscriptions
    while remaining_amount >= six_month_price:
        term_length += 6
        remaining_amount -= six_month_price

    # Check for the maximum number of full 3-month subscriptions
    while remaining_amount >= three_month_price:
        term_length += 3
        remaining_amount -= three_month_price

    # Check for the maximum number of full 1-month subscriptions
    while remaining_amount >= one_month_price:
        term_length += 1
        remaining_amount -= one_month_price

    # Handle small overpayments by checking if the remaining amount is negligible
    if remaining_amount < one_month_price:
        return term_length

    # If the remaining amount is still significant, then the payment does not exactly match any subscription plan
    return 0
