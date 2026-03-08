"""
bleekware.Client
"""

import asyncio
from collections import deque
import functools
import inspect

from java import jarray, jbyte, jclass, jint, jvoid, Override, static_proxy
from java.util import UUID

from android.bluetooth import (
    BluetoothAdapter,
    BluetoothGatt,
    BluetoothGattCallback,
    BluetoothProfile,
    BluetoothGattCharacteristic,
    BluetoothGattDescriptor,
)
from android.os import Build

from . import BLEDevice, BLEGattService
from . import bleekWareError, bleekWareCharacteristicNotFoundError
from . import check_for_permissions

DEBUG_LOGS = False


def _log(*args, **kwargs):
    if DEBUG_LOGS:
        print(*args, **kwargs)


received_data = deque()
status_message = []
services = []
write_status = {}
descriptor_write_status = {}
async_callbacks = set()

# Client Characteristic Configuration Descriptor
CCCD = '00002902-0000-1000-8000-00805f9b34fb'

class _PythonGattCallback(static_proxy(BluetoothGattCallback)):
    """Callback class for GattClient. PRIVATE."""

    def __init__(self, client):
        super(_PythonGattCallback, self).__init__()
        self.client = client
        _log(f"[bleekWare] >>> _PythonGattCallback created with client: {client}")
        _log(f"[bleekWare] >>> Callback instance: {id(self)}")

    @Override(jvoid, [BluetoothGatt, jint, jint])
    def onConnectionStateChange(self, gatt, status, newState):
        """Register connect or disconnect events.

        This is the callback function for Android's 'device.ConnectGatt'.
        """
        _log(f"[bleekWare] onConnectionStateChange: status={status}, newState={newState}")
        if newState == BluetoothProfile.STATE_CONNECTED:
            _log(f"[bleekWare] >>> CONNECTED, discovering services...")
            status_message.append('connected')
            gatt.discoverServices()
        elif newState == BluetoothProfile.STATE_DISCONNECTED:
            _log(f"[bleekWare] >>> DISCONNECTED")
            status_message.append('disconnected')
            gatt = None
            services.clear()
            if self.client.disconnected_callback:
                self.client.disconnected_callback()

    @Override(jvoid, [BluetoothGatt, jint])
    def onServicesDiscovered(self, gatt, status):
        """Write services to list.

        This is the callback function for Android's 'gatt.discoverServices'.
        """
        _log(f"[bleekWare] onServicesDiscovered: status={status}")
        if status == BluetoothGatt.GATT_SUCCESS:
            _log(f"[bleekWare] >>> Service discovery SUCCESSFUL")
        else:
            _log(f"[bleekWare] >>> Service discovery FAILED")
        services.extend(gatt.getServices().toArray())
        _log(f"[bleekWare] >>> Found {len(services)} services")
        # getServices returns an ArrayList, must be converted to Array to work
        # with Python

    @Override(
        jvoid,
        [BluetoothGatt, BluetoothGattCharacteristic, jarray(jbyte), jint],
    )
    @Override(jvoid, [BluetoothGatt, BluetoothGattCharacteristic, jint])
    def onCharacteristicRead(self, gatt, characteristic, *args):
        """Put characteristic's read value to a data list.

        This is the callback function for Android's 'gatt.readCharacteristic'.

        Covers the deprecated version (API level < 33 / Android 12 and older)
        and the actual version (API level 33 upwards  / Android 13 and newer).
        """
        status = args[-1]
        # Android 12 and below:
        if len(args) == 1:
            value = characteristic.getValue()
        else:
            value = args[0]
        if status == BluetoothGatt.GATT_SUCCESS:
            received_data.append(value)

    @Override(
        jvoid, [BluetoothGatt, BluetoothGattCharacteristic, jarray(jbyte)]
    )
    @Override(jvoid, [BluetoothGatt, BluetoothGattCharacteristic])
    def onCharacteristicChanged(self, gatt, characteristic, *args):
        """Read notifications from the peripheral.

        Supports both callback signatures:
        - Android <= 12: (gatt, characteristic)
        - Android >= 13: (gatt, characteristic, value)
        """
        uuid = str(characteristic.getUuid()).lower()
        if len(args) == 0:
            data = characteristic.getValue()
        else:
            data = args[0]

        if data is None:
            _log(f"[bleekWare] *** onCharacteristicChanged FIRED for {uuid}, but data is None")
            return

        _log(f"[bleekWare] *** onCharacteristicChanged FIRED for {uuid}")
        _log(f"[bleekWare] *** Received {len(data)} bytes: {data[:100] if len(data) > 100 else data}")
        received_data.append(data)

    @Override(
        jvoid, [BluetoothGatt, BluetoothGattCharacteristic, jint]
    )
    def onCharacteristicWrite(self, gatt, characteristic, status):
        """Track write completion.

        This is the callback function for Android's 'gatt.writeCharacteristic'.
        """
        uuid = str(characteristic.getUuid()).lower()
        _log(f"[bleekWare] >>> onCharacteristicWrite FIRED: uuid={uuid}, status={status}")
        if status == BluetoothGatt.GATT_SUCCESS:
            _log(f"[bleekWare] Write successful to {uuid}")
            write_status[uuid] = True
        else:
            _log(f"[bleekWare] Write failed to {uuid}, status: {status}")
            write_status[uuid] = False

    @Override(jvoid, [BluetoothGatt, BluetoothGattDescriptor, jint])
    def onDescriptorWrite(self, gatt, descriptor, status):
        """Track descriptor write completion.

        This is the callback function for Android's 'gatt.writeDescriptor'.
        """
        uuid = str(descriptor.getUuid()).lower()
        _log(f"[bleekWare] >>> onDescriptorWrite FIRED: uuid={uuid}, status={status}")
        if status == BluetoothGatt.GATT_SUCCESS:
            _log(f"[bleekWare] Descriptor write successful: {uuid}")
            descriptor_write_status[uuid] = True
        else:
            _log(f"[bleekWare] Descriptor write failed: {uuid}, status: {status}")
            descriptor_write_status[uuid] = False

    @Override(jvoid, [BluetoothGatt, jint, jint])
    def onMtuChanged(self, gatt, mtu, status):
        """Handle change in MTU size.

        This is the callback function for changes in MTU.
        """
        if status == BluetoothGatt.GATT_SUCCESS:
            self.client.mtu = mtu


class Client:
    """Class to connect to a Bluetooth LE GATT server and communicate."""

    client = None

    def __init__(
        self,
        address_or_ble_device,
        disconnected_callback=None,
        services=None,
        **kwargs,
    ):
        self.activity = self.context = jclass(
            'org.beeware.android.MainActivity'
        ).singletonThis

        if isinstance(address_or_ble_device, BLEDevice):
            self._address = address_or_ble_device.address
            self.device = address_or_ble_device.details
        else:
            self._address = address_or_ble_device
            self.device = BluetoothAdapter.getDefaultAdapter().getRemoteDevice(
                self._address
            )

        self.disconnected_callback = (
            None
            if disconnected_callback is None
            else functools.partial(disconnected_callback, self)
        )
        if services:
            raise NotImplementedError()
        self.adapter = None
        self.gatt = None
        self._services = []
        self.mtu = 23

    def __str__(self):
        return f'{self.__class__.__name__}, {self.address}'

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    async def connect(self, **kwargs):
        """Connect to a GATT server."""
        _log(f"[bleekWare] Starting connection to {self._address}")
        
        # Request runtime permissions for Bluetooth
        try:
            check_for_permissions(self.activity)
            _log("[bleekWare] Permissions requested")
        except Exception as e:
            _log(f"[bleekWare] Permission request failed: {e}")
            raise bleekWareError(f"Failed to request Bluetooth permissions: {e}")
        
        # Give time for permission dialog and user response
        # Permissions are requested asynchronously on Android
        await asyncio.sleep(0.5)
        
        self.adapter = BluetoothAdapter.getDefaultAdapter()
        if self.adapter is None:
            _log("[bleekWare] Bluetooth not supported")
            raise bleekWareError('Bluetooth is not supported on this device')
        if self.adapter.getState() != BluetoothAdapter.STATE_ON:
            _log("[bleekWare] Bluetooth is off")
            raise bleekWareError('Bluetooth is turned off')

        if self.gatt is not None:
            self.gatt.connect()
        else:
            # Make a reference for external access
            Client.client = self

            # Create a GATT connection
            self.gatt_callback = _PythonGattCallback(Client.client)
            _log(f"[bleekWare] >>> Calling connectGatt with callback: {id(self.gatt_callback)}")
            self.gatt = self.device.connectGatt(
                self.activity, False, self.gatt_callback
            )
            _log(f"[bleekWare] >>> connectGatt returned GATT: {self.gatt}")
            self.gatt_callback.gatt = self.gatt

            # Read the services
            while not services:
                await asyncio.sleep(0.1)
            self._services = await self._get_services()

            # Ask for max Mtu size
            self.gatt.requestMtu(517)

            # Avoid racing CCCD writes with MTU negotiation on Android.
            # If MTU callback doesn't arrive, continue after a short timeout.
            mtu_wait = 0
            while self.mtu == 23 and mtu_wait < 20:
                await asyncio.sleep(0.05)
                mtu_wait += 1
            _log(f"[bleekWare] MTU ready for next GATT ops: {self.mtu}")

        return True  # For Bleak backwards compatibility

    async def disconnect(self):
        """Disconnect from connected GATT server."""
        if self.gatt is None:
            return True
        try:
            self.gatt.disconnect()
            self.gatt.close()
        except Exception as e:
            status_message.append(e)

        self.gatt = None
        self._services.clear()
        services.clear()
        status_message.clear()
        received_data.clear()
        Client.client = None

        return True  # For Bleak backwards compatibility

    async def start_notify(self, uuid, callback, **kwargs):
        """Start notification of a notifying characteristic.

        ``uuid`` (characteristic specifier) must be an UUID as string
        ``callback`` can be a usual or async callback method
        """
        if not self.is_connected:
            raise bleekWareError('Client not connected')

        self.notification_callback = callback
        characteristic = self._find_characteristic(uuid)
        if characteristic:
            _log(f"[bleekWare] >>> START_NOTIFY: Characteristic found for {uuid}")
            props = characteristic.getProperties()
            _log(f"[bleekWare] >>> Characteristic properties: {props}")
            can_notify = bool(props & BluetoothGattCharacteristic.PROPERTY_NOTIFY)
            can_indicate = bool(props & BluetoothGattCharacteristic.PROPERTY_INDICATE)
            _log(f"[bleekWare] >>> Can NOTIFY: {can_notify}, Can INDICATE: {can_indicate}")
            
            _log(f"[bleekWare] Enabling notifications for {uuid}")
            
            # Enable notifications at GATT level - this is required
            try:
                notification_enabled = self.gatt.setCharacteristicNotification(characteristic, True)
                _log(f"[bleekWare] >>> setCharacteristicNotification COMPLETED with result: {notification_enabled}")
            except Exception as e:
                _log(f"[bleekWare] >>> setCharacteristicNotification RAISED EXCEPTION: {e}")
                raise
            
            # Try to write CCCD descriptor if it exists
            # Note: Some devices/Android versions don't require explicit CCCD write
            # if setCharacteristicNotification already enables it
            descriptor = characteristic.getDescriptor(UUID.fromString(CCCD))
            if descriptor:
                descriptor_uuid = str(descriptor.getUuid()).lower()
                try:
                    descriptor_write_status.pop(descriptor_uuid, None)

                    # Retry once; some Android stacks return success but don't actually apply CCCD on first try.
                    for attempt in range(1, 3):
                        if Build.VERSION.SDK_INT < 33:
                            descriptor.setValue(
                                BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                            )
                            write_result = self.gatt.writeDescriptor(descriptor)
                        else:
                            write_result = self.gatt.writeDescriptor(
                                descriptor,
                                BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE,
                            )

                        _log(
                            f"[bleekWare] CCCD descriptor write attempt {attempt} queued: {write_result}"
                        )

                        # Wait briefly for callback confirmation when available.
                        for _ in range(15):  # up to 1.5s
                            if descriptor_uuid in descriptor_write_status:
                                if descriptor_write_status[descriptor_uuid]:
                                    _log("[bleekWare] CCCD write CONFIRMED")
                                    attempt = 99
                                else:
                                    _log("[bleekWare] CCCD write FAILED in callback")
                                break
                            await asyncio.sleep(0.1)

                        if attempt == 99:
                            break
                        if descriptor_uuid in descriptor_write_status:
                            break

                    if descriptor_uuid not in descriptor_write_status:
                        # Some devices do not invoke onDescriptorWrite, but can still work.
                        _log(
                            "[bleekWare] CCCD write callback timeout (device may still accept subscription)"
                        )
                        
                except Exception as e:
                    _log(f"[bleekWare] Error writing CCCD descriptor: {e}")
            else:
                _log(f"[bleekWare] No CCCD descriptor found, relying on setCharacteristicNotification alone")
            
            # Give Android time to set up notifications
            await asyncio.sleep(0.2)
            _log(f"[bleekWare] Starting notification listener loop for {uuid}")

            # Start the notification loop in a background task
            async def notification_loop():
                _log(f"[bleekWare] Notification loop started, callback is coroutine: {inspect.iscoroutinefunction(callback)}")
                loop_count = 0
                while self.notification_callback:
                    if received_data:
                        # Drain all queued notifications quickly to avoid throttling.
                        while received_data and self.notification_callback:
                            data = received_data.popleft()
                            _log(f"[bleekWare] >>> NOTIFICATION RECEIVED: {len(data)} bytes from {uuid}")
                            _log(f"[bleekWare] >>> DATA: {data[:100] if len(data) > 100 else data}")
                            if inspect.iscoroutinefunction(callback):
                                task = asyncio.create_task(
                                    callback(characteristic, bytearray(data))
                                )
                                async_callbacks.add(task)
                                task.add_done_callback(async_callbacks.discard)
                            else:
                                callback(characteristic, bytearray(data))
                    else:
                        loop_count += 1
                        if loop_count % 100 == 0:  # Log every 10 seconds
                            _log(f"[bleekWare] Waiting for notifications... ({loop_count * 100}ms elapsed)")
                    # Keep this low to prevent capping notify throughput on Android.
                    await asyncio.sleep(0.005)
                _log(f"[bleekWare] Notification loop ended for {uuid}")
            
            # Create the notification loop task
            task = asyncio.create_task(notification_loop())
            async_callbacks.add(task)
            task.add_done_callback(async_callbacks.discard)
            _log(f"[bleekWare] Notification listener task created")
            return

    async def stop_notify(self, uuid):
        """Stop notification of a notifying characteristic."""
        characteristic = self._find_characteristic(uuid)
        if characteristic:
            self.gatt.setCharacteristicNotification(characteristic, False)
            descriptor = characteristic.getDescriptor(UUID.fromString(CCCD))
            descriptor.setValue(
                BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE
            )
            self.gatt.writeDescriptor(descriptor)

            self.notification_callback = None

    async def read_gatt_char(self, uuid):
        """Read from a characteristic.

        For bleekWare, you must pass the characteristic's UUID
        as string.
        """
        characteristic = self._find_characteristic(uuid)
        if characteristic:
            self.gatt.readCharacteristic(characteristic)
            while not received_data:
                await asyncio.sleep(0.1)
            return bytearray(received_data.popleft())
        else:
            raise bleekWareCharacteristicNotFoundError(uuid)

    async def write_gatt_char(self, uuid, data, response=None):
        """Write to a characteristic.

        For bleekWare, you must pass the characteristic's UUID
        as string.
        """
        uuid_lower = uuid.lower()
        _log(f"[bleekWare] write_gatt_char called for {uuid} with {len(data)} bytes: {data}")
        characteristic = self._find_characteristic(uuid)
        if characteristic:
            # Check properties using bitwise operations
            props = characteristic.getProperties()
            
            # For UART, always use NO_RESPONSE (Nordic UART doesn't require response)
            write_type = BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
            _log(f"[bleekWare] Using WRITE_TYPE_NO_RESPONSE (UART write)")

            if Build.VERSION.SDK_INT < 33:  # Android 12 and older
                characteristic.setWriteType(write_type)
                characteristic.setValue(data)
                result = self.gatt.writeCharacteristic(characteristic)
                _log(f"[bleekWare] Write result (Android <13): {result}")
            else:
                result = self.gatt.writeCharacteristic(characteristic, data, write_type)
                _log(f"[bleekWare] Write result (Android 13+): {result}")
            
            # Add small delay to allow write to process
            await asyncio.sleep(0.05)
        else:
            raise bleekWareCharacteristicNotFoundError(uuid)

    @property
    def address(self):
        return self._address

    @property
    def is_connected(self):
        return False if self.gatt is None else True

    @property
    def mtu_size(self):
        return self.mtu

    @property
    def services(self):
        """Return list of services and their characteristics.

        As list of BLEGattService objects.
        """
        if not self._services:
            raise bleekWareError(
                'Service Discovery has not been performed yet'
            )

        return self._services

    async def _get_services(self):
        """Read and store the announced services of a GATT server. PRIVAT.

        The characteristics of the services are also read. Both are
        stored in a list of BLEGattService objects.
        """
        if self._services:
            return self._services
        _log(f"[bleekWare] Discovered {len(services)} services")
        for service in services:
            new_service = BLEGattService(service)
            characts = service.getCharacteristics().toArray()
            _log(f"[bleekWare] Service {service.getUuid()} has {len(characts)} characteristics")
            for charact in characts:
                uuid_str = str(charact.getUuid())
                _log(f"[bleekWare]   - Characteristic: {uuid_str}")
                new_service.characteristics.append(uuid_str)
            self._services.append(new_service)
        return self._services

    def _find_characteristic(self, uuid):
        """Find and return characteristic object by UUID. PRIVATE."""
        # Normalize to lowercase for comparison
        uuid = uuid.lower()
        if len(uuid) == 4:
            uuid = f'0000{uuid}-0000-1000-8000-00805f9b34fb'
        elif len(uuid) == 8:
            uuid = f'{uuid}-0000-1000-8000-00805f9b34fb'
        _log(f"[bleekWare] Looking for characteristic: {uuid}")
        for service in self._services:
            # Normalize stored UUIDs to lowercase for comparison
            if uuid in [c.lower() for c in service.characteristics]:
                _log(f"[bleekWare] Found characteristic in service {service.service.getUuid()}")
                return service.service.getCharacteristic(UUID.fromString(uuid))
        _log(f"[bleekWare] Characteristic {uuid} not found in any service")
        return None
