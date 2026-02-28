"""
Embed the main_demo plots inside the BeeWare Toga window.
"""

import asyncio
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from bkfbmobile import main_demo


class BeeWareProject(toga.App):
    def startup(self):
        self.stream_task = None
        self.stop_event = None

        self.plot_view = toga.ImageView(style=Pack(flex=1, height=260, margin=(5, 5, 2, 5)))
        self.avg_view = toga.ImageView(style=Pack(flex=1, height=260, margin=(2, 5, 5, 5)))
        self.status_label = toga.Label("Idle", style=Pack(margin=5))

        connect_button = toga.Button("Connect", on_press=self.connect_live, style=Pack(margin_right=5))
        clear_button = toga.Button("Clear", on_press=self.clear_plots, style=Pack(margin_right=5))
        stop_button = toga.Button("Stop", on_press=self.stop_live)

        controls = toga.Box(style=Pack(direction=ROW, margin=5))
        controls.add(connect_button)
        controls.add(clear_button)
        controls.add(stop_button)

        images = toga.Box(style=Pack(direction=COLUMN, flex=1))
        images.add(self.plot_view)
        images.add(self.avg_view)

        main_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
        main_box.add(controls)
        main_box.add(self.status_label)
        main_box.add(images)

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = main_box
        self.main_window.show()

    async def connect_live(self, widget):
        if self.stream_task and not self.stream_task.done():
            return

        self.status_label.text = "Connecting..."
        self.stop_event = asyncio.Event()

        async def on_update(plot_png, avg_png):
            if plot_png:
                self.plot_view.image = toga.Image(data=plot_png)
            if avg_png:
                self.avg_view.image = toga.Image(data=avg_png)

        async def on_status(status):
            self.status_label.text = status

        async def runner():
            await main_demo.connect_live_in_app(
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
        plot_png, avg_png = main_demo.clear_in_app_plots()
        if plot_png:
            self.plot_view.image = toga.Image(data=plot_png)
        if avg_png:
            self.avg_view.image = toga.Image(data=avg_png)
        else:
            self.avg_view.image = None


def main():
    return BeeWareProject()
