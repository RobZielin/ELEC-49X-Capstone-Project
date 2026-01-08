# code to connect to the ESP32 via bluetooth and send/receive data

import asyncio
from bleak import BleakClient

UART_SERVICE = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX      = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # recieving
UART_RX      = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # writing

ESP32_ADDR = "" # need to find this

async def main():
    def handle_rx(sender, data):
        print("ESP32 → PC:", data)


    # asynchronous function that sends a test message and listens for notifications
    async with BleakClient(ESP32_ADDR) as client:
        print("Connected:", client.is_connected)

        await client.start_notify(UART_TX, handle_rx)

        # write to client
        await client.write_gatt_char(UART_RX, b"hello")

        # listen
        await asyncio.sleep(10)

asyncio.run(main())
