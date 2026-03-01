"""
Multi-page app with Live Feed, Average Stroke, and Bluetooth Config screens.
"""

import asyncio
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from bkfbmobile import bkfb


class BeeWareProject(toga.App):
    def startup(self):
        self.stream_task = None
        self.stop_event = None

        # Shared image views that will be updated by BLE stream
        self.live_plot_view = toga.ImageView(style=Pack(flex=1, padding=10))
        self.avg_plot_view = toga.ImageView(style=Pack(flex=1, padding=10))
        self.status_label = toga.Label("Idle", style=Pack(margin=5))

        # Create the three pages
        live_feed_page = self._create_live_feed_page()
        avg_stroke_page = self._create_avg_stroke_page()
        config_page = self._create_config_page()

        # Create tab container
        container = toga.OptionContainer(
            content=[
                ("Live Feed", live_feed_page),
                ("Average Stroke", avg_stroke_page),
                ("Bluetooth Config", config_page),
            ],
            style=Pack(flex=1)
        )

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = container
        self.main_window.show()

    def _create_live_feed_page(self):
        """Create the live feed page with real-time plot and clear button."""
        clear_button = toga.Button("Clear", on_press=self.clear_plots, style=Pack(padding=5))
        
        controls = toga.Box(style=Pack(direction=ROW, padding=5))
        controls.add(clear_button)
        
        page_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
        page_box.add(controls)
        page_box.add(self.live_plot_view)
        
        return page_box

    def _create_avg_stroke_page(self):
        """Create the average stroke analysis page."""
        info_label = toga.Label(
            "Average stroke analysis appears here after collecting data",
            style=Pack(padding=10, text_align="center")
        )
        
        page_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
        page_box.add(info_label)
        page_box.add(self.avg_plot_view)
        
        return page_box

    def _create_config_page(self):
        """Create the bluetooth configuration page (placeholder)."""
        title_label = toga.Label(
            "Bluetooth Configuration",
            style=Pack(padding=10, font_size=16, font_weight="bold")
        )
        
        connect_button = toga.Button("Connect", on_press=self.connect_live, style=Pack(padding=5, flex=1))
        stop_button = toga.Button("Stop", on_press=self.stop_live, style=Pack(padding=5, flex=1))
        
        controls = toga.Box(style=Pack(direction=ROW, padding=10))
        controls.add(connect_button)
        controls.add(stop_button)
        
        page_box = toga.Box(style=Pack(direction=COLUMN, flex=1, padding=10))
        page_box.add(title_label)
        page_box.add(self.status_label)
        page_box.add(controls)
        
        # Placeholder content
        placeholder = toga.Label(
            "Bluetooth settings and device configuration coming soon...",
            style=Pack(padding=20, text_align="center")
        )
        page_box.add(placeholder)
        
        return page_box

    async def connect_live(self, widget):
        if self.stream_task and not self.stream_task.done():
            return

        self.status_label.text = "Connecting..."
        self.stop_event = asyncio.Event()

        async def on_update(plot_png, avg_png):
            if plot_png:
                self.live_plot_view.image = toga.Image(src=plot_png)
            if avg_png:
                self.avg_plot_view.image = toga.Image(src=avg_png)

        async def on_status(status):
            self.status_label.text = status

        async def runner():
            await bkfb.connect_live_in_app(
                on_update,
                stop_event=self.stop_event,
                on_status=on_status,
            )
            self.status_label.text = "Idle"
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
        plot_png, avg_png = bkfb.clear_in_app_plots()
        if plot_png:
            self.live_plot_view.image = toga.Image(src=plot_png)
        if avg_png:
            self.avg_plot_view.image = toga.Image(src=avg_png)
        else:
            self.avg_plot_view.image = None


def main():
    return BeeWareProject()
