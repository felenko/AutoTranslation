"""
Windows WASAPI loopback audio capture.
Captures what the system is currently playing (not the microphone).
Requires: pyaudiowpatch
"""
import asyncio
import struct
import time
from typing import AsyncIterator

import pyaudiowpatch as pyaudio

_READ_SECONDS = 0.1  # internal read size — chunk_duration is accumulated from these


class AudioCapture:
    def __init__(
        self,
        chunk_duration: float = 4.0,
        sample_rate: int = 16000,
        capture_device: str = "",
        playback_device: str = "",
        original_volume: float = 1.0,
        overlap_seconds: float = 0.8,
    ):
        self._chunk_duration = chunk_duration
        self._sample_rate = sample_rate
        self._capture_device = capture_device
        # Passthrough: forward raw captured audio to output device at original_volume.
        # Both attributes are read every 0.1 s so live updates take effect quickly.
        self._playback_device = playback_device
        self._original_volume = original_volume
        self._overlap_seconds = overlap_seconds
        # Tail of the last emitted chunk, prepended to the next chunk so boundary
        # words always appear complete in at least one chunk's audio.
        self._tail_buf: bytes = b""

    async def stream(self) -> AsyncIterator[tuple[bytes, float]]:
        """Yields (pcm_chunk, captured_at) pairs. captured_at is monotonic time when the
        chunk was fully assembled — used by the pipeline to discard chunks that fall
        inside a TTS mute window even if they are dequeued after the window expires."""
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[tuple[bytes, float]] = asyncio.Queue()

        def _run():
            pa = pyaudio.PyAudio()
            try:
                device = _find_loopback_device(pa, self._capture_device)
                native_rate = int(device["defaultSampleRate"])
                channels = min(int(device["maxInputChannels"]), 2)
                read_frames = int(native_rate * _READ_SECONDS)

                in_stream = pa.open(
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

                # Open passthrough output stream if a device is configured.
                # Uses the same format as the input so no resampling is needed.
                out_stream = None
                if self._playback_device:
                    out_idx = _find_output_device_index(pa, self._playback_device)
                    if out_idx is not None:
                        try:
                            out_stream = pa.open(
                                format=pyaudio.paInt16,
                                channels=channels,
                                rate=native_rate,
                                output=True,
                                output_device_index=out_idx,
                                frames_per_buffer=read_frames,
                            )
                            print(f"[AudioCapture] passthrough -> '{self._playback_device}'")
                        except Exception as exc:
                            print(f"[AudioCapture] cannot open passthrough output: {exc}")

                buffer = b""
                try:
                    while True:
                        raw = in_stream.read(read_frames, exception_on_overflow=False)

                        # Passthrough: forward raw audio to output device.
                        if out_stream is not None:
                            vol = self._original_volume
                            out_stream.write(_scale_pcm16(raw, vol) if vol != 1.0 else raw)

                        pcm = _to_mono_16k(raw, channels, native_rate, self._sample_rate)
                        buffer += pcm
                        target = int(self._sample_rate * self._chunk_duration) * 2  # bytes
                        if len(buffer) >= target:
                            chunk = buffer[:target]
                            buffer = buffer[target:]
                            # Prepend tail of previous chunk so boundary words are complete.
                            overlap_bytes = int(self._sample_rate * self._overlap_seconds) * 2
                            full_chunk = self._tail_buf + chunk
                            self._tail_buf = chunk[-overlap_bytes:] if overlap_bytes > 0 else b""
                            asyncio.run_coroutine_threadsafe(
                                queue.put((full_chunk, time.monotonic())), loop
                            )
                finally:
                    in_stream.stop_stream()
                    in_stream.close()
                    if out_stream:
                        out_stream.stop_stream()
                        out_stream.close()
            finally:
                pa.terminate()

        loop.run_in_executor(None, _run)
        while True:
            yield await queue.get()  # yields (chunk, captured_at)


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

    default = pa.get_default_wasapi_loopback()
    return default if default else loopbacks[0]


def _find_output_device_index(pa: pyaudio.PyAudio, name_filter: str) -> int | None:
    needle = name_filter.lower()
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if (info.get("maxOutputChannels", 0) > 0
                and not info.get("isLoopbackDevice")
                and needle in info["name"].lower()):
            return i
    print(f"[AudioCapture] output device not found: {name_filter!r}")
    return None


def _scale_pcm16(data: bytes, volume: float) -> bytes:
    """Scale 16-bit PCM samples by volume (0.0–1.0). Returns silence for volume=0."""
    if volume <= 0.0:
        return bytes(len(data))
    n = len(data) // 2
    samples = struct.unpack(f"<{n}h", data)
    scaled = (max(-32768, min(32767, int(s * volume))) for s in samples)
    return struct.pack(f"<{n}h", *scaled)


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
