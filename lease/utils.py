from __future__ import absolute_import, unicode_literals
import io
import logging
from datetime import datetime, timezone
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
    Returns None when the chunk could not be analysed, so failures never leak into the summary.
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
        except openai.error.RateLimitError as error:
            logger.error("RateLimitError: %s", error)
            if attempt < retry_attempts - 1:
                logger.info("Retrying after 30 seconds.")
                time.sleep(30)
            else:
                logger.critical("Rate limit exceeded after multiple attempts.")
        except openai.error.OpenAIError:
            logger.exception("OpenAI request failed in analyze_chunk.")
            return None
    return None


STATUS_PATTERN = re.compile(r"\b(approved|rejected|draft)\b", re.IGNORECASE)
LABELLED_STATUS_PATTERN = re.compile(r"status\W{0,5}(approved|rejected|draft)\b", re.IGNORECASE)


def parse_lease_status(analysis):
    """Prefer an explicit "Status: X" label, then the first status word, then Draft."""
    match = LABELLED_STATUS_PATTERN.search(analysis) or STATUS_PATTERN.search(analysis)
    return match.group(1).capitalize() if match else "Draft"


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
        response = requests.get(document.file_url, timeout=60)
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
                reader.pages[j].extract_text() or ""
                for j in range(i, min(i + chunk_size, num_pages))
            )
            for i in range(0, num_pages, chunk_size)
        ]
        logger.info(f"Document split into {len(chunks)} chunks.")

        chunks = [chunk for chunk in chunks if chunk.strip()]
        if not chunks:
            logger.error("No text found in the document.")
            raise ValueError("No text found in the document.")

        # Initialize OpenAI API
        openai.api_key = settings.OPENAI_API_KEY
        encoding = tiktoken.get_encoding("cl100k_base")

        # Define the system message for the document analysis, including lease details
        system_message = """
            This GPT acts as a short-term rental contract expert designed to help users, especially students,
            review rental leases.
            The primary goal is to assist users in identifying unusual clauses, potential legal risks, and
            ensuring transparency within the lease documents.
            It will always identify key financial details such as rent amounts and security deposits from
            uploaded leases.
            Additionally, the GPT will carefully review the lease for unfavorable terms to the tenant, such as
            disproportionate fees, restrictions, or unclear responsibilities,
            and will make suggestions for favorable terms and strategies for negotiation.
            For example, it will suggest negotiating points such as reduced late fees, prorated rent for
            partial occupancy months, or limits on certain restrictions like subletting.
            It will also ensure that checkbox provisions are correctly applied, particularly regarding
            assignment, subleasing, and permissions.
            The length of the lease, any related fees, and responsibilities of both the landlord and tenant
            are key areas of focus.

            Please analyze the lease document and provide a clear assessment.
            Specifically, include a status for the lease:
            - "Approved" if the lease is favorable and there are no significant concerns.
            - "Rejected" if there are major unfavorable clauses or legal risks.
            - "Draft" if the lease is in an incomplete or negotiable state, and suggest any improvements or
              issues that need addressing.

            Please ensure the status is clearly mentioned in the response along with a summary of your findings.
            """

        chunk_summaries = [
            summary for summary in (analyze_chunk(chunk, system_message) for chunk in chunks) if summary
        ]
        if not chunk_summaries:
            raise ValueError("None of the document chunks could be analysed.")

        combined_summary = " ".join(chunk_summaries)
        combined_tokens = len(encoding.encode(combined_summary))

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

        status = parse_lease_status(analysis_result)

        logger.info(f"Document analysis result: {status}")

        # Split the message by the first newline and ignore the status line (first part)
        message_lines = analysis_result.split("\n\n", 1)
        gpt_message = (
            message_lines[1] if len(message_lines) > 1 else ""
        )  # The message after the first newline

        return {
            "status": status,
            "message": gpt_message,  # The message without the status
            "created_time": created_time,
        }

    except (ValueError, requests.RequestException, PyPDF2.errors.PdfReadError, openai.error.OpenAIError) as error:
        logger.exception("Document analysis failed for document ID %s.", document.id)
        return {
            "status": "Error",
            "message": f"Document analysis failed: {error}",
        }
