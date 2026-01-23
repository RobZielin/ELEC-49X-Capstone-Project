"""
Embed the main_demo plots inside the BeeWare Toga window.
"""

import asyncio
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from beewareproject import main_demo


class BeeWareProject(toga.App):
    def startup(self):
        self.replay_task = None
        self.stop_event = None

        self.plot_view = toga.ImageView(style=Pack(flex=1, height=260, margin=(5, 5, 2, 5)))
        self.avg_view = toga.ImageView(style=Pack(flex=1, height=260, margin=(2, 5, 5, 5)))
        self.status_label = toga.Label("Idle", style=Pack(margin=5))

        start_button = toga.Button("Start replay", on_press=self.start_replay, style=Pack(margin_right=5))
        stop_button = toga.Button("Stop", on_press=self.stop_replay)

        controls = toga.Box(style=Pack(direction=ROW, margin=5))
        controls.add(start_button)
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

    async def start_replay(self, widget):
        if self.replay_task and not self.replay_task.done():
            return

        self.status_label.text = "Running replay..."
        self.stop_event = asyncio.Event()

        async def on_update(plot_png, avg_png):
            if plot_png:
                self.plot_view.image = toga.Image(data=plot_png)
            if avg_png:
                self.avg_view.image = toga.Image(data=avg_png)

        async def runner():
            await main_demo.replay_in_app(on_update, stop_event=self.stop_event)
            self.status_label.text = "Idle"
            self.replay_task = None

        self.replay_task = asyncio.create_task(runner())

    async def stop_replay(self, widget):
        if self.stop_event:
            self.stop_event.set()
        if self.replay_task:
            await self.replay_task
            self.replay_task = None
        self.status_label.text = "Stopped"


def main():
    return BeeWareProject()
