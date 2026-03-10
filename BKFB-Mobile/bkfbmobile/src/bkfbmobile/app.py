"""
Multi-page app with Live Feed, Average Stroke, and Bluetooth Config screens.
Responsive design for both mobile and desktop.
"""

import asyncio
import os
import sys
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from bkfbmobile import bkfb


class BeeWareProject(toga.App):
    def startup(self):
        self.stream_task = None
        self.stop_event = None
        self.mobile_preview_forced = self._is_mobile_preview_forced()
        
        # Detect if running on mobile
        self.is_mobile = self._detect_mobile()

        # Shared image views that will be updated by BLE stream
        self.live_plot_view = toga.ImageView(style=Pack(flex=1, padding=10))
        self.avg_plot_view = toga.ImageView(style=Pack(flex=1, padding=10))
        self.compare_plot_view = toga.ImageView(style=Pack(flex=1, padding=10))
        self.status_label = toga.Label("Idle", style=Pack(margin=5))
        
        # Load existing Bluetooth address from config
        self.config_path = os.path.join(os.path.dirname(bkfb.__file__), 'Networking', 'ESP32.cfg')
        self.bt_address = self._load_bt_address()
        self.stroke_axis_config_path = os.path.join(os.path.dirname(bkfb.__file__), 'Networking', 'StrokeAxis.cfg')
        self.stroke_axis = self._load_stroke_axis()
        bkfb.set_stroke_axis(self.stroke_axis)
        self.stroke_direction_config_path = os.path.join(os.path.dirname(bkfb.__file__), 'Networking', 'StrokeDirection.cfg')
        self.stroke_direction = self._load_stroke_direction()
        bkfb.set_stroke_direction(self.stroke_direction)
        
        # For BLE scanning
        self.discovered_devices = {}
        self.scanning = False

        # Create the three pages
        if self.is_mobile:
            live_feed_page = self._create_live_feed_page_mobile()
            avg_stroke_page = self._create_avg_stroke_page_mobile()
            compare_strokes_page = self._create_compare_strokes_page_mobile()
            config_page = self._create_config_page_mobile()
        else:
            live_feed_page = self._create_live_feed_page_desktop()
            avg_stroke_page = self._create_avg_stroke_page_desktop()
            compare_strokes_page = self._create_compare_strokes_page_desktop()
            config_page = self._create_config_page_desktop()

        # Create tab container
        container = toga.OptionContainer(
            content=[
                ("Live Feed", live_feed_page),
                ("Average Stroke", avg_stroke_page),
                ("Compare Stroke", compare_strokes_page),
                ("Bluetooth Config", config_page),
            ],
            style=Pack(flex=1)
        )

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = container
        self.main_window.show()
        
        # Scale window only for desktop preview of mobile UI.
        if self.mobile_preview_forced and not (self._is_android_runtime() or self._is_ios_runtime()):
            self._set_mobile_window_size()

    def _is_mobile_preview_forced(self):
        """Return True when mobile UI is forced for desktop preview/testing."""
        return os.environ.get("FORCE_MOBILE_UI", "").lower() in ["1", "true", "yes"]

    def _is_android_runtime(self):
        """Detect Android runtime across Python/packaging variants."""
        if sys.platform == "android":
            return True
        # Some Android runtimes expose linux platform with Android env vars.
        return any(
            key in os.environ
            for key in ["ANDROID_ARGUMENT", "ANDROID_BOOTLOGO", "ANDROID_STORAGE"]
        )

    def _is_ios_runtime(self):
        """Detect iOS runtime across Python/packaging variants."""
        if sys.platform == "ios":
            return True
        return "IOS_ARGUMENT" in os.environ
    
    def _detect_mobile(self):
        """Detect if running on mobile platform.
        
        Can be overridden with FORCE_MOBILE_UI environment variable for testing.
        Example: FORCE_MOBILE_UI=1 briefcase dev
        """
        # Allow forcing mobile UI for preview/testing purposes
        if self.mobile_preview_forced:
            return True

        if self._is_android_runtime() or self._is_ios_runtime():
            return True
        
        return False
    
    def _set_mobile_window_size(self):
        """Set window size to mobile device aspect ratio.
        
        Default: Portrait (375×667 - iPhone size)
        Landscape: Set MOBILE_LANDSCAPE=1 environment variable
        """
        try:
            # Check if landscape mode is enabled
            is_landscape = os.environ.get('MOBILE_LANDSCAPE', '').lower() in ['1', 'true', 'yes']
            
            if is_landscape:
                # Standard iPhone size in landscape (667×375)
                self.main_window.size = (667, 375)
            else:
                # Standard iPhone size in portrait (375×667)
                self.main_window.size = (375, 667)
        except Exception as e:
            print(f"Could not set window size for mobile preview: {e}")
    
    # mobile ui
    
    def _create_live_feed_page_mobile(self):
        """Create mobile-optimized live feed page with vertical layout."""
        clear_button = toga.Button("Clear", on_press=self.clear_plots, style=Pack(padding=5, flex=1))
        controls = toga.Box(style=Pack(direction=ROW, padding=5))
        controls.add(clear_button)

        page_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
        page_box.add(self.live_plot_view)
        page_box.add(controls)

        return page_box
    
    def _create_avg_stroke_page_mobile(self):
        """Create mobile-optimized average stroke page."""
        clear_button = toga.Button("Clear", on_press=self.clear_plots, style=Pack(padding=5, flex=1))
        controls = toga.Box(style=Pack(direction=ROW, padding=5))
        controls.add(clear_button)

        page_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
        page_box.add(self.avg_plot_view)
        page_box.add(controls)

        return page_box

    def _create_compare_strokes_page_mobile(self):
        """Create mobile page for comparing the last two detected strokes."""
        clear_button = toga.Button("Clear", on_press=self.clear_plots, style=Pack(padding=5, flex=1))
        controls = toga.Box(style=Pack(direction=ROW, padding=5))
        controls.add(clear_button)

        page_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
        page_box.add(self.compare_plot_view)
        page_box.add(controls)

        return page_box
    
    def _create_config_page_mobile(self):
        """Create mobile-optimized bluetooth configuration page."""
        title_label = toga.Label(
            "Bluetooth Configuration",
            style=Pack(padding=10, font_size=14, font_weight="bold")
        )
        
        # Scan button
        scan_button = toga.Button(
            "Scan for Devices",
            on_press=self.scan_devices,
            style=Pack(padding=5, flex=1)
        )
        
        # Device selection dropdown
        self.device_selection = toga.Selection(
            items=["No devices found"],
            on_change=self.on_device_selected,
            style=Pack(padding=5, flex=1)
        )
        
        # Bluetooth address input section
        address_label = toga.Label(
            "Bluetooth Device Address:",
            style=Pack(padding=(10, 5, 5, 5))
        )
        
        self.bt_address_input = toga.TextInput(
            value=self.bt_address or "",
            placeholder="Enter Bluetooth MAC address (e.g., AA:BB:CC:DD:EE:FF)",
            style=Pack(padding=5, flex=1)
        )

        stroke_axis_label = toga.Label(
            "Stroke Axis:",
            style=Pack(padding=(10, 5, 5, 5))
        )

        self.stroke_axis_selection = toga.Selection(
            items=["X-axis", "Y-axis", "Z-axis"],
            on_change=self.on_stroke_axis_changed,
            style=Pack(padding=5, flex=1)
        )
        self.stroke_axis_selection.value = self._stroke_axis_label(self.stroke_axis)

        stroke_direction_label = toga.Label(
            "Stroke Direction:",
            style=Pack(padding=(10, 5, 5, 5))
        )

        self.stroke_direction_selection = toga.Selection(
            items=["+", "-"],
            on_change=self.on_stroke_direction_changed,
            style=Pack(padding=5, flex=1)
        )
        self.stroke_direction_selection.value = "+" if self.stroke_direction >= 0 else "-"

        stroke_axis_row = toga.Box(style=Pack(direction=ROW, padding=5))
        stroke_axis_row.add(self.stroke_axis_selection)
        stroke_axis_row.add(self.stroke_direction_selection)

        save_button = toga.Button(
            "Save Address",
            on_press=self.save_bt_address,
            style=Pack(padding=5, flex=1)
        )

        # Full-width layout for mobile
        address_section = toga.Box(style=Pack(direction=COLUMN, padding=5, flex=1))
        address_section.add(self.bt_address_input)
        address_section.add(save_button)
        
        # Connection controls - stacked vertically on mobile
        connect_button = toga.Button("Connect", on_press=self.connect_live, style=Pack(padding=5, flex=1))
        stop_button = toga.Button("Stop", on_press=self.stop_live, style=Pack(padding=5, flex=1))
        
        controls = toga.Box(style=Pack(direction=COLUMN, padding=10, flex=1))
        controls.add(connect_button)
        controls.add(stop_button)
        
        page_box = toga.Box(style=Pack(direction=COLUMN, flex=1, padding=10))
        page_box.add(title_label)
        page_box.add(scan_button)
        page_box.add(self.device_selection)
        page_box.add(address_label)
        page_box.add(address_section)
        page_box.add(stroke_axis_label)
        page_box.add(stroke_axis_row)
        page_box.add(self.status_label)
        page_box.add(controls)
        
        return page_box

    # desktop ui

    def _create_live_feed_page_desktop(self):
        """Create desktop-optimized live feed page with side-by-side layout."""
        clear_button = toga.Button("Clear", on_press=self.clear_plots, style=Pack(padding=5))
        controls = toga.Box(style=Pack(direction=ROW, padding=5))
        controls.add(clear_button)
        controls.add(toga.Divider(style=Pack(flex=1)))

        page_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
        page_box.add(self.live_plot_view)
        page_box.add(controls)

        return page_box
    
    def _create_avg_stroke_page_desktop(self):
        """Create desktop-optimized average stroke page."""
        clear_button = toga.Button("Clear", on_press=self.clear_plots, style=Pack(padding=5))
        controls = toga.Box(style=Pack(direction=ROW, padding=5))
        controls.add(clear_button)
        controls.add(toga.Divider(style=Pack(flex=1)))

        page_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
        page_box.add(self.avg_plot_view)
        page_box.add(controls)

        return page_box

    def _create_compare_strokes_page_desktop(self):
        """Create desktop page for comparing the last two detected strokes."""
        clear_button = toga.Button("Clear", on_press=self.clear_plots, style=Pack(padding=5))
        controls = toga.Box(style=Pack(direction=ROW, padding=5))
        controls.add(clear_button)
        controls.add(toga.Divider(style=Pack(flex=1)))

        page_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
        page_box.add(self.compare_plot_view)
        page_box.add(controls)

        return page_box
    
    def _create_config_page_desktop(self):
        """Create desktop-optimized bluetooth configuration page with full-width address input."""
        title_label = toga.Label(
            "Bluetooth Configuration",
            style=Pack(padding=10, font_size=16, font_weight="bold")
        )
        
        # Scan section
        scan_label = toga.Label(
            "Device Discovery:",
            style=Pack(padding=(10, 5, 5, 5), font_weight="bold")
        )
        
        scan_button = toga.Button(
            "Scan for Devices",
            on_press=self.scan_devices,
            style=Pack(padding=5, width=150)
        )
        
        # Device selection dropdown
        self.device_selection = toga.Selection(
            items=["No devices found"],
            on_change=self.on_device_selected,
            style=Pack(padding=5, flex=1, width=400)
        )
        
        scan_row = toga.Box(style=Pack(direction=ROW, padding=5))
        scan_row.add(scan_button)
        scan_row.add(self.device_selection)
        
        # Address configuration section - full width for readability
        address_label = toga.Label(
            "Bluetooth Device Address:",
            style=Pack(padding=(10, 5, 5, 5), font_weight="bold")
        )
        
        self.bt_address_input = toga.TextInput(
            value=self.bt_address or "",
            placeholder="Enter Bluetooth MAC address (e.g., AA:BB:CC:DD:EE:FF)",
            style=Pack(padding=5, flex=1, width=400)
        )

        stroke_axis_label = toga.Label(
            "Stroke Axis:",
            style=Pack(padding=(10, 5, 5, 5), font_weight="bold")
        )

        self.stroke_axis_selection = toga.Selection(
            items=["X-axis", "Y-axis", "Z-axis"],
            on_change=self.on_stroke_axis_changed,
            style=Pack(padding=5, width=160)
        )
        self.stroke_axis_selection.value = self._stroke_axis_label(self.stroke_axis)

        stroke_direction_label = toga.Label(
            "Direction:",
            style=Pack(padding=(10, 5, 5, 5), font_weight="bold")
        )

        self.stroke_direction_selection = toga.Selection(
            items=["+", "-"],
            on_change=self.on_stroke_direction_changed,
            style=Pack(padding=5, width=80)
        )
        self.stroke_direction_selection.value = "+" if self.stroke_direction >= 0 else "-"

        stroke_axis_row = toga.Box(style=Pack(direction=ROW, padding=5))
        stroke_axis_row.add(stroke_axis_label)
        stroke_axis_row.add(self.stroke_axis_selection)
        stroke_axis_row.add(stroke_direction_label)
        stroke_axis_row.add(self.stroke_direction_selection)
        
        save_button = toga.Button(
            "Save Address", 
            on_press=self.save_bt_address, 
            style=Pack(padding=5, width=120)
        )
        
        # Full-width input with button on the right
        address_input_row = toga.Box(style=Pack(direction=ROW, padding=5))
        address_input_row.add(self.bt_address_input)
        address_input_row.add(save_button)
        
        # Status display
        status_box = toga.Box(style=Pack(direction=ROW, padding=5))
        status_box.add(self.status_label)
        
        # Connection controls section
        control_section = toga.Box(style=Pack(direction=COLUMN, padding=10))
        
        control_title = toga.Label(
            "Connection Controls",
            style=Pack(padding=5, font_size=14, font_weight="bold")
        )
        
        connect_button = toga.Button("Connect", on_press=self.connect_live, style=Pack(padding=5, flex=1))
        stop_button = toga.Button("Stop", on_press=self.stop_live, style=Pack(padding=5, flex=1))
        
        control_section.add(control_title)
        control_section.add(connect_button)
        control_section.add(stop_button)
        
        # Combine everything vertically for better readability
        page_box = toga.Box(style=Pack(direction=COLUMN, flex=1, padding=10))
        page_box.add(title_label)
        page_box.add(scan_label)
        page_box.add(scan_row)
        page_box.add(address_label)
        page_box.add(address_input_row)
        page_box.add(stroke_axis_row)
        page_box.add(status_box)
        page_box.add(control_section)
        
        return page_box
    
    def _load_bt_address(self):
        """Load Bluetooth address from config file."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r") as f:
                    return f.read().strip()
        except Exception as e:
            print(f"Error loading Bluetooth address: {e}")
        return None

    def _load_stroke_axis(self):
        """Load stroke axis from config file."""
        try:
            if os.path.exists(self.stroke_axis_config_path):
                with open(self.stroke_axis_config_path, "r") as f:
                    value = f.read().strip().lower()
                    if value in ('x', 'y', 'z'):
                        return value
        except Exception as e:
            print(f"Error loading stroke axis: {e}")
        return 'y'

    def _load_stroke_direction(self):
        """Load stroke direction from config file."""
        try:
            if os.path.exists(self.stroke_direction_config_path):
                with open(self.stroke_direction_config_path, "r") as f:
                    value = f.read().strip()
                    return 1 if value == '+' else -1
        except Exception as e:
            print(f"Error loading stroke direction: {e}")
        return 1

    def _stroke_axis_label(self, axis):
        normalized = (axis or '').strip().lower()
        if normalized == 'x':
            return 'X-axis'
        if normalized == 'z':
            return 'Z-axis'
        return 'Y-axis'

    def _stroke_axis_from_label(self, label):
        if label == 'X-axis':
            return 'x'
        if label == 'Z-axis':
            return 'z'
        return 'y'

    def on_stroke_axis_changed(self, widget):
        """Apply and persist stroke axis setting."""
        selected_label = self.stroke_axis_selection.value
        selected_axis = self._stroke_axis_from_label(selected_label)
        self.stroke_axis = selected_axis
        bkfb.set_stroke_axis(selected_axis)

        try:
            os.makedirs(os.path.dirname(self.stroke_axis_config_path), exist_ok=True)
            with open(self.stroke_axis_config_path, "w") as f:
                f.write(selected_axis)
            self.status_label.text = f"Stroke axis set: {selected_axis.upper()}"
        except Exception as e:
            self.status_label.text = f"Error saving stroke axis: {e}"

    def on_stroke_direction_changed(self, widget):
        """Apply and persist stroke direction setting."""
        selected = self.stroke_direction_selection.value
        direction = 1 if selected == '+' else -1
        self.stroke_direction = direction
        bkfb.set_stroke_direction(direction)

        try:
            os.makedirs(os.path.dirname(self.stroke_direction_config_path), exist_ok=True)
            with open(self.stroke_direction_config_path, "w") as f:
                f.write(selected)
            self.status_label.text = f"Stroke direction set: {selected}"
        except Exception as e:
            self.status_label.text = f"Error saving stroke direction: {e}"
    
    async def scan_devices(self, widget):
        """Scan for nearby BLE devices."""
        if self.scanning:
            return
        
        self.scanning = True
        self.status_label.text = "Scanning for devices..."
        self.discovered_devices = {}
        
        try:
            if self.is_mobile:
                # Use bleekWare scanner on Android/iOS
                from bkfbmobile.bleekWare.Scanner import Scanner
                
                scanner = Scanner()
                await scanner.start()
                await asyncio.sleep(5)  # Scan for 5 seconds
                await scanner.stop()
                
                devices = scanner.discovered_devices
                for device in devices:
                    name = device.name or "Unknown"
                    addr = device.address
                    self.discovered_devices[f"{name} ({addr})"] = addr
            else:
                # Use bleak scanner on desktop
                try:
                    from bleak import BleakScanner
                    
                    devices = await BleakScanner.discover(timeout=5.0)
                    for device in devices:
                        name = device.name or "Unknown"
                        addr = device.address
                        self.discovered_devices[f"{name} ({addr})"] = addr
                except ImportError:
                    self.status_label.text = "Error: BLE scanning not available on this platform"
                    self.scanning = False
                    return
            
            if self.discovered_devices:
                # Update selection widget
                self.device_selection.items = list(self.discovered_devices.keys())
                self.status_label.text = f"Found {len(self.discovered_devices)} device(s)"
            else:
                self.device_selection.items = ["No devices found"]
                self.status_label.text = "No BLE devices found"
                
        except Exception as e:
            self.status_label.text = f"Scan error: {e}"
            print(f"Scan error: {e}")
        finally:
            self.scanning = False
    
    def on_device_selected(self, widget):
        """Handle device selection from dropdown."""
        selected = self.device_selection.value
        if selected and selected in self.discovered_devices:
            address = self.discovered_devices[selected]
            self.bt_address_input.value = address
            self.status_label.text = f"Selected: {selected}"
    
    async def save_bt_address(self, widget):
        """Save Bluetooth address to config file."""
        address = self.bt_address_input.value.strip()
        if not address:
            self.status_label.text = "Error: Address cannot be empty"
            return
        
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            
            # Write address to config file
            with open(self.config_path, "w") as f:
                f.write(address)
            
            # Update the module-level variable in bkfb
            bkfb.ESP32_ADDR = address
            self.bt_address = address
            
            self.status_label.text = f"Address saved: {address}"
        except Exception as e:
            self.status_label.text = f"Error saving address: {e}"

    async def connect_live(self, widget):
        if self.stream_task and not self.stream_task.done():
            return
        
        # Update the address from the input field before connecting
        address = self.bt_address_input.value.strip()
        if not address:
            self.status_label.text = "Error: Please enter a Bluetooth address"
            return
        
        # Update the module-level variable in bkfb
        bkfb.ESP32_ADDR = address
        bkfb.set_stroke_axis(self.stroke_axis)

        self.status_label.text = "Connecting..."
        self.stop_event = asyncio.Event()

        async def on_update(plot_png, avg_png, compare_png):
            if plot_png:
                self.live_plot_view.image = toga.Image(src=plot_png)
            if avg_png:
                self.avg_plot_view.image = toga.Image(src=avg_png)
            if compare_png:
                self.compare_plot_view.image = toga.Image(src=compare_png)

        async def on_status(status):
            self.status_label.text = status

        async def runner():
            try:
                await bkfb.connect_live_in_app(
                    on_update,
                    stop_event=self.stop_event,
                    on_status=on_status,
                )
                self.status_label.text = "Idle"
            except Exception as e:
                error_msg = f"Connection error: {e}"
                print(error_msg)
                self.status_label.text = error_msg
            finally:
                self.stream_task = None

        self.stream_task = asyncio.create_task(runner())

    async def stop_live(self, widget):
        if self.stop_event:
            self.stop_event.set()
        if self.stream_task:
            await self.stream_task
            self.stream_task = None
        self.status_label.text = "Stopped"

    async def clear_plots(self, widget):
        plot_png, avg_png, compare_png = bkfb.clear_in_app_plots()
        if plot_png:
            self.live_plot_view.image = toga.Image(src=plot_png)
        if avg_png:
            self.avg_plot_view.image = toga.Image(src=avg_png)
        else:
            self.avg_plot_view.image = None
        if compare_png:
            self.compare_plot_view.image = toga.Image(src=compare_png)
        else:
            self.compare_plot_view.image = None

    def on_exit(self):
        # Ensure BLE stream is asked to stop, then force-kill any lingering worker.
        if self.stop_event:
            self.stop_event.set()
        if self.stream_task and not self.stream_task.done():
            self.stream_task.cancel()
        bkfb.force_stop_worker_sync()
        return True


def main():
    return BeeWareProject()
