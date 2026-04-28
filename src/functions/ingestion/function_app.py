"""Azure Functions Python v2 entrypoint.

In `azure` profile the function is bound to an Event Grid trigger; the
EG system topic configured by infra/bicep/modules/eventGridSystemTopic.bicep
targets a function named `IngestionTrigger` and filters subjects beginning with
`/blobServices/default/containers/raw/blobs/contracts/`.

In `local` profile (docker-compose) the function uses the polling blob
trigger instead — Event Grid is not available against Azurite without extra
plumbing, and the polling trigger is well-supported by the Functions runtime.
The function name and the downstream `process_blob_event(...)` signature are
identical in both profiles.
"""
from __future__ import annotations

import logging
import os

import azure.functions as func

from pipeline import process_blob_event

app = func.FunctionApp()

_PROFILE = os.environ.get("RUNTIME_PROFILE", "azure").lower()


if _PROFILE == "local":
    # Polling blob trigger against Azurite. Path token captures the rest of
    # the blob name so we can reconstruct the URL passed downstream.
    @app.function_name(name="IngestionTrigger")
    @app.blob_trigger(
        arg_name="blob",
        path="raw/contracts/{name}",
        connection="AzureWebJobsStorage",
    )
    def ingestion_trigger(blob: func.InputStream) -> None:
        # blob.uri is the full blob URL inside Azurite; pipeline parses it.
        blob_url = blob.uri or ""
        event_id = blob.name or ""
        logging.info("Ingestion start (local): blob=%s", blob_url)
        process_blob_event(blob_url=blob_url, event_id=event_id)
        logging.info("Ingestion done (local): blob=%s", blob_url)

else:
    @app.function_name(name="IngestionTrigger")
    @app.event_grid_trigger(arg_name="event")
    def ingestion_trigger(event: func.EventGridEvent) -> None:
        payload = event.get_json() or {}
        blob_url = payload.get("url")
        if not blob_url:
            logging.warning(
                "EventGrid event %s missing data.url; skipping. subject=%s",
                event.id, event.subject,
            )
            return
        logging.info("Ingestion start: blob=%s eventId=%s", blob_url, event.id)
        process_blob_event(blob_url=blob_url, event_id=event.id)
        logging.info("Ingestion done: blob=%s", blob_url)
