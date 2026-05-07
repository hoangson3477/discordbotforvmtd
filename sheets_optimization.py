"""
Advanced Google Sheets optimization with caching and batch operations
"""
import asyncio
import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from functools import lru_cache
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import gspread
from gspread.utils import a1_to_rowcol, rowcol_to_a1

logger = logging.getLogger("my_bot")

@dataclass
class SheetUpdate:
    """Represents a single sheet update operation"""
    worksheet_name: str
    cell: str
    value: Any
    batch_id: Optional[str] = None

@dataclass 
class SheetRow:
    """Represents a row with metadata for efficient operations"""
    data: List[str]
    username: str
    row_index: int
    last_modified: float

class SheetsCache:
    """Advanced multi-level caching system for Google Sheets"""
    
    def __init__(self, ttl: int = 300, max_size: int = 100):
        self.ttl = ttl
        self.max_size = max_size
        self.memory_cache: Dict[str, Dict] = {}
        self.username_index: Dict[str, Dict[str, int]] = {}
        self.column_cache: Dict[str, Dict[str, int]] = {}
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sheets")
        
    def get(self, key: str) -> Optional[List[List[str]]]:
        """Get cached sheet data with TTL check"""
        if key in self.memory_cache:
            cache_entry = self.memory_cache[key]
            if time.time() - cache_entry["timestamp"] < self.ttl:
                return cache_entry["data"]
            else:
                self.invalidate(key)
        return None
    
    def set(self, key: str, data: List[List[str]], username_col: str = "USERNAME"):
        """Set cached data with indexing"""
        if len(self.memory_cache) >= self.max_size:
            self._evict_oldest()
        
        # Build username index for fast lookups
        username_idx = {}
        if username_col in (data[0] if data else []):
            col_idx = data[0].index(username_col)
            for row_idx, row in enumerate(data[1:], 1):
                if len(row) > col_idx and row[col_idx]:
                    username_idx[row[col_idx].strip().lower()] = row_idx
        
        self.memory_cache[key] = {
            "data": data,
            "timestamp": time.time(),
            "username_index": username_idx
        }
        
        # Store username index separately for fast access
        self.username_index[key] = username_idx
    
    def invalidate(self, key: str):
        """Remove specific cache entry"""
        self.memory_cache.pop(key, None)
        self.username_index.pop(key, None)
        self.column_cache.pop(key, None)
    
    def _evict_oldest(self):
        """Remove oldest cache entry"""
        if not self.memory_cache:
            return
        
        oldest_key = min(self.memory_cache.keys(), 
                       key=lambda k: self.memory_cache[k]["timestamp"])
        self.invalidate(oldest_key)
    
    def find_user_row(self, sheet_name: str, username: str) -> Optional[int]:
        """Fast user row lookup using cached index"""
        sheet_index = self.username_index.get(sheet_name, {})
        return sheet_index.get(username.strip().lower())
    
    def clear_all(self):
        """Clear all caches"""
        self.memory_cache.clear()
        self.username_index.clear()
        self.column_cache.clear()

class BatchUpdateManager:
    """Manages batch updates to minimize API calls"""
    
    def __init__(self, spreadsheet, batch_size: int = 100):
        self.spreadsheet = spreadsheet
        self.batch_size = batch_size
        self.pending_updates: List[SheetUpdate] = []
        self.batch_counter = 0
        
    def add_update(self, worksheet_name: str, cell: str, value: Any, batch_id: str = None):
        """Add update to batch queue"""
        update = SheetUpdate(
            worksheet_name=worksheet_name,
            cell=cell,
            value=value,
            batch_id=batch_id or f"batch_{self.batch_counter}"
        )
        self.pending_updates.append(update)
        
        # Auto-flush when batch is full
        if len(self.pending_updates) >= self.batch_size:
            asyncio.create_task(self.flush())
    
    async def flush(self) -> bool:
        """Execute all pending updates"""
        if not self.pending_updates:
            return True
        
        try:
            # Group updates by worksheet
            worksheet_updates = {}
            for update in self.pending_updates:
                if update.worksheet_name not in worksheet_updates:
                    worksheet_updates[update.worksheet_name] = []
                worksheet_updates[update.worksheet_name].append(update)
            
            # Execute updates in parallel
            tasks = []
            for worksheet_name, updates in worksheet_updates.items():
                task = self._flush_worksheet(worksheet_name, updates)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check for errors
            errors = [r for r in results if isinstance(r, Exception)]
            if errors:
                logger.error(f"[BatchUpdate] {len(errors)} errors occurred")
                for error in errors:
                    logger.error(f"[BatchUpdate] Error: {error}")
            
            self.pending_updates.clear()
            self.batch_counter += 1
            return len(errors) == 0
            
        except Exception as e:
            logger.error(f"[BatchUpdate] Flush failed: {e}")
            return False
    
    async def _flush_worksheet(self, worksheet_name: str, updates: List[SheetUpdate]) -> bool:
        """Flush updates for a specific worksheet"""
        try:
            # Run in thread pool to avoid blocking
            result = await asyncio.to_thread(self._execute_worksheet_updates, 
                                         worksheet_name, updates)
            return result
        except Exception as e:
            logger.error(f"[BatchUpdate] Worksheet {worksheet_name} failed: {e}")
            return False
    
    def _execute_worksheet_updates(self, worksheet_name: str, updates: List[SheetUpdate]) -> bool:
        """Execute worksheet updates (sync)"""
        try:
            worksheet = self.spreadsheet.worksheet(worksheet_name)
            
            # Prepare batch update data
            update_data = []
            for update in updates:
                row, col = a1_to_rowcol(update.cell)
                update_data.append({
                    'range': update.cell,
                    'values': [[update.value]]
                })
            
            # Execute batch update
            worksheet.batch_update(update_data)
            logger.info(f"[BatchUpdate] Updated {len(updates)} cells in {worksheet_name}")
            return True
            
        except Exception as e:
            logger.error(f"[BatchUpdate] Execute failed for {worksheet_name}: {e}")
            return False

class OptimizedSheetsClient:
    """High-performance Google Sheets client with caching and batching"""
    
    def __init__(self, spreadsheet, cache_ttl: int = 300, batch_size: int = 100):
        self.spreadsheet = spreadsheet
        self.cache = SheetsCache(ttl=cache_ttl)
        self.batch_manager = BatchUpdateManager(spreadsheet, batch_size)
        self.column_maps: Dict[str, Dict[str, int]] = {}
        
    async def get_sheet_data(self, worksheet_name: str, force_refresh: bool = False) -> List[List[str]]:
        """Get worksheet data with caching"""
        if not force_refresh:
            cached_data = self.cache.get(worksheet_name)
            if cached_data is not None:
                return cached_data
        
        # Fetch fresh data
        try:
            data = await asyncio.to_thread(self._fetch_sheet_data, worksheet_name)
            if data:
                # Build column map for fast column access
                if data and data[0]:
                    self.column_maps[worksheet_name] = {
                        col.strip().upper(): idx for idx, col in enumerate(data[0])
                    }
                
                self.cache.set(worksheet_name, data)
                return data
        except Exception as e:
            logger.error(f"[SheetsClient] Failed to fetch {worksheet_name}: {e}")
        
        return []
    
    def _fetch_sheet_data(self, worksheet_name: str) -> List[List[str]]:
        """Fetch sheet data (sync)"""
        try:
            worksheet = self.spreadsheet.worksheet(worksheet_name)
            return worksheet.get_all_values()
        except Exception as e:
            logger.error(f"[SheetsClient] Sync fetch failed {worksheet_name}: {e}")
            return []
    
    def find_user_row_fast(self, worksheet_name: str, username: str) -> Optional[int]:
        """Find user row using cached index"""
        return self.cache.find_user_row(worksheet_name, username)
    
    def get_column_index(self, worksheet_name: str, column_name: str) -> Optional[int]:
        """Get column index from cached map"""
        worksheet_map = self.column_maps.get(worksheet_name, {})
        return worksheet_map.get(column_name.strip().upper())
    
    async def update_cell(self, worksheet_name: str, cell: str, value: Any, 
                        batch: bool = True) -> bool:
        """Update single cell with optional batching"""
        if batch:
            self.batch_manager.add_update(worksheet_name, cell, value)
            return True
        else:
            # Immediate update
            try:
                worksheet = self.spreadsheet.worksheet(worksheet_name)
                await asyncio.to_thread(worksheet.update, cell, value)
                return True
            except Exception as e:
                logger.error(f"[SheetsClient] Immediate update failed: {e}")
                return False
    
    async def update_user_field(self, worksheet_name: str, username: str, 
                             field_name: str, value: Any, batch: bool = True) -> bool:
        """Update user field by username and field name"""
        # Find user row
        user_row = self.find_user_row_fast(worksheet_name, username)
        if user_row is None:
            logger.warning(f"[SheetsClient] User {username} not found in {worksheet_name}")
            return False
        
        # Find column
        col_idx = self.get_column_index(worksheet_name, field_name)
        if col_idx is None:
            logger.warning(f"[SheetsClient] Column {field_name} not found in {worksheet_name}")
            return False
        
        # Convert to A1 notation
        cell = rowcol_to_a1(user_row + 1, col_idx + 1)  # +1 for 1-based indexing
        
        return await self.update_cell(worksheet_name, cell, value, batch)
    
    async def flush_updates(self) -> bool:
        """Flush all pending batch updates"""
        return await self.batch_manager.flush()
    
    async def get_user_data(self, worksheet_name: str, username: str) -> Optional[Dict[str, str]]:
        """Get all data for a specific user"""
        user_row = self.find_user_row_fast(worksheet_name, username)
        if user_row is None:
            return None
        
        sheet_data = await self.get_sheet_data(worksheet_name)
        if not sheet_data or user_row >= len(sheet_data):
            return None
        
        # Map column names to values
        row_data = sheet_data[user_row]
        column_map = self.column_maps.get(worksheet_name, {})
        
        user_data = {}
        for col_name, col_idx in column_map.items():
            if col_idx < len(row_data):
                user_data[col_name] = row_data[col_idx]
        
        return user_data
    
    def invalidate_cache(self, worksheet_name: str = None):
        """Invalidate cache for specific worksheet or all"""
        if worksheet_name:
            self.cache.invalidate(worksheet_name)
        else:
            self.cache.clear_all()
    
    async def close(self):
        """Cleanup resources"""
        await self.flush_updates()
        self.cache.executor.shutdown(wait=True)
