"""
Asynchronous Dual-Database Sync Service.
Synchronizes real-time state from Firestore into BigQuery Analytics Warehouse in the background.
"""

import threading
import queue
import time
from typing import Dict, Any, List, Optional
from .firestore_client import get_firestore_client, FirestoreWardrobeClient
from .bigquery_client import get_bigquery_client, BigQueryWardrobeClient


class SyncService:
    """
    Background sync worker that streams Firestore mutation events into BigQuery tables.
    """
    def __init__(
        self,
        firestore_client: Optional[FirestoreWardrobeClient] = None,
        bigquery_client: Optional[BigQueryWardrobeClient] = None,
        run_worker_thread: bool = True
    ):
        self.firestore = firestore_client or get_firestore_client()
        self.bigquery = bigquery_client or get_bigquery_client()
        self._queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread = None

        if run_worker_thread:
            self._start_worker()

    def _start_worker(self):
        self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._worker_thread.start()

    def _process_queue(self):
        while not self._stop_event.is_set():
            try:
                event = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self._dispatch_event(event)
            except Exception as e:
                print(f"[SyncService] Error syncing event {event.get('type')}: {e}")
            finally:
                self._queue.task_done()

    def _dispatch_event(self, event: Dict[str, Any]):
        event_type = event.get("type")
        payload = event.get("payload", {})

        if event_type == "SYNC_ITEM":
            self.bigquery.insert_items([payload])
        elif event_type == "DELETE_ITEM":
            self.bigquery.delete_item(payload.get("item_id"))
        elif event_type == "SYNC_OUTFIT":
            outfit_data = payload.get("outfit", {})
            items = payload.get("items", [])
            
            self.bigquery.insert_outfits([outfit_data])
            if items:
                junction_rows = [
                    {"outfit_id": outfit_data["outfit_id"], "item_id": item_id}
                    for item_id in items
                ]
                self.bigquery.insert_outfit_items(junction_rows)
        elif event_type == "SYNC_WEAR_EVENT":
            # Wear event associated with an outfit or single item
            outfit_id = payload.get("outfit_id") or f"wear_{payload.get('item_id')}_{int(time.time())}"
            outfit_row = {
                "outfit_id": outfit_id,
                "user_id": payload["user_id"],
                "worn_date": payload.get("worn_date", time.strftime("%Y-%m-%d")),
                "occasion": payload.get("occasion", "Casual / Daily"),
                "weather_summary": payload.get("weather_summary", ""),
                "outfit_gs_uri": payload.get("outfit_gs_uri", "")
            }
            self.bigquery.insert_outfits([outfit_row])
            self.bigquery.insert_outfit_items([{"outfit_id": outfit_id, "item_id": payload["item_id"]}])

    def queue_item_sync(self, item_data: Dict[str, Any]):
        """Queues an item record for BigQuery synchronization."""
        self._queue.put({"type": "SYNC_ITEM", "payload": item_data})

    def queue_outfit_sync(self, outfit_data: Dict[str, Any], item_ids: List[str]):
        """Queues an outfit and its junction items for BigQuery synchronization."""
        self._queue.put({
            "type": "SYNC_OUTFIT",
            "payload": {"outfit": outfit_data, "items": item_ids}
        })

    def queue_wear_event_sync(self, user_id: str, item_id: str, worn_date: Optional[str] = None, outfit_id: Optional[str] = None):
        """Queues a single item wear event for BigQuery synchronization."""
        self._queue.put({
            "type": "SYNC_WEAR_EVENT",
            "payload": {
                "user_id": user_id,
                "item_id": item_id,
                "worn_date": worn_date or time.strftime("%Y-%m-%d"),
                "outfit_id": outfit_id
            }
        })

    def queue_delete_item(self, item_id: str):
        """Queues an item deletion for BigQuery synchronization."""
        self._queue.put({
            "type": "DELETE_ITEM",
            "payload": {"item_id": item_id}
        })

    def flush(self):
        """Blocks until all queued sync events have been processed."""
        self._queue.join()

    def shutdown(self):
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)


# Global singleton instance
_SYNC_SERVICE_INSTANCE: Optional[SyncService] = None

def get_sync_service() -> SyncService:
    global _SYNC_SERVICE_INSTANCE
    if _SYNC_SERVICE_INSTANCE is None:
        _SYNC_SERVICE_INSTANCE = SyncService()
    return _SYNC_SERVICE_INSTANCE
