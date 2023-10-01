import logging
from io import StringIO

import pandas as pd
import requests
from celery import shared_task
from django.conf import settings
from django.db import DatabaseError

import bnbu_constants.constants as constants
from bnbu_constants.utility import (
    calculate_monthly_profit,
    calculate_utilities,
    determine_property_status,
    process_airdna_api
)
from rental.models import RentalProperty

logger = logging.getLogger(__name__)


def _value_or(value, default):
    return default if pd.isna(value) else value


def _enrich_chunk(data_chunk):
    """Ask AirDNA for projections and derive utilities, profit and status for one chunk of rows."""
    bulk_queries = [
        {
            "address": row.Location,
            "bedrooms": row.Br,
            "bathrooms": row.Ba,
            "accommodates": row.Br * 2 if row.Br else None,
            "currency": constants.CURRENCY_USD,
        }
        for row in data_chunk.itertuples(index=False)
    ]
    response = process_airdna_api(bulk_queries)
    logger.info("Received API response for %d properties", len(bulk_queries))

    projections = pd.DataFrame([
        {
            'ADR': entry['stats']['future']['summary'].get('adr'),
            'Occupancy': entry['stats']['future']['summary'].get('occupancy'),
            'Revenue': entry['stats']['future']['summary'].get('revenue'),
            'Location': entry['details']['address'],
        }
        for entry in response
    ])
    merged_df = pd.merge(data_chunk, projections, on='Location', how='left')
    merged_df['utilities'] = merged_df['Br'].apply(calculate_utilities)
    merged_df['monthly_estimated_profit'] = merged_df.apply(
        lambda row: calculate_monthly_profit(row.Revenue, row.Price, row.Br)[-1], axis=1
    )
    merged_df['property_status'] = merged_df.apply(
        lambda row: determine_property_status(row.Br, row.monthly_estimated_profit), axis=1
    )
    return merged_df


def _build_property(row, user_id, batch_id):
    """Map one enriched row to an unsaved RentalProperty, or None when square footage is missing."""
    square_feet = row.get('Sq. ft.')
    if pd.isna(square_feet):
        logger.warning("Skipping property at Location: %s due to missing 'square_feet'.", row['Location'])
        return None

    rental_property = RentalProperty(
        user_id=user_id,
        location=row['Location'],
        rent=_value_or(row['Price'], 0),
        no_of_bedrooms=_value_or(row['Br'], 0),
        no_of_bathrooms=_value_or(row['Ba'], 0),
        square_feet=int(square_feet),
        property_zillow_link=row['Link'],
        adr=float(_value_or(row.get('ADR'), 0)),
        occupancy_rate=float(_value_or(row.get('Occupancy'), 0)),
        utilities=_value_or(row.get('utilities'), None),
        yearly_projected_revenue=float(_value_or(row.get('Revenue'), 0)),
        monthly_estimated_profit=_value_or(row['monthly_estimated_profit'], 0),
        batch_id=batch_id,
        property_status=row['property_status'],
    )
    rental_property.yearly_rent_cost_util = calculate_monthly_profit(
        rental_property.yearly_projected_revenue, rental_property.rent, rental_property.no_of_bedrooms
    )[2]
    return rental_property


def _save_chunk(merged_df, user_id, batch_id):
    for _, row in merged_df.iterrows():
        try:
            rental_property = _build_property(row, user_id, batch_id)
            if rental_property is None:
                continue
            rental_property.save()
            if rental_property.property_status == constants.APPROVED:
                upload_properties_to_clickup(
                    rental_property.location, rental_property.property_zillow_link, rental_property.property_status
                )
        except (ValueError, TypeError, DatabaseError) as error:
            # One bad row (or a ClickUp failure) must not abort the rest of the batch.
            logger.error("Error saving RentalProperty for Location: %s. Error: %s", row['Location'], error,
                         exc_info=True)


@shared_task(bind=True)
def process_rental_properties_task(self, cleaned_df_json, context):
    batch_id = context['new_batch_id']
    user_id = context['user']
    cleaned_df = pd.read_json(StringIO(cleaned_df_json))
    logger.info("Loaded DataFrame from JSON. Batch ID: %s, Rows: %d", batch_id, len(cleaned_df))

    batch_size = 25
    total_rows = len(cleaned_df)
    results = []
    processed = 0

    for i in range(0, total_rows, batch_size):
        data_chunk = cleaned_df.iloc[i:i + batch_size]
        try:
            merged_df = _enrich_chunk(data_chunk)
        except (ValueError, KeyError, requests.RequestException) as error:
            logger.error("Error calling AirDNA API: %s", error, exc_info=True)
        else:
            _save_chunk(merged_df, user_id, batch_id)
            results.append(merged_df)

        processed += len(data_chunk)
        progress = int(processed / total_rows * 100)
        self.update_state(
            state='PROGRESS', meta={'progress': progress, 'message': f'Processed {processed} of {total_rows} rows'}
        )
        logger.info("Progress updated to %d%%", progress)

    logger.info("Finished Batch ID %s: %d of %d chunks enriched", batch_id, len(results),
                -(-total_rows // batch_size))
    return pd.concat(results).to_json(orient='records') if results else "[]"


def upload_properties_to_clickup(task_name, zillow_link, property_status):
    if not settings.CLICKUP_URL:
        logger.info("CLICKUP_URL is not configured; not pushing %s to ClickUp.", task_name)
        return None
    query_params = {
        "custom_task_ids": True,
        "team_id": settings.TEAM_ID,
    }
    headers = {
        "content-type": "application/json",
        "Authorization": settings.ACCESS_TOKEN,
    }

    zillow_custom_id = settings.ZILLOW_CUSTOM_ID
    property_status_custom_id = settings.PROPERTY_STATUS_CUSTOM_ID

    property_status_options = {
        "Approved": settings.APPROVED,
        "Rejected": "259560c3-e128-4b7a-8265-7353e838dc7c",
        "Call Back": "cebb1b5e-df5d-4d8a-962e-8ab495a16eda",
        "Owner Approval": "2f4670ba-e556-4475-94e1-03db3a986e5a",
        "On Hold": "fc866b1e-88af-4f4c-a5b0-2143d65cb8a4",
        "SEE NOTES": "0ea8ec8e-61e3-4527-a160-da378ad0e3ae",
        "FOR CHI ONLY": "80e99f57-ac03-4225-aaf0-528cbb2bdbfc"
    }

    payload = {
        "name": task_name,
        "status": "to do",
        "custom_fields": [
            {
                "id": zillow_custom_id,
                "value": zillow_link
            },
            {
                "id": property_status_custom_id,
                "value": property_status_options.get(property_status, None)  # Property Status dropdown option
            }
        ]
    }

    logger.debug("Payload sent to ClickUp: %s", payload)

    try:
        response = requests.post(settings.CLICKUP_URL, headers=headers, json=payload, params=query_params, timeout=30)
        response.raise_for_status()
        logger.info("Response from ClickUp: %s", response.json())

        return response.json()
    except requests.exceptions.JSONDecodeError:
        logger.error("ClickUp returned non-JSON. Status: %s", response.status_code)
        raise ValueError(f"JSON decoding failed. Status: {response.status_code}, Response: {response.text}")
    except requests.exceptions.RequestException as e:
        logger.error("Request to ClickUp failed: %s", e)
        raise ValueError(f"Request failed: {e}")
