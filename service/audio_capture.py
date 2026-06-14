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
    def __init__(self, chunk_duration: float = 4.0, sample_rate: int = 16000):
        self._chunk_duration = chunk_duration
        self._sample_rate = sample_rate

    async def stream(self) -> AsyncIterator[bytes]:
        """Yields mono 16-bit PCM chunks. Chunk size follows _chunk_duration dynamically."""
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        def _run():
            pa = pyaudio.PyAudio()
            try:
                device = _find_loopback_device(pa)
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
                            asyncio.run_coroutine_threadsafe(queue.put(buffer[:target]), loop)
                            buffer = buffer[target:]
                finally:
                    stream.stop_stream()
                    stream.close()
            finally:
                pa.terminate()

        loop.run_in_executor(None, _run)
        while True:
            yield await queue.get()


def _find_loopback_device(pa: pyaudio.PyAudio) -> dict:
    default_speakers = pa.get_default_wasapi_loopback()
    if default_speakers:
        return default_speakers
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info.get("isLoopbackDevice"):
            return info
    raise RuntimeError(
        "No WASAPI loopback device found. "
        "Make sure audio is playing and pyaudiowpatch is installed."
    )


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
