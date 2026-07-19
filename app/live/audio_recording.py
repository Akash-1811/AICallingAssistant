"""
Write live-call audio to disk as a .wav so the UI can replay calls.

The browser sends interleaved stereo int16 PCM @ 16 kHz:
  [mic0, tab0, mic1, tab1, ...] (little-endian)

We persist it as PCM WAV. The writer runs in a background task and batches
writes so the event loop is not blocked by frequent small file writes.
"""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _wav_header(*, channels: int, sample_rate: int, bits_per_sample: int, data_size: int) -> bytes:
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    riff_size = 36 + data_size
    return b"".join(
        [
            b"RIFF",
            struct.pack("<I", riff_size),
            b"WAVE",
            b"fmt ",
            struct.pack("<I", 16),  # PCM fmt chunk size
            struct.pack("<H", 1),  # format = PCM
            struct.pack("<H", channels),
            struct.pack("<I", sample_rate),
            struct.pack("<I", byte_rate),
            struct.pack("<H", block_align),
            struct.pack("<H", bits_per_sample),
            b"data",
            struct.pack("<I", data_size),
        ]
    )


@dataclass(frozen=True)
class RecordingSpec:
    channels: int = 2
    sample_rate: int = 16_000
    bits_per_sample: int = 16


class WavRecordingWriter:
    """
    Append PCM chunks to a WAV file and patch the header on close.

    Usage:
        rec = WavRecordingWriter(conversation_id)
        await rec.start()
        rec.enqueue(pcm_bytes)
        await rec.close()
    """

    _CLOSE = object()

    def __init__(
        self,
        conversation_id: str,
        *,
        out_dir: Path | None = None,
        spec: RecordingSpec = RecordingSpec(),
        queue_max_chunks: int = 2048,
    ):
        self.conversation_id = conversation_id
        self.spec = spec
        self.out_dir = out_dir or Path(settings.CALL_RECORDINGS_DIR)
        self.path = self.out_dir / f"{conversation_id}.wav"
        self._pending: asyncio.Queue[bytes | object] = asyncio.Queue(maxsize=queue_max_chunks)
        self._task: asyncio.Task | None = None
        self._data_size = 0

    async def start(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        # Write placeholder header (data_size=0). We'll patch sizes on close.
        header = _wav_header(
            channels=self.spec.channels,
            sample_rate=self.spec.sample_rate,
            bits_per_sample=self.spec.bits_per_sample,
            data_size=0,
        )
        await asyncio.to_thread(self._write_header, header)
        self._task = asyncio.create_task(self._drain(), name=f"wav-rec-{self.conversation_id[:8]}")

    def enqueue(self, chunk: bytes) -> None:
        if not chunk:
            return
        if self._task is None:
            return
        try:
            self._pending.put_nowait(chunk)
        except asyncio.QueueFull:
            # If the disk can't keep up, prefer live UX over perfect recordings.
            logger.warning("audio recorder queue full, dropping chunk conversation=%s", self.conversation_id)

    async def close(self) -> None:
        if self._task is None:
            return
        try:
            self._pending.put_nowait(self._CLOSE)
        except asyncio.QueueFull:
            # Drain will exit eventually; add close sentinel when room is available.
            await self._pending.put(self._CLOSE)
        await self._task
        self._task = None
        header = _wav_header(
            channels=self.spec.channels,
            sample_rate=self.spec.sample_rate,
            bits_per_sample=self.spec.bits_per_sample,
            data_size=self._data_size,
        )
        await asyncio.to_thread(self._patch_header, header)

    @property
    def data_size_bytes(self) -> int:
        return int(self._data_size)

    def _write_header(self, header: bytes) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("wb") as f:
            f.write(header)

    def _append_bytes(self, buf: bytes) -> None:
        with self.path.open("ab") as f:
            f.write(buf)

    def _patch_header(self, header: bytes) -> None:
        with self.path.open("r+b") as f:
            f.seek(0)
            f.write(header)

    async def _drain(self) -> None:
        buffer = bytearray()
        # Tune batching: keep file writes chunky without adding large latency.
        flush_bytes = 256 * 1024
        while True:
            item = await self._pending.get()
            if item is self._CLOSE:
                break
            assert isinstance(item, (bytes, bytearray))
            buffer.extend(item)
            if len(buffer) >= flush_bytes:
                buf = bytes(buffer)
                buffer.clear()
                await asyncio.to_thread(self._append_bytes, buf)
                self._data_size += len(buf)
        if buffer:
            buf = bytes(buffer)
            buffer.clear()
            await asyncio.to_thread(self._append_bytes, buf)
            self._data_size += len(buf)

