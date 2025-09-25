"""
Request batching system for improved performance.
Groups similar requests together to reduce overhead.
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Callable, Optional, TypeVar, Generic
from dataclasses import dataclass
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

T = TypeVar('T')
R = TypeVar('R')


@dataclass
class BatchConfig:
    """Configuration for request batching."""
    max_batch_size: int = 10
    max_wait_time: float = 0.1  # 100ms
    max_concurrent_batches: int = 5


@dataclass
class BatchRequest(Generic[T, R]):
    """Individual request in a batch."""
    request_id: str
    data: T
    future: asyncio.Future[R]
    timestamp: float


class BatchProcessor(ABC, Generic[T, R]):
    """Abstract base class for batch processors."""

    @abstractmethod
    async def process_batch(self, requests: List[BatchRequest[T, R]]) -> None:
        """Process a batch of requests."""
        pass

    @abstractmethod
    def can_batch_together(self, request1: T, request2: T) -> bool:
        """Check if two requests can be batched together."""
        pass


class RequestBatcher(Generic[T, R]):
    """Generic request batcher implementation."""

    def __init__(self, name: str, processor: BatchProcessor[T, R], config: BatchConfig = None):
        self.name = name
        self.processor = processor
        self.config = config or BatchConfig()

        self.pending_requests: List[BatchRequest[T, R]] = []
        self.active_batches = 0
        self.total_requests = 0
        self.total_batches = 0

        self._lock = asyncio.Lock()
        self._batch_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the request batcher."""
        if self._batch_task is None or self._batch_task.done():
            self._batch_task = asyncio.create_task(self._batch_processing_loop())
            logger.info(f"Started request batcher: {self.name}")

    async def stop(self) -> None:
        """Stop the request batcher."""
        if self._batch_task and not self._batch_task.done():
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass

        # Process any remaining requests
        async with self._lock:
            if self.pending_requests:
                await self._process_current_batch()

        logger.info(f"Stopped request batcher: {self.name}")

    async def submit_request(self, request_id: str, data: T) -> R:
        """Submit a request for batching."""
        future: asyncio.Future[R] = asyncio.Future()

        batch_request = BatchRequest(
            request_id=request_id,
            data=data,
            future=future,
            timestamp=time.time()
        )

        async with self._lock:
            self.pending_requests.append(batch_request)
            self.total_requests += 1

        # Wait for the result
        return await future

    async def _batch_processing_loop(self) -> None:
        """Main batch processing loop."""
        while True:
            try:
                await asyncio.sleep(self.config.max_wait_time)

                async with self._lock:
                    if self._should_process_batch():
                        await self._process_current_batch()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in batch processing loop: {e}")

    def _should_process_batch(self) -> bool:
        """Determine if current batch should be processed."""
        if not self.pending_requests:
            return False

        # Check batch size limit
        if len(self.pending_requests) >= self.config.max_batch_size:
            return True

        # Check time limit
        oldest_request = min(self.pending_requests, key=lambda r: r.timestamp)
        if time.time() - oldest_request.timestamp >= self.config.max_wait_time:
            return True

        # Check concurrent batch limit
        if self.active_batches >= self.config.max_concurrent_batches:
            return False

        return False

    async def _process_current_batch(self) -> None:
        """Process the current batch of requests."""
        if not self.pending_requests:
            return

        # Group requests that can be batched together
        batches = self._group_requests()

        for batch in batches:
            if self.active_batches < self.config.max_concurrent_batches:
                asyncio.create_task(self._process_batch_group(batch))

    def _group_requests(self) -> List[List[BatchRequest[T, R]]]:
        """Group requests into batches based on compatibility."""
        if not self.pending_requests:
            return []

        groups = []
        remaining_requests = self.pending_requests.copy()
        self.pending_requests.clear()

        while remaining_requests:
            current_batch = [remaining_requests.pop(0)]

            # Find compatible requests
            i = 0
            while i < len(remaining_requests) and len(current_batch) < self.config.max_batch_size:
                if self.processor.can_batch_together(current_batch[0].data, remaining_requests[i].data):
                    current_batch.append(remaining_requests.pop(i))
                else:
                    i += 1

            groups.append(current_batch)

        return groups

    async def _process_batch_group(self, batch: List[BatchRequest[T, R]]) -> None:
        """Process a group of batched requests."""
        self.active_batches += 1
        self.total_batches += 1

        try:
            logger.debug(f"Processing batch of {len(batch)} requests")
            await self.processor.process_batch(batch)

        except Exception as e:
            logger.error(f"Error processing batch: {e}")

            # Mark all requests as failed
            for request in batch:
                if not request.future.done():
                    request.future.set_exception(e)

        finally:
            self.active_batches -= 1

    def get_stats(self) -> Dict[str, Any]:
        """Get batching statistics."""
        avg_batch_size = self.total_requests / self.total_batches if self.total_batches > 0 else 0

        return {
            "name": self.name,
            "pending_requests": len(self.pending_requests),
            "active_batches": self.active_batches,
            "total_requests": self.total_requests,
            "total_batches": self.total_batches,
            "avg_batch_size": avg_batch_size,
            "config": {
                "max_batch_size": self.config.max_batch_size,
                "max_wait_time": self.config.max_wait_time,
                "max_concurrent_batches": self.config.max_concurrent_batches
            }
        }


class AIRequestBatchProcessor(BatchProcessor[Dict[str, Any], Dict[str, Any]]):
    """Batch processor for AI requests."""

    def __init__(self, ai_provider_func: Callable):
        self.ai_provider_func = ai_provider_func

    async def process_batch(self, requests: List[BatchRequest[Dict[str, Any], Dict[str, Any]]]) -> None:
        """Process a batch of AI requests."""
        try:
            # Combine messages for batch processing
            combined_messages = []
            request_boundaries = []

            for request in requests:
                start_idx = len(combined_messages)
                messages = request.data.get("messages", [])
                combined_messages.extend(messages)
                request_boundaries.append((start_idx, len(combined_messages), request))

            # Process the combined batch
            if combined_messages:
                batch_result = await self.ai_provider_func(combined_messages)

                # Distribute results back to individual requests
                for start_idx, end_idx, request in request_boundaries:
                    # Extract relevant portion of result for this request
                    request_result = {
                        "messages": batch_result.get("messages", [])[start_idx:end_idx],
                        "metadata": batch_result.get("metadata", {})
                    }

                    if not request.future.done():
                        request.future.set_result(request_result)

        except Exception as e:
            # Mark all requests as failed
            for request in requests:
                if not request.future.done():
                    request.future.set_exception(e)

    def can_batch_together(self, request1: Dict[str, Any], request2: Dict[str, Any]) -> bool:
        """Check if two AI requests can be batched together."""
        # Simple heuristic: batch requests with similar model and parameters
        model1 = request1.get("model", "")
        model2 = request2.get("model", "")

        temperature1 = request1.get("temperature", 0.7)
        temperature2 = request2.get("temperature", 0.7)

        # Batch if same model and similar temperature
        return model1 == model2 and abs(temperature1 - temperature2) < 0.1


class FileOperationBatchProcessor(BatchProcessor[Dict[str, Any], Dict[str, Any]]):
    """Batch processor for file operations."""

    async def process_batch(self, requests: List[BatchRequest[Dict[str, Any], Dict[str, Any]]]) -> None:
        """Process a batch of file operations."""
        # Group by operation type
        operations = {}
        for request in requests:
            op_type = request.data.get("operation", "unknown")
            if op_type not in operations:
                operations[op_type] = []
            operations[op_type].append(request)

        # Process each operation type
        for op_type, op_requests in operations.items():
            try:
                if op_type == "read_multiple":
                    await self._process_read_batch(op_requests)
                elif op_type == "write_multiple":
                    await self._process_write_batch(op_requests)
                else:
                    # Process individually for unknown operations
                    for request in op_requests:
                        result = {"status": "processed", "operation": op_type}
                        if not request.future.done():
                            request.future.set_result(result)

            except Exception as e:
                for request in op_requests:
                    if not request.future.done():
                        request.future.set_exception(e)

    async def _process_read_batch(self, requests: List[BatchRequest[Dict[str, Any], Dict[str, Any]]]) -> None:
        """Process a batch of read operations."""
        # Read multiple files efficiently
        for request in requests:
            file_path = request.data.get("path", "")
            # Simulate file reading
            result = {
                "status": "success",
                "path": file_path,
                "content": f"Content of {file_path}",
                "size": len(file_path) * 10
            }
            if not request.future.done():
                request.future.set_result(result)

    async def _process_write_batch(self, requests: List[BatchRequest[Dict[str, Any], Dict[str, Any]]]) -> None:
        """Process a batch of write operations."""
        # Write multiple files efficiently
        for request in requests:
            file_path = request.data.get("path", "")
            content = request.data.get("content", "")
            # Simulate file writing
            result = {
                "status": "success",
                "path": file_path,
                "bytes_written": len(content)
            }
            if not request.future.done():
                request.future.set_result(result)

    def can_batch_together(self, request1: Dict[str, Any], request2: Dict[str, Any]) -> bool:
        """Check if two file operations can be batched together."""
        op1 = request1.get("operation", "")
        op2 = request2.get("operation", "")

        # Batch operations of the same type
        return op1 == op2


class BatcherManager:
    """Manages multiple request batchers."""

    def __init__(self):
        self.batchers: Dict[str, RequestBatcher] = {}
        self.logger = logging.getLogger(__name__)

    def create_ai_batcher(self, name: str, ai_provider_func: Callable, config: BatchConfig = None) -> RequestBatcher:
        """Create an AI request batcher."""
        processor = AIRequestBatchProcessor(ai_provider_func)
        batcher = RequestBatcher(name, processor, config)
        self.batchers[name] = batcher

        self.logger.info(f"Created AI request batcher: {name}")
        return batcher

    def create_file_batcher(self, name: str, config: BatchConfig = None) -> RequestBatcher:
        """Create a file operation batcher."""
        processor = FileOperationBatchProcessor()
        batcher = RequestBatcher(name, processor, config)
        self.batchers[name] = batcher

        self.logger.info(f"Created file operation batcher: {name}")
        return batcher

    def get_batcher(self, name: str) -> Optional[RequestBatcher]:
        """Get a batcher by name."""
        return self.batchers.get(name)

    async def start_all(self) -> None:
        """Start all batchers."""
        for batcher in self.batchers.values():
            await batcher.start()

    async def stop_all(self) -> None:
        """Stop all batchers."""
        for batcher in self.batchers.values():
            await batcher.stop()

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all batchers."""
        return {
            name: batcher.get_stats()
            for name, batcher in self.batchers.items()
        }


# Global batcher manager
_batcher_manager = BatcherManager()


def get_batcher_manager() -> BatcherManager:
    """Get the global batcher manager."""
    return _batcher_manager