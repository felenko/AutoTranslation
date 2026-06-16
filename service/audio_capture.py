"""
Windows WASAPI loopback audio capture.
Captures what the system is currently playing (not the microphone).
Requires: pyaudiowpatch
"""
import asyncio
import struct
from typing import AsyncIterator

import pyaudiowpatch as pyaudio

_READ_SECONDS = 0.1  # internal read size — chunk_duration is accumulated from these


class AudioCapture:
    def __init__(self, chunk_duration: float = 4.0, sample_rate: int = 16000, capture_device: str = ""):
        self._chunk_duration = chunk_duration
        self._sample_rate = sample_rate
        self._capture_device = capture_device

    async def stream(self) -> AsyncIterator[bytes]:
        """Yields mono 16-bit PCM chunks. Chunk size follows _chunk_duration dynamically."""
        loop = asyncio.get_event_loop()
        # Unbounded — every chunk is kept. Pipeline processes in order and catches up
        # during speaker pauses; lag is acceptable, missing audio is not.
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        def _run():
            pa = pyaudio.PyAudio()
            try:
                device = _find_loopback_device(pa, self._capture_device)
                native_rate = int(device["defaultSampleRate"])
                channels = min(int(device["maxInputChannels"]), 2)
                read_frames = int(native_rate * _READ_SECONDS)

                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=channels,
                    rate=native_rate,
                    input=True,
                    input_device_index=device["index"],
                    frames_per_buffer=read_frames,
                )
                print(
                    f"[AudioCapture] capturing from '{device['name']}' "
                    f"at {native_rate}Hz, {channels}ch"
                )
                buffer = b""
                try:
                    while True:
                        raw = stream.read(read_frames, exception_on_overflow=False)
                        pcm = _to_mono_16k(raw, channels, native_rate, self._sample_rate)
                        buffer += pcm
                        target = int(self._sample_rate * self._chunk_duration) * 2  # bytes
                        if len(buffer) >= target:
                            chunk = buffer[:target]
                            buffer = buffer[target:]
                            asyncio.run_coroutine_threadsafe(queue.put(chunk), loop)
                finally:
                    stream.stop_stream()
                    stream.close()
            finally:
                pa.terminate()

        loop.run_in_executor(None, _run)
        while True:
            yield await queue.get()


def list_loopback_devices() -> None:
    """Print all available WASAPI loopback devices. Run to discover the right capture_device name."""
    pa = pyaudio.PyAudio()
    try:
        found = False
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info.get("isLoopbackDevice"):
                print(f"  [{i}] {info['name']}")
                found = True
        if not found:
            print("  (none found — install pyaudiowpatch and ensure audio devices are active)")
    finally:
        pa.terminate()


def list_loopback_device_names() -> list[str]:
    pa = pyaudio.PyAudio()
    try:
        return [
            pa.get_device_info_by_index(i)["name"]
            for i in range(pa.get_device_count())
            if pa.get_device_info_by_index(i).get("isLoopbackDevice")
        ]
    finally:
        pa.terminate()


def list_output_device_names() -> list[str]:
    pa = pyaudio.PyAudio()
    try:
        seen: set[str] = set()
        names: list[str] = []
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if (info.get("maxOutputChannels", 0) > 0
                    and not info.get("isLoopbackDevice")
                    and info["name"] not in seen):
                seen.add(info["name"])
                names.append(info["name"])
        return names
    finally:
        pa.terminate()


def _find_loopback_device(pa: pyaudio.PyAudio, name_filter: str = "") -> dict:
    loopbacks = []
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info.get("isLoopbackDevice"):
            loopbacks.append(info)

    if not loopbacks:
        raise RuntimeError(
            "No WASAPI loopback device found. "
            "Make sure audio is playing and pyaudiowpatch is installed."
        )

    if name_filter:
        needle = name_filter.lower()
        matches = [d for d in loopbacks if needle in d["name"].lower()]
        if matches:
            return matches[0]
        names = [d["name"] for d in loopbacks]
        raise RuntimeError(
            f"No loopback device matching '{name_filter}'. Available: {names}"
        )

    # Default: prefer the system default output's loopback
    default = pa.get_default_wasapi_loopback()
    return default if default else loopbacks[0]


def _to_mono_16k(raw: bytes, channels: int, src_rate: int, dst_rate: int) -> bytes:
    """Downmix to mono and resample to dst_rate using simple linear interpolation."""
    samples = struct.unpack(f"<{len(raw)//2}h", raw)

    if channels > 1:
        mono = [
            sum(samples[i : i + channels]) // channels
            for i in range(0, len(samples), channels)
        ]
    else:
        mono = list(samples)

    if src_rate != dst_rate:
        ratio = src_rate / dst_rate
        out_len = int(len(mono) / ratio)
        resampled = []
        for i in range(out_len):
            src_pos = i * ratio
            src_idx = int(src_pos)
            frac = src_pos - src_idx
            s0 = mono[src_idx] if src_idx < len(mono) else 0
            s1 = mono[src_idx + 1] if src_idx + 1 < len(mono) else s0
            resampled.append(int(s0 + frac * (s1 - s0)))
        mono = resampled

    return struct.pack(f"<{len(mono)}h", *mono)
