import bnbu_constants.constants as constants
import pandas as pd
from django.conf import settings
import logging

import requests

logger = logging.getLogger(__name__)
AIRDNA_ATTEMPTS = 5


def validate_file_type(file):
    return file.name.lower().endswith(tuple(constants.VALID_FILE_EXTENSION))


def file_to_df(file):
    if file.name.lower().endswith(".csv"):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)
    return df


def validate_df(df):
    missing_cols = []
    if any(col not in df.columns for col in constants.REQUIRED_COLS):
        missing_cols = set(constants.REQUIRED_COLS) - set(df.columns)
    return missing_cols


def normalize_column(df, col_name):
    df[col_name] = df[col_name].astype(str).str.extract(r"(\d+)").astype(float)


def normalize_df(df):
    df = df.dropna(subset=constants.IMP_COLS)
    return df


def clean_price(price):
    try:
        return int(str(price).replace("$", "").replace("/mo", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def process_airdna_api(bulk_queries):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.AIRDNA_API_KEY}",
    }
    payload = {"queries": bulk_queries}
    if not settings.AIRDNA_URL:
        raise ValueError("AIRDNA_URL is not configured; rental rows cannot be enriched.")

    for attempt in range(1, AIRDNA_ATTEMPTS + 1):
        try:
            response = requests.post(settings.AIRDNA_URL, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
        except requests.exceptions.RequestException as error:
            logger.warning("AirDNA request attempt %d/%d failed: %s", attempt, AIRDNA_ATTEMPTS, error)
            continue
        results = response.json().get("payload", {}).get("results")
        if not results:
            raise ValueError("No results returned from AirDNA.")
        return results

    raise ValueError(f"AirDNA request failed after {AIRDNA_ATTEMPTS} attempts.")


def calculate_utilities(no_of_bedroom):
    return no_of_bedroom * 2000


def calculate_monthly_profit(annual_revenue, monthly_rent, no_of_bedroom):
    if not annual_revenue or not monthly_rent or not no_of_bedroom:
        return None, None, None

    utilities = calculate_utilities(no_of_bedroom)
    yearly_rent_cost_util = (monthly_rent * 12) + utilities
    monthly_estimated_profit = (annual_revenue - yearly_rent_cost_util) / 12
    return utilities, annual_revenue, yearly_rent_cost_util, round(monthly_estimated_profit, 2)


def determine_property_status(no_of_bedrooms, monthly_estimated_profit):
    """Determine the property status based on number of bedrooms and monthly profit."""
    if monthly_estimated_profit is None:
        return "Error"

    if no_of_bedrooms == 1 and monthly_estimated_profit >= 1000:
        return "Approved"
    elif no_of_bedrooms == 2 and monthly_estimated_profit >= 1500:
        return "Approved"
    elif no_of_bedrooms >= 3 and monthly_estimated_profit >= 2000:
        return "Approved"
    else:
        return "Rejected"


def to_chat_messages(system_message, chat_history):
    """Build an OpenAI message list; stored history carries timestamps the API rejects."""
    return [{"role": "system", "content": system_message}] + [
        {"role": entry["role"], "content": entry["content"]} for entry in chat_history
    ]
