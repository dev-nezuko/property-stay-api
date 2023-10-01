from __future__ import absolute_import, unicode_literals
from celery import shared_task, current_task
import pandas as pd
import bnbu_constants.constants as constants
from bnbu_constants.utility import (
    calculate_monthly_profit,
    calculate_utilities,
    determine_property_status,
    process_airdna_api
)
from rental.models import RentalProperty
from datetime import datetime
import logging
from io import StringIO
from django.contrib.auth import get_user_model
from tqdm import tqdm
from django.conf import settings
import requests

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def process_rental_properties_task(self, cleaned_df_json, context):
    try:
        # Convert JSON back to DataFrame
        batch_id = context['new_batch_id']
        user_id = context['user']
        cleaned_df = pd.read_json(StringIO(cleaned_df_json))  # Wrap JSON in StringIO
        logger.info("Loaded DataFrame from JSON. Batch ID: %s, Rows: %d", batch_id, len(cleaned_df))
    except Exception as e:
        logger.error("Error loading DataFrame from JSON: %s", e, exc_info=True)
        raise

    batch_size = 25
    total_rows = len(cleaned_df)
    results = []

    # Initialize tqdm progress bar
    with tqdm(total=total_rows, desc="Processing", unit="row") as pbar:
        for i in range(0, total_rows, batch_size):
            bulk_queries = []
            data_chunk = cleaned_df.iloc[i:i + batch_size]
            logger.info("Processing chunk %d to %d. Total rows: %d", i, i + len(data_chunk), len(data_chunk))

            for row in data_chunk.itertuples(index=False):
                query = {
                    "address": row.Location,
                    "bedrooms": row.Br,
                    "bathrooms": row.Ba,
                    "accommodates": row.Br * 2 if row.Br else None,
                    "currency": constants.CURRENCY_USD,
                }
                bulk_queries.append(query)

            try:
                response = process_airdna_api(bulk_queries)
                logger.info("Received API response for %d properties", len(bulk_queries))
            except Exception as e:
                logger.error("Error calling AirDNA API: %s", e, exc_info=True)
                continue

            relevant_information = [
                {
                    'ADR': entry['stats']['future']['summary'].get('adr'),
                    'Occupancy': entry['stats']['future']['summary'].get('occupancy'),
                    'Revenue': entry['stats']['future']['summary'].get('revenue'),
                    'Location': entry['details']['address'],
                }
                for entry in response
            ]
            response_dataframe = pd.DataFrame(relevant_information)
            merged_df = pd.merge(data_chunk, response_dataframe, on='Location', how='left')
            logger.debug("Merged DataFrame for chunk %d to %d:\n%s", i, i + len(data_chunk), merged_df)

            # Calculate utilities, monthly profit, and property status
            merged_df['utilities'] = merged_df['Br'].apply(calculate_utilities)
            merged_df['monthly_estimated_profit'] = merged_df.apply(
                lambda row: calculate_monthly_profit(row.Revenue, row.Price, row.Br)[-1],
                axis=1
            )
            merged_df['property_status'] = merged_df.apply(
                lambda row: determine_property_status(row.Br, row.monthly_estimated_profit),
                axis=1
            )
            logger.info("Calculated additional metrics for chunk %d to %d", i, i + len(data_chunk))

            # Save processed properties
            for _, row in merged_df.iterrows():
                try:
                    # Validate and handle missing or NaN values
                    square_feet = row.get('Sq. ft.')
                    adr = row.get('ADR')
                    occupancy_rate = row.get('Occupancy')
                    revenue = row.get('Revenue')

                    # Handle NaN values and ensure valid data for saving
                    if pd.isna(square_feet):
                        logger.warning("Skipping property at Location: %s due to missing 'square_feet'.", row['Location'])
                        continue  # Skip this row

                    # Ensure all numeric fields are valid
                    adr = 0 if pd.isna(adr) else float(adr)
                    occupancy_rate = 0 if pd.isna(occupancy_rate) else float(occupancy_rate)
                    revenue = 0 if pd.isna(revenue) else float(revenue)

                    utilities = row.get('utilities') if pd.notna(row.get('utilities')) else None

                    # Save to RentalProperty model
                    rental_property = RentalProperty(
                        user_id=user_id,
                        location=row['Location'],
                        rent=row['Price'] if not pd.isna(row['Price']) else 0,  # Default to 0 if missing
                        no_of_bedrooms=row['Br'] if not pd.isna(row['Br']) else 0,
                        no_of_bathrooms=row['Ba'] if not pd.isna(row['Ba']) else 0,
                        square_feet=int(square_feet) if not pd.isna(square_feet) else 0,  # Ensure square_feet is valid
                        property_zillow_link=row['Link'],
                        adr=adr, 
                        occupancy_rate=occupancy_rate,
                        utilities=utilities,
                        yearly_projected_revenue=revenue,
                        monthly_estimated_profit=row['monthly_estimated_profit'] if not pd.isna(row['monthly_estimated_profit']) else 0,
                        batch_id=batch_id,
                        property_status=row['property_status'],
                        created_at=datetime.now(),
                        updated_at=datetime.now(),
                    )
                    rental_property.yearly_rent_cost_util = calculate_monthly_profit(
                        rental_property.yearly_projected_revenue, rental_property.rent, rental_property.no_of_bedrooms
                    )[2]

                    rental_property.save()
                    if rental_property.property_status == "Approved":
                        result = upload_properties_to_clickup(rental_property.location, rental_property.property_zillow_link, rental_property.property_status)
                    logger.debug("Saved RentalProperty: %s", rental_property)
                except Exception as e:
                    logger.error("Error saving RentalProperty for Location: %s. Error: %s", row['Location'], e, exc_info=True)

            results.append(merged_df)

            # Update progress in the progress bar
            pbar.update(len(data_chunk))
            # Also update the Celery task state with the current progress
            progress = int(pbar.n / total_rows * 100)
            self.update_state(state='PROGRESS', meta={'progress': progress, 'message': f'Processed {pbar.n} of {total_rows} rows'})
            logger.info("Progress updated to %d%%", progress)

    try:
        self.update_state(state='SUCCESS', meta={'progress': 100, 'message': 'Task completed successfully'})
        logger.info("Successfully processed all chunks for Batch ID: %s", batch_id)
        result_json = pd.concat(results).to_json(orient='records')
        return result_json
    except Exception as e:
        logger.error("Error concatenating results: %s", e, exc_info=True)
        raise

def upload_properties_to_clickup(task_name, zillow_link, property_status):
    query_params = {
        "custom_task_ids": True,
        "team_id": settings.TEAM_ID,
    }
    headers = {
        "content-type": "application/json",
        "Authorization":settings.ACCESS_TOKEN,
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

    # Log the payload being sent to ClickUp
    logger.debug("Payload sent to ClickUp: %s", payload)

    try:
        response = requests.post(settings.CLICKUP_URL, headers=headers, json=payload, params=query_params)
        response.raise_for_status()  # Raises an HTTPError for 4xx/5xx responses
        
        # Log the response from ClickUp
        logger.info("Response from ClickUp: %s", response.json())
        
        return response.json()
    except requests.exceptions.JSONDecodeError:
        logger.error(f"JSON decoding failed. Status: {response.status_code}, Response: {response.text}")
        raise ValueError(f"JSON decoding failed. Status: {response.status_code}, Response: {response.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request to ClickUp failed: {e}")
        raise ValueError(f"Request failed: {e}")
