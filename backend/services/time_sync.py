"""Time synchronization service to correct system clock drift."""

from __future__ import annotations

import datetime
import logging
import requests
import threading
from typing import Optional

logger = logging.getLogger(__name__)

class TimeSyncService:
    """
    Synchronizes time with an external server to prevent issues with
    clock drift (especially common in Docker/WSL2 environments).
    """
    _instance: Optional[TimeSyncService] = None
    _offset_seconds: float = 0.0
    _last_sync: Optional[datetime.datetime] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sync()
        return cls._instance

    def _sync(self):
        """Synchronize with worldtimeapi to find the clock offset."""
        try:
            # We use UTC endpoint to keep calculations simple
            response = requests.get("https://worldtimeapi.org/api/timezone/Etc/UTC", timeout=3)
            if response.status_code == 200:
                data = response.json()
                true_time = datetime.datetime.fromisoformat(data["datetime"].replace('Z', '+00:00'))
                local_time = datetime.datetime.now(datetime.timezone.utc)
                
                with self._lock:
                    self._offset_seconds = (true_time - local_time).total_seconds()
                    self._last_sync = local_time
                    
                logger.info(f"Time synced successfully. System clock offset: {self._offset_seconds:.2f} seconds.")
        except Exception as e:
            logger.warning(f"Failed to sync time with WorldTimeAPI: {e}. Using system time.")
            
    def get_true_now(self, tzinfo=None) -> datetime.datetime:
        """
        Get the true current time, adjusted for any system clock drift.
        
        Args:
            tzinfo: Optional timezone object (e.g. pytz.timezone('Asia/Kolkata')).
                    If None, returns UTC.
        """
        # Resync if it's been more than 4 hours
        with self._lock:
            needs_sync = self._last_sync is None or \
                (datetime.datetime.now(datetime.timezone.utc) - self._last_sync).total_seconds() > 14400
            
        if needs_sync:
            # Sync in a background thread to avoid blocking
            threading.Thread(target=self._sync, daemon=True).start()
            
        true_utc_now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=self._offset_seconds)
        
        if tzinfo:
            return true_utc_now.astimezone(tzinfo)
        return true_utc_now

time_sync = TimeSyncService()
