# /Users/dev/Documents/bnbu-backend-api/bnbu_backend_api/lease/utils.py
from __future__ import absolute_import, unicode_literals
import io
import json
import logging
from datetime import datetime, timezone
import os
import re
import time
import PyPDF2
from django.conf import settings
import openai
import requests
import tiktoken

logger = logging.getLogger(__name__)


def analyze_chunk(chunk, system_message):
    """
    Analyzes a chunk of text using OpenAI GPT-4 API with retries for handling rate limits.
    """
    retry_attempts = 3
    for attempt in range(retry_attempts):
        try:
            logger.info(f"Analyzing chunk: Attempt {attempt + 1} of {retry_attempts}")
            openai.api_key = settings.OPENAI_API_KEY
            encoding = tiktoken.get_encoding("cl100k_base")
            chunk_tokens = len(encoding.encode(chunk))

            # Summarize if the chunk exceeds token limit
            if chunk_tokens > 4096:
                logger.warning("Chunk exceeds token limit. Summarizing.")
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {
                            "role": "system",
                            "content": "Please summarize the following text to fit within the token limit.",
                        },
                        {"role": "user", "content": chunk},
                    ],
                )
                return response["choices"][0]["message"]["content"]
            else:
                # Analyze the chunk directly
                logger.info("Chunk within token limit. Analyzing directly.")
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": chunk},
                    ],
                )
                return response["choices"][0]["message"]["content"]
        except openai.error.RateLimitError:
            logger.error(f"RateLimitError: {e}")
            if attempt < retry_attempts - 1:
                logger.info("Retrying after 30 seconds.")
                time.sleep(30)  # Wait before retrying
            else:
                logger.critical("Rate limit exceeded after multiple attempts.")
                return {
                    "status": "Error",
                    "message": "Rate limit exceeded after multiple attempts",
                }
        except Exception as e:
            logger.exception("An error occurred in analyze_chunk.")
            return str(e)


def analyze_document_with_gpt(document):
    """
    Analyzes a PDF document by downloading it from Cloudinary, splitting it into chunks,
    processing each chunk with GPT-4, and combining the results for final analysis.
    """
    logger.info(f"Analyzing document ID: {document.id}")
    try:
        # Ensure the document has a valid file URL
        if not document.file_url:
            logger.error("Document file URL is not set.")
            raise ValueError("Document file URL is not set.")

        # Fetch the document from Cloudinary
        response = requests.get(document.file_url, stream=True)
        if response.status_code != 200:
            logger.error(f"Failed to fetch document from Cloudinary. Status code: {response.status_code}")
            raise ValueError("Failed to fetch document from Cloudinary.")

        file_content = io.BytesIO(response.content)
        reader = PyPDF2.PdfReader(file_content)
        num_pages = len(reader.pages)
        logger.info(f"Document has {num_pages} pages.")
        chunk_size = 5
        chunks = [
            "".join(
                reader.pages[j].extract_text()
                for j in range(i, min(i + chunk_size, num_pages))
            )
            for i in range(0, num_pages, chunk_size)
        ]
        logger.info(f"Document split into {len(chunks)} chunks.")

        if not chunks:
            logger.error("No text found in the document.")
            raise ValueError("No text found in the document.")

        # Initialize OpenAI API
        openai.api_key = settings.OPENAI_API_KEY
        encoding = tiktoken.get_encoding("cl100k_base")

        # Define the system message for the document analysis, including lease details
        system_message = f"""
            This GPT acts as a short-term rental contract expert designed to help users, especially students, review rental leases.
            The primary goal is to assist users in identifying unusual clauses, potential legal risks, and ensuring transparency within the lease documents.
            It will always identify key financial details such as rent amounts and security deposits from uploaded leases.
            Additionally, the GPT will carefully review the lease for unfavorable terms to the tenant, such as disproportionate fees, restrictions, or unclear responsibilities,
            and will make suggestions for favorable terms and strategies for negotiation.
            For example, it will suggest negotiating points such as reduced late fees, prorated rent for partial occupancy months, or limits on certain restrictions like subletting.
            It will also ensure that checkbox provisions are correctly applied, particularly regarding assignment, subleasing, and permissions.
            The length of the lease, any related fees, and responsibilities of both the landlord and tenant are key areas of focus.

            Please analyze the lease document and provide a clear assessment.
            Specifically, include a status for the lease:
            - "Approved" if the lease is favorable and there are no significant concerns.
            - "Rejected" if there are major unfavorable clauses or legal risks.
            - "Draft" if the lease is in an incomplete or negotiable state, and suggest any improvements or issues that need addressing.

            Please ensure the status is clearly mentioned in the response along with a summary of your findings.
            """

        # logger.info("Starting group task for chunk analysis.")
        # group_results = group(analyze_chunk.s(chunk, system_message) for chunk in chunks)()
        # chunk_summaries = group_results.get()
        # chunk_summaries = [result.get('message', '') if isinstance(result, dict) else str(result) for result in chunk_summaries]
        # logger.info("Chunk analysis completed. Combining summaries.")
        # combined_summary = " ".join(chunk_summaries)
        # logger.info(f"Combined summary token count: {len(tiktoken.get_encoding('cl100k_base').encode(combined_summary))}")

        chunk_summaries = []
        # Process each chunk sequentially
        for chunk in chunks:
            result = analyze_chunk(chunk, system_message)
            if isinstance(result, str):
                chunk_summaries.append(result)

        combined_summary = " ".join(chunk_summaries)

        combined_tokens = len(encoding.encode(result))

        if combined_tokens > 4096:
            logger.warning("Combined summary exceeds token limit. Summarizing.")
            final_summary_response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "Please summarize the following document to fit within the token limit.",
                    },
                    {"role": "user", "content": combined_summary},
                ],
            )
            combined_summary = final_summary_response["choices"][0]["message"][
                "content"
            ]

        logger.info("Performing final analysis.")
        final_analysis_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": combined_summary},
            ],
        )
        analysis_result = final_analysis_response["choices"][0]["message"][
            "content"
        ].strip()
        created_time = datetime.fromtimestamp(
            final_analysis_response["created"], tz=timezone.utc
        ).isoformat()

        if "approved" in analysis_result.lower():
            status = "Approved"
        elif "rejected" in analysis_result.lower():
            status = "Rejected"
        else:
            status = "Draft"

        logger.info(f"Document analysis result: {status}")

        # Split the message by the first newline and ignore the status line (first part)
        message_lines = analysis_result.split("\n\n", 1)
        gpt_message = (
            message_lines[1] if len(message_lines) > 1 else ""
        )  # The message after the first newline

        # Store the GPT response as a text string in JSON format
        gpt_response_text = json.dumps(
            {
                "status": status,
                "message": gpt_message,  # Use the modified message without the status
                "created_time": created_time,
            }
        )

        # Update the document object
        document.status = status
        document.gpt_response = gpt_response_text
        document.gpt_created_time = created_time
        document.save()

        # Return the response
        return {
            "status": status,
            "message": gpt_message,  # The message without the status
            "created_time": created_time,
        }

    except Exception as e:
        logger.exception("An error occurred in _analyze_document_with_gpt.")
        return {
            "status": "Error",
            "message": f"An unexpected error occurred: {str(e)}",
        }
