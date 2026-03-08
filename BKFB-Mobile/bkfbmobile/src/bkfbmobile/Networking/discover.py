import asyncio

from bkfbmobile.Networking import ble_runtime

async def main():
    devices = await ble_runtime.discover()
    for d in devices:
        print(d)


if __name__ == "__main__":
    asyncio.run(main())
