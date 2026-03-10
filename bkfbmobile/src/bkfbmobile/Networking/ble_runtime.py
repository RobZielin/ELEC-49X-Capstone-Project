# this is specifically for the android version

import asyncio
import contextlib
import os
import struct
import sys
from typing import Awaitable, Callable, Optional

DEBUG_LOGS = False


def _log(*args, **kwargs):
    if DEBUG_LOGS:
        print(*args, **kwargs)

UART_TX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"

SampleHandler = Callable[[float, float, float], None]


def _is_android() -> bool:
    if sys.platform == "android":
        return True
    # Some Android runtime variants expose linux platform with Android env vars
    return any(
        key in os.environ
        for key in ["ANDROID_ARGUMENT", "ANDROID_BOOTLOGO", "ANDROID_STORAGE"]
    )


def _backend_name() -> str:
    backend = "bleekWare" if _is_android() else "bleak"
    _log(f"[ble_runtime] Backend selection: is_android={_is_android()}, sys.platform={sys.platform}, backend={backend}")
    return backend


def _get_bleak_client_class():
    if _is_android():
        # Preferred import path for the bleekWare repo copied into this app package.
        try:
            from bkfbmobile.bleekWare.Client import Client  # type: ignore

            return Client
        except Exception as exc:
            raise ImportError(
                "Android BLE backend not found. Copy the `bleekWare/` folder into "
                "`src/bkfbmobile/bleekWare/` and configure Briefcase staticProxy."
            ) from exc

    from bleak import BleakClient  # type: ignore

    return BleakClient


def _get_bleak_scanner_class():
    if _is_android():
        try:
            from bkfbmobile.bleekWare.Scanner import Scanner  # type: ignore

            return Scanner
        except Exception as exc:
            raise ImportError(
                "Android BLE scanner backend not found. Copy the `bleekWare/` folder into "
                "`src/bkfbmobile/bleekWare/` and configure Briefcase staticProxy."
            ) from exc

    from bleak import BleakScanner  # type: ignore

    return BleakScanner


def decode_payload(data: bytes):
    try:
        text = data.decode("utf-8").strip()
        if " " in text:
            return text
        return float(text)
    except (UnicodeDecodeError, ValueError):
        if len(data) == 4:
            return struct.unpack("<f", data)[0]
        if len(data) == 2:
            return float(struct.unpack("<h", data)[0])
        if len(data) == 1:
            return float(data[0])
        if len(data) % 4 == 0:
            return [struct.unpack("<f", data[i : i + 4])[0] for i in range(0, len(data), 4)]
        return data


def parse_xyz_sample(text: str) -> Optional[tuple[float, float, float]]:
    parts = text.strip().split()
    if len(parts) != 7 or parts[1] != "x" or parts[3] != "y" or parts[5] != "z":
        return None

    try:
        return float(parts[2]), float(parts[4]), float(parts[6])
    except ValueError:
        return None


async def discover(timeout: float = 5.0):
    scanner_cls = _get_bleak_scanner_class()
    devices = await scanner_cls.discover(timeout=timeout)
    return devices


async def _keep_alive(client, interval: float = 8.0) -> None:
    while True:
        try:
            await client.write_gatt_char(UART_RX, b"batman")
        except Exception:
            return
        await asyncio.sleep(interval)


async def stream_samples(
    address: str,
    on_sample: SampleHandler,
    stop_event: asyncio.Event,
    on_status: Optional[Callable[[str], Awaitable[None]]] = None,
) -> None:
    _log(f"[ble_runtime] stream_samples starting for {address} using {_backend_name()}")
    disconnect_event = asyncio.Event()

    async def emit_status(text: str) -> None:
        _log(f"[ble_runtime] Status: {text}")
        if on_status:
            await on_status(text)

    def on_disconnect(_client):
        _log("[ble_runtime] Disconnect callback triggered")
        disconnect_event.set()

    def on_rx(_sender, data):
        _log(f"[ble_runtime] Received {len(data)} bytes: {data[:50]}")  # Show first 50 bytes
        decoded = decode_payload(bytes(data))
        _log(f"[ble_runtime] Decoded: {decoded}")
        if not isinstance(decoded, str):
            _log(f"[ble_runtime] Decoded is not string, type: {type(decoded)}")
            return

        sample = parse_xyz_sample(decoded)
        if sample is None:
            _log("[ble_runtime] parse_xyz_sample returned None")
            return

        _log(f"[ble_runtime] Parsed sample: {sample}")
        on_sample(*sample)

    client_cls = _get_bleak_client_class()
    _log(f"[ble_runtime] Got client class: {client_cls}")
    await emit_status(f"Connecting using {_backend_name()}...")

    try:
        async with client_cls(address, disconnected_callback=on_disconnect) as client:
            _log("[ble_runtime] Client connected, setting up notifications")
            await emit_status("Connected")
            await client.start_notify(UART_TX, on_rx)
            _log(f"[ble_runtime] Notifications started for {UART_TX}")
            await client.write_gatt_char(UART_RX, b"batman initiated")
            _log(f"[ble_runtime] Wrote initiation command to {UART_RX}")
            _log("[ble_runtime] Entering main loop, waiting for data...")

            keep_task = asyncio.create_task(_keep_alive(client))
            try:
                while not stop_event.is_set() and not disconnect_event.is_set():
                    await asyncio.sleep(0.05)
            finally:
                keep_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await keep_task
                    
        _log("[ble_runtime] Client disconnected cleanly")
    except Exception as e:
        _log(f"[ble_runtime] Exception in stream_samples: {e}")
        import traceback
        traceback.print_exc()
        raise

    if disconnect_event.is_set() and not stop_event.is_set():
        await emit_status("Disconnected")
