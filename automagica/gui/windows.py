"""Copyright 2020 Oakwood Technologies BVBA"""

import base64
import json
import os
import tkinter as tk
from io import BytesIO
from time import sleep
from tkinter import font, ttk

from automagica.httpclient import http_client
from PIL import Image, ImageTk

from automagica import config
from automagica.bots import ThreadedBot
from automagica.config import _
from automagica.flow import Flow
from automagica.gui.buttons import Button, HelpButton, LargeButton
from automagica.gui.frames import (
    ConsoleFrame,
    FlowFrame,
    LabelFrame,
    SidebarFrame,
    ToolbarFrame,
)
from automagica.gui.inputs import (
    AutocompleteDropdown,
    AutomagicaIdInputWidget,
    BooleanInputWidget,
    DirWidget,
    FilePathInputWidget,
    FilePathOutputWidget,
    InputField,
    InputWidget,
    KeycombinationEntry,
    NodeSelectionInputWidget,
    TextInputWidget,
)
from automagica.keybinds import Keybind, KeybindsManager
from automagica.nodes import LoopNode, SubFlowNode

# Keep track of currently visible notifications (so they can stack)
AUTOMAGICA_NUMBER_OF_NOTIFICATIONS = 0

# Keep track of currently visible player windows (so they can stack)
AUTOMAGICA_NUMBER_OF_PLAYER_WINDOWS = 0


class Window(tk.Toplevel):
    """
    General Window class based on tkinter's TopLevel class
    """

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.parent = parent

        # Set background color
        self.configure(bg=config.COLOR_4)

        self.icon_path = os.path.join(
            os.path.abspath(__file__).replace(
                os.path.basename(os.path.realpath(__file__)), ""
            ),
            "icons",
            "automagica.ico",
        )

        # Set Title Bar Icon on Windows
        if "nt" in os.name:
            self.iconbitmap(self.icon_path)

    def center(self, w=None, h=None):
        """
        Center a tkinter.Window on the screen
        """
        # Required, update to get the height/width properties correctly
        self.update()

        # Hide window
        self.withdraw()

        if not w:
            w = self.winfo_width()

        if not h:
            h = self.winfo_height()

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        x = int((sw / 2) - (w / 2))
        y = int((sh / 2) - (h / 2))

        # Adjust window geometry (positioning)
        self.geometry("{}x{}+{}+{}".format(w, h, x, y))

        # Update the window
        self.update()

        # Show the window
        self.deiconify()


class FlowDesignerWindow(Window):
    """
    The Flow Designer window is the main window for Automagica Flow
    """

    def __init__(
        self, parent, *args, flow=None, bot=None, autosave=True, **kwargs
    ):
        """
        Initialize the main window
        """
        super().__init__(parent, *args, **kwargs)

        self.flow = flow
        self.bot = bot

        # If no Bot provided, initialize one
        if not self.bot:
            self.bot = ThreadedBot()

        # If no Flow provided, initialize one
        if not self.flow:
            self.flow = Flow()

        self._configure_window()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.state("normal")

        self.autosave = autosave

        self.save_buffer = []
        self.last_state = self.flow.to_dict()
        self.save_buffer.append(self.last_state)

        self.bind("<Control-z>", self.undo)

        if self.autosave:
            self._autosave_cycle()

        self._layout()
        self.center(w=1300, h=720)

    def _autosave_cycle(self):
        """
        Take care of auto saving if applicable
        """

        # Check if the Flow's state has changed since last time
        if self.flow.to_dict() != self.last_state:
            self.last_state = self.flow.to_dict()

            # Add it to the buffer
            self.save_buffer.append(self.last_state)

            # If a file path is set, save the Flow
            if self.flow.file_path:
                self.flow.save(self.flow.file_path)

        self.after(100, self._autosave_cycle)

    def undo(self, event):
        """
        Take one step back in the buffer
        """
        # Remove last state
        self.save_buffer.pop(-1)

        # Set the last state to the last item in the save buffer
        self.last_state = self.save_buffer[-1]

        # Set to last known state
        self.flow.from_dict(self.last_state)

        # Redraw
        self.flow_frame.draw()

    def on_closing(self):
        """
        Override what happens when this window gets closed
        """
        if not self.flow.file_path:
            from tkinter import messagebox

            answer = messagebox.showwarning(
                _("Unsaved Flow"),
                _("Close without saving?"),
                master=self,
                type=messagebox.YESNO,
            )

            if answer != "yes":
                return

        self.destroy()

        if not self.master.winfo_children():
            # Close root application if no open windows
            self.master.close_app()

    def _layout(self):
        """
        Layout the window
        """
        fixed_frame = tk.Frame(self, height=150, bg=config.COLOR_0)
        fixed_frame.pack(fill="x")

        fluid_frame = tk.Frame(self)
        fluid_frame.pack(fill="both", expand=True)

        # Toolbar
        self.toolbar_frame = ToolbarFrame(fixed_frame)
        self.toolbar_frame.pack(side="left")

        # Sidebar
        self.sidebar_frame = SidebarFrame(fluid_frame)
        self.sidebar_frame.place(relx=0, rely=0, relwidth=0.165, relheight=1)

        # Flow Area
        self.flow_frame = FlowFrame(fluid_frame, self.flow)
        self.flow_frame.place(
            relx=0.165, rely=0, relwidth=0.835, relheight=0.7
        )

        # Console
        self.console_frame = ConsoleFrame(fluid_frame, bot=self.bot)
        self.console_frame.place(
            relx=0.165, rely=0.7, relwidth=0.835, relheight=0.3
        )

    def _configure_window(self):
        """
        Window configuration
        """
        if self.flow.file_path:
            self.title("{} - Automagica Flow".format(self.flow.file_path))
        else:
            self.title(_("Unsaved Flow") + " - Automagica Flow")

        self.option_add("*Background", config.COLOR_1)
        self.configure(bg=config.COLOR_1)
        self.grid_columnconfigure(0, weight=1)

    @property
    def suggested_previous_node(self):
        """
        Retrieve the suggested previous node
        """
        if self.flow_frame.selection:
            for graph in self.flow_frame.selection[::-1]:
                if not graph.node.next_node:
                    return graph.node

        return None

    def add_activity(self, activity, args_=None):
        """
        Add an activity
        """
        previous_node = self.suggested_previous_node

        node = self.flow.add_activity_node(
            activity, previous_node=previous_node, args_=args_
        )

        if not previous_node:
            node.x = (
                int(self.flow_frame.canvas.winfo_width() / 2)
                + self.flow_frame.canvas.canvasx(0)
                - int(125 / 2)
            )
            node.y = (
                int(self.flow_frame.canvas.winfo_height() / 2)
                + self.flow_frame.canvas.canvasy(0)
                - int(75 / 2)
            )

        graph = self.flow_frame.add_node_graph(node)
        graph.select()

    def add_node(self, node_type):
        """
        Add a node
        """
        node = self.flow.add_node(node_type)
        self.flow_frame.add_node_graph(node)
        return node


class FlowPlayerWindow(tk.Toplevel):
    """
    The main Flow Player Window
    """

    def __init__(
        self,
        *args,
        flow=None,
        bot=None,
        autoplay=False,
        step_by_step=False,
        on_close=None,
        autoclose=None,
        start_node=None,
        title=None,
        **kwargs,
    ):
        """
        Initialize Flow Player Window
        """
        global AUTOMAGICA_NUMBER_OF_PLAYER_WINDOWS

        super().__init__(*args, **kwargs)

        self._configure_window()

        self.protocol("WM_DELETE_WINDOW", self.on_close_window)
        self.state("normal")

        self.flow = flow
        self.bot = bot
        self.on_close = on_close
        self.autoclose = autoclose
        self.title = title
        self.errors = False

        if not self.title:
            self.title = flow.name

        self.paused = True
        self.step_by_step = step_by_step

        if start_node:
            self.current_node = self.flow.get_node_by_uid(start_node)
        else:
            self.current_node = self.flow.get_start_nodes()[0]

        self.total_nodes = len(flow.nodes)
        self.n_nodes_ran = 0

        self.progress_frame = self.create_progress_frame()
        self.progress_frame.pack(padx=5, pady=5, expand=True, fill="x")

        self.buttons_frame = self.create_buttons_frame()
        self.buttons_frame.pack(padx=5, pady=5)

        self.autoplay = autoplay

        if autoplay:
            self.paused = False
            self.on_play_click()

        self.overrideredirect(True)

        AUTOMAGICA_NUMBER_OF_PLAYER_WINDOWS += 1

    def on_close_window(self):
        """
        Override closing behaviour
        """
        global AUTOMAGICA_NUMBER_OF_PLAYER_WINDOWS

        AUTOMAGICA_NUMBER_OF_PLAYER_WINDOWS -= 1

        self.destroy()

        if not self.master.winfo_children():
            # Close root application if no open windows
            if self.errors:
                self.master.close_app(exit_code=1)
            else:
                self.master.close_app(exit_code=0)

    def update(self):
        """
        Update contents of the window, runs after every node
        """
        self.n_nodes_ran += 1

        self.progress_bar["value"] = int(
            self.n_nodes_ran / self.total_nodes * 100
        )

        self.current_node_label.configure(
            text=_("Current step: {}").format(self.current_node)
        )

        if self.current_node:
            if self.current_node.next_node:
                self.next_node_label.configure(
                    text=_("Next step: {}").format(
                        self.flow.get_node_by_uid(self.current_node.next_node)
                    )
                )
            else:
                self.next_node_label.configure(text="")

    def create_progress_frame(self):
        """
        Create the progress frame
        """
        frame = tk.Frame(self)

        frame.configure(bg=self.cget("bg"))

        self.flow_label = tk.Label(
            frame, text=self.title, bg=self.cget("bg"), font=(config.FONT, 10)
        )
        self.flow_label.pack()

        self.progress_bar = ttk.Progressbar(
            frame, orient=tk.HORIZONTAL, length=100, mode="determinate"
        )
        self.progress_bar.pack(fill="both", expand=True)

        self.current_node_label = tk.Label(
            frame,
            text=_("No current activity"),
            fg=config.COLOR_11,
            bg=self.cget("bg"),
            font=(config.FONT, 10),
        )
        self.current_node_label.pack()

        self.next_node_label = tk.Label(
            frame,
            text=_("Next step: {}").format(
                self.flow.get_node_by_uid(self.current_node.next_node)
            ),
            fg=config.COLOR_11,
            bg=self.cget("bg"),
            font=(config.FONT, 10),
        )
        self.next_node_label.pack()

        return frame

    def create_buttons_frame(self):
        """
        Create the buttons frame
        """
        frame = tk.Frame(self)

        frame.configure(bg=self.cget("bg"))

        self.play_pause_button = Button(
            frame,
            text=_("Play"),
            command=self.on_play_click,
            bg=config.COLOR_7,
        )
        self.play_pause_button.pack(side="left", padx=5, pady=5)

        self.stop_button = Button(
            frame,
            text=_("Stop"),
            bg=config.COLOR_6,
            command=self.on_stop_click,
        )
        self.stop_button.pack(side="left", padx=5, pady=5)

        return frame

    def on_pause_click(self):
        """
        When 'pause' is clicked
        """
        self.play_pause_button.configure(
            text=_("Play"), command=self.on_play_click, bg=config.COLOR_7
        )
        self.paused = True

    def on_play_click(self):
        """
        When 'play' is clicked
        """
        self.play_pause_button.configure(
            text=_("Pause"), command=self.on_pause_click, bg=config.COLOR_0
        )

        self.paused = False
        self.play()

    def on_restart_click(self):
        """
        When 'restart' is clicked
        """
        self.current_node = self.flow.get_start_nodes()[0]
        self.n_nodes_ran = 0
        self.update()
        self.play_pause_button.configure(
            text=_("Play"), command=self.on_play_click, bg=config.COLOR_7
        )

    def play(self, loop=False, node=""):
        """
        Main play loop
        """
        # Pause the flow if mouse is topleft corner
        try:
            mouse_x = self.winfo_pointerx()
            mouse_y = self.winfo_pointery()
        except:  # If flow is stopped by user before this is called back, exception occurs
            return

        if mouse_x == 0 and mouse_y == 0:
            self.on_pause_click()

        # If a specific node is specified with the play function
        if node == "":
            # Regular play
            pass

        elif node is None:
            # Play called with None-node
            self.current_node = None

            if self.autoclose:
                self.after(100, self.on_stop_click)

            self.progress_bar["value"] = 100

            self.play_pause_button.configure(
                text=_("Restart"),
                command=self.on_restart_click,
                bg=config.COLOR_7,
            )

        elif node is not None or node != "":
            # We actually got a next node
            self.current_node = self.flow.get_node_by_uid(node)

        if self.current_node:
            if not self.paused:
                self.update()

                if self.step_by_step:
                    self.on_pause_click()

                if isinstance(self.current_node, SubFlowNode):
                    FlowPlayerWindow(
                        self,
                        flow=Flow(
                            self.current_node.subflow_path.replace('"', "")
                        ),
                        bot=self.bot,
                        autoplay=self.autoplay,
                        step_by_step=self.step_by_step,
                        on_close=lambda: self.play(
                            node=self.current_node.next_node
                        ),
                        autoclose=True,
                    )

                elif isinstance(self.current_node, LoopNode):
                    # Are we iterating?
                    if not self.bot.interpreter.locals.get(
                        "AUTOMAGICA_ITERABLE"
                    ):
                        # Set Iterable variable
                        self.bot._run_command(
                            f"AUTOMAGICA_ITERABLE = iter({self.current_node.iterable})"
                        )

                    # Set 'next' in iterable
                    self.bot._run_command(
                        f"try:\n\t{self.current_node.loop_variable} = next(AUTOMAGICA_ITERABLE)\nexcept StopIteration:\n\t{self.current_node.loop_variable} = None\n\tAUTOMAGICA_ITERABLE = None"
                    )

                    if (
                        self.bot.interpreter.locals.get(
                            self.current_node.loop_variable
                        )
                        is not None
                    ):
                        FlowPlayerWindow(
                            self,
                            flow=self.flow,
                            start_node=self.current_node.loop_node,
                            bot=self.bot,
                            autoplay=self.autoplay,
                            step_by_step=self.step_by_step,
                            on_close=self.play,
                            autoclose=True,
                            title=str(self.current_node.label),
                        )

                    else:
                        self.play(node=self.current_node.next_node)

                else:
                    # Is an on exception node specified?
                    if hasattr(self.current_node, "on_exception_node"):
                        self.current_node.run(
                            self.bot,
                            on_done=self.play,
                            on_fail=lambda: self.play(
                                node=self.current_node.on_exception_node
                            ),
                        )
                    # No exception node specified, call the on_fail function (likely stopping the flow)
                    else:
                        self.current_node.run(
                            self.bot, on_done=self.play, on_fail=self.on_fail
                        )

    def on_fail(self):
        """
        What should happen when the Flow fails
        """
        self.errors = True
        self.on_stop_click()

    def on_stop_click(self):
        """
        When 'stop' is clicked
        """
        if self.on_close:
            self.on_close()

        self.on_close_window()

    def _configure_window(self):
        """
        Configure the window
        """
        self.title(_("Flow"))
        self.attributes("-alpha", 0.75)
        self.attributes("-topmost", True)

        self.screen_width = self.winfo_screenwidth()
        self.screen_height = self.winfo_screenheight()

        self.geometry("300x140")
        self.geometry(
            "-50-{}".format(
                (10 + 140) * AUTOMAGICA_NUMBER_OF_PLAYER_WINDOWS + 50
            )
        )

        self.resizable(False, False)


class FlowValidationWindow(Window):
    """
    Flow validation window
    """

    def __init__(self, parent, flow, *args, **kwargs):
        """
        Create Flow validation window
        """
        super().__init__(parent, *args, **kwargs)
        self.flow = flow

        self._layout()
        self._configure_window()

        self.center()

    def _configure_window(self):
        """
        Configure the Flow validation window
        """
        self.title(_("Flow Validation"))

    def _layout(self):
        """
        Window layout
        """
        self.validation_errors_frame = self.create_validation_errors_frame()
        self.validation_errors_frame.pack()

    def create_validation_errors_frame(self):
        """
        Create validation errors frame
        """
        frame = tk.Frame(self)

        self.validation_errors_list = tk.Listbox(frame, width=100)
        self.validation_errors_list.pack()

        errors = self.flow.validate()

        for error in errors:
            self.validation_errors_list.insert(tk.END, str(error))

        if not errors:
            self.validation_errors_list.insert(
                tk.END, _("There are no validation errors for this Flow.")
            )

        return frame


class NotificationWindow(tk.Toplevel):
    """
    The notification window is a small notification window in
    the corner of the screen, which fades out when disappearing.
    """

    def __init__(
        self, parent, message, *args, duration=1, title="Automagica", **kwargs
    ):
        """
        Create notification window
        """
        super().__init__(parent, *args, **kwargs)
        global AUTOMAGICA_NUMBER_OF_NOTIFICATIONS

        AUTOMAGICA_NUMBER_OF_NOTIFICATIONS += 1

        self.parent = parent
        self.duration = duration
        self.title = title
        self.alpha = 1

        self._configure()
        self._binds()

        self.message = message

        icon_path = os.path.join(
            os.path.abspath(__file__).replace(
                os.path.basename(os.path.realpath(__file__)), ""
            ),
            "icons",
            "trayicon.png",
        )

        self.image_frame = self.create_image_frame(icon_path)
        self.image_frame.pack(side="left", fill="y", padx=0, pady=0)

        self.text_frame = self.create_text_frame()
        self.text_frame.pack(side="left", expand=True, fill="both")

        self.animate()

    def animate(self):
        """
        Animation loop
        """
        self.after(self.duration * 1000, self.fade)

    def fade(self):
        """
        Fade animation
        """
        global AUTOMAGICA_NUMBER_OF_NOTIFICATIONS

        self.alpha -= 0.05
        self.attributes("-alpha", self.alpha)

        if self.alpha > 0:
            self.after(50, self.fade)
        else:
            AUTOMAGICA_NUMBER_OF_NOTIFICATIONS -= 1
            self.destroy()

    def create_text_frame(self):
        """
        Create text frame
        """
        frame = tk.Frame(self, bg=config.COLOR_0)

        self.title_label = tk.Label(
            frame,
            fg=config.COLOR_1,
            bg=config.COLOR_0,
            text=self.title,
            font=(config.FONT, 10),
            width=20,
            justify="left",
            anchor="w",
            wraplength=150,
        )
        self.title_label.pack(expand=True, fill="both")

        self.text_label = tk.Label(
            frame,
            fg=config.COLOR_1,
            bg=config.COLOR_0,
            text=self.message,
            font=(config.FONT, 10),
            width=20,
            justify="left",
            anchor="nw",
            wraplength=150,
        )
        self.text_label.pack(expand=True, fill="both")

        return frame

    def _configure(self):
        """
        Configure window
        """
        global AUTOMAGICA_NUMBER_OF_NOTIFICATIONS

        # self.wm_attributes("-topmost", True)
        # self.attributes("-alpha", 1)
        self.attributes("-topmost", True)

        self.screen_width = self.winfo_screenwidth()
        self.screen_height = self.winfo_screenheight()

        self._place_window(
            self.screen_width - 300,
            self.screen_height
            - 100 * (AUTOMAGICA_NUMBER_OF_NOTIFICATIONS + 1)
            - 30,
        )

        self.overrideredirect(True)

    def _binds(self):
        """
        Configure binds
        """
        self.bind("<ButtonPress-1>", self.mouse_down)
        self.bind("<Double-Button-1>", self.mouse_double_click)

    def create_image_frame(self, file_path):
        """
        Create image frame
        """
        frame = tk.Frame(self, bd=0, bg=config.COLOR_0)

        self.img_pil = Image.open(file_path)
        self.img_pil = self.img_pil.resize((64, 64))
        self.img = ImageTk.PhotoImage(self.img_pil)

        self.label = tk.Label(frame, image=self.img, bd=0)
        self.label.pack(padx=10, pady=10)

        return frame

    def mouse_double_click(self, event):
        """
        Double click on the notification window
        """
        print(event)

    def mouse_down(self, event):
        """
        When user clicks the notification, destroy it.
        """
        self.destroy()

    def _place_window(self, x, y):
        """
        Place the window
        """
        self.geometry("+{}+{}".format(x, y))
        self.x = x
        self.y = y


class BotTrayWindow(tk.Toplevel):
    """
    Tray icon for the bot
    """

    def __init__(self, *args, **kwargs):
        """
        Create the tray window icon
        """
        super().__init__(*args, **kwargs)
        self._configure()
        self._binds()

        icon_path = os.path.join(
            os.path.abspath(__file__).replace(
                os.path.basename(os.path.realpath(__file__)), ""
            ),
            "icons",
            "trayicon.png",
        )

        self.image_frame = self.create_image_frame(icon_path)
        self.image_frame.pack(expand=True, fill="both", padx=0, pady=0)

    def _configure(self):
        """
        Configure the window
        """
        self.attributes("-alpha", 0.5)
        self.attributes("-topmost", True)

        self.screen_width = self.winfo_screenwidth()
        self.screen_height = self.winfo_screenheight()

        self._place_window(self.screen_width - 80, self.screen_height - 80)

        self.overrideredirect(True)

    def _binds(self):
        """
        Configure the binds
        """
        self.bind("<ButtonPress-1>", self.mouse_down)
        self.bind("<Double-Button-1>", self.mouse_double_click)
        self.bind("<B1-Motion>", self.mouse_drag)

    def create_image_frame(self, file_path):
        """
        Create the image frame
        """
        frame = tk.Frame(self, bd=0)

        self.img_pil = Image.open(file_path)
        self.img_pil = self.img_pil.resize((40, 40))
        self.img = ImageTk.PhotoImage(self.img_pil)

        self.label = tk.Label(frame, image=self.img, bd=0)
        self.label.pack(padx=0, pady=0)

        self.popup_menu = tk.Menu(self, tearoff=0, font=(config.FONT, 10))
        self.popup_menu.add_command(
            label="Settings", command=self.settings_clicked
        )
        self.popup_menu.add_command(label="Quit", command=self.quit_clicked)

        self.bind("<Button-3>", self.popup)

        return frame

    def popup(self, event):
        """
        Show pop-up menu
        """
        try:
            self.popup_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.popup_menu.grab_release()

    def quit_clicked(self):
        """
        When the user clicks 'quit'
        """
        self.master.exit()

    def settings_clicked(self):
        """
        When the user clicks 'settings'
        """
        return ConfigWindow(self)

    def mouse_double_click(self, event):
        """
        When the user double clicks
        """
        pass

    def mouse_down(self, event):
        """
        On mouse down
        """
        self.mouse_x = event.x
        self.mouse_y = event.y

    def _place_window(self, x, y):
        """
        Place the window
        """
        self.geometry("+{}+{}".format(x, y))
        self.x = x
        self.y = y

    def mouse_drag(self, event):
        """
        On mouse drag, move the window
        """
        self.x = self.x + (event.x - self.mouse_x)
        self.y = self.y + (event.y - self.mouse_y)

        self.geometry("+{}+{}".format(self.x, self.y))

        self.mouse_x = event.x
        self.mouse_y = event.y


class WandWindow(Window):
    def __init__(
        self,
        parent,
        *args,
        action=None,
        standalone=False,
        delay=0,
        on_finish=None,
        **kwargs,
    ):
        """
        Main window for Wand
        """
        super().__init__(parent, *args, **kwargs)

        self.withdraw()

        self.config = config.Config()

        if not self.config.values.get("bot_secret"):
            from tkinter import messagebox

            yes = messagebox.askyesno(
                _("Automagica Wand"),
                _(
                    "To use Automagica Wand, please register on the \
                        Automagica Portal and set up your bot. \n\n\
                            Would you like to go to the Automagica Portal?"
                ),
                parent=self,
            )

            if yes:
                import webbrowser

                webbrowser.open(
                    os.environ.get(
                        "AUTOMAGICA_PORTAL_URL",
                        "https://portal.automagica.com",
                    )
                )

            else:
                self.destroy()

        else:
            self.action = action
            self.standalone = standalone
            self.on_finish = on_finish

            self.anchors = []
            self.anchor_images = []
            self.minimap_scale = 1

            self.withdraw()

            if delay:
                splash_window = tk.Toplevel(self)
                splash_window.overrideredirect(1)
                countdown_text = tk.Label(
                    splash_window,
                    text=f"Select element in {delay} seconds...",
                    font=(config.FONT, 20),
                    fg=config.COLOR_1,
                    bg=config.COLOR_0,
                )
                countdown_text.pack()
                splash_window.update()
                sleep(delay)
                splash_window.withdraw()

            sleep(0.5)  # Wait for animations to finish

            self.screenshot = self.capture_screenshot()

            self.select_target()

    def capture_screenshot(self):
        """
        Captures the screen to a Pillow Image object
        TODO: this does not work for xvfb-based systems
        """
        from PIL import Image
        import mss

        with mss.mss() as sct:

            # Find primary monitor
            for monitor in sct.monitors:
                if monitor["left"] == 0 and monitor["top"] == 0:
                    break

            sct_img = sct.grab(monitor)

        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        return img

    def select_target(self):
        """
        Select target on the screen
        """
        SnippingToolWindow(self, self.screenshot, self.set_target)

    def set_target(self, coordinates):
        """
        Set the target
        """
        self.target = coordinates
        self.create_layout()
        self.show()

    def show(self):
        """
        Show the window
        """
        self.update()
        self.deiconify()
        self.attributes("-topmost", True)

        try:
            self.grab_set()
        except:
            pass  # nosec

        # self.resizable(False, False)

    def add_anchor(self, coordinates):
        """
        Add an anchor based on coordinates
        """
        self.anchors.append(coordinates)
        self.show()

        image_cropped = self.screenshot.crop(coordinates)
        image_cropped, _ = self._resize_to_fit(image_cropped, 128, 128)

        anchor_frame = tk.Frame(
            self.anchors_frame,
            highlightbackground="green",
            highlightcolor="green",
            highlightthickness=4,
            bd=0,
        )
        anchor_frame.pack(side="left")

        image = ImageTk.PhotoImage(image_cropped)
        anchor_lbl = tk.Label(anchor_frame, image=image)
        anchor_lbl.pack()

        self.anchor_images.append(image)

        self.minimap_canvas.create_rectangle(
            int(coordinates[0] * self.minimap_scale),
            int(coordinates[1] * self.minimap_scale),
            int(coordinates[2] * self.minimap_scale),
            int(coordinates[3] * self.minimap_scale),
            outline="green",
            width=2,
        )

        if len(self.anchors) == 3:
            self.add_anchor_button.pack_forget()

        self.update()

    def create_layout(self):
        """
        Create the layout for the window
        """
        self.title(_("Automagica Wand"))

        # Minimap Frame
        self.minimap_frame = self.create_minimap_frame()
        self.minimap_frame.grid(
            row=0, column=0, columnspan=2, pady=10, padx=10
        )

        # Target Frame
        self.target_frame = self.create_target_frame()
        self.target_frame.grid(
            row=1, column=0, sticky="ewns", pady=10, padx=10
        )

        # Anchors Frame
        self.anchors_frame = self.create_anchors_frame()
        self.anchors_frame.grid(
            row=1, column=1, sticky="ewns", pady=10, padx=10
        )

        # Buttons Frame
        self.buttons_frame = self.create_buttons_frame()
        self.buttons_frame.grid(
            row=2, column=0, columnspan=2, pady=10, padx=10
        )

        # Keybinds
        self.bind("<Return>", self.enter_pressed)

    def enter_pressed(self, event):
        """
        When the user presses enter
        """
        self.save_clicked()

    def create_buttons_frame(self):
        """
        Create a buttons frame
        """
        frame = tk.Frame(self)

        frame.configure(bg=config.COLOR_4)

        save_btn = LargeButton(
            frame, text=_("Save"), command=self.save_clicked
        )
        save_btn.grid(row=0, column=1, sticky="e", padx=10, pady=10)

        return frame

    def create_minimap_frame(self):
        """
        Create the minimap frame
        """
        frame = LabelFrame(self, text=_("Screenshot"), bg=self.cget("bg"))

        screenshot_small, self.minimap_scale = self._resize_to_fit(
            self.screenshot, 192 * 4, 108 * 4
        )

        self.minimap_canvas = tk.Canvas(
            frame,
            width=screenshot_small.size[0],
            height=screenshot_small.size[1],
            bg=self.cget("bg"),
        )
        self.minimap_canvas.pack()

        self.minimap_image = ImageTk.PhotoImage(screenshot_small)

        self.minimap_canvas.create_image(
            (0, 0), image=self.minimap_image, anchor="nw"
        )

        self.minimap_canvas.create_rectangle(
            int(self.target[0] * self.minimap_scale),
            int(self.target[1] * self.minimap_scale),
            int(self.target[2] * self.minimap_scale),
            int(self.target[3] * self.minimap_scale),
            outline="red",
            width=2,
        )

        return frame

    def create_anchors_frame(self):
        """
        Create anchors frame
        """
        frame = LabelFrame(
            self, text=_("Anchors"), padx=10, pady=10, bg=self.cget("bg")
        )

        anchors_label = tk.Label(
            frame,
            text=_("Add anchors to make the element detection more reliable."),
            font=(config.FONT, 10),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
        )
        anchors_label.pack()

        self.add_anchor_button = Button(
            frame, text=_("Add anchor"), command=self.add_anchor_button_clicked
        )
        self.add_anchor_button.pack()

        return frame

    def create_target_frame(self):
        """
        Create the target frame
        """
        from automagica.config import _

        frame = LabelFrame(self, text=_("Target"), bg=self.cget("bg"))

        target_image, _ = self._resize_to_fit(
            self.screenshot.crop(self.target), 156, 156
        )
        self.target_img = ImageTk.PhotoImage(target_image)

        image_frame = tk.Frame(
            frame,
            highlightbackground="red",
            highlightcolor="red",
            highlightthickness=4,
            bd=0,
        )
        image_frame.pack()

        target_label = tk.Label(image_frame, image=self.target_img)
        target_label.pack()

        return frame

    def _resize_to_fit(self, image, fit_w, fit_h):
        """
        Resize the image to fit

        TODO: this should probably be a utility
              function rather than a window-specific method
        """
        w, h = image.size

        if w >= h:
            image = image.resize((fit_w, int(h / w * fit_w)))
            factor = fit_w / w
        else:
            image = image.resize(((int(w / h * fit_h), fit_h)))
            factor = fit_h / h

        return image, factor

    def add_anchor_button_clicked(self):
        """
        'Add anchor button' clicked by the user
        """
        self.withdraw()

        SnippingToolWindow(self, self.screenshot, self.add_anchor)

    def save(self):
        """
        Save the UI Element
        """
        self.grab_release()
        self.destroy()

        config_path = os.path.join(os.path.expanduser("~"), "automagica.json")

        def save_config(config):
            """
            Save the config

            TODO: implement the Config class here
            """
            with open(config_path, "w") as f:
                json.dump(config, f)

        try:
            with open(config_path, "r") as f:
                config = json.load(f)

        except FileNotFoundError:
            config = {}
            save_config(config)

        if not config.get("accepted_recorder_terms"):
            from tkinter import messagebox

            accepted = messagebox.askyesno(
                _("Important"),
                _(
                    "By continuing, the information you provided in the previous steps will be uploaded to Automagica's Portal. You can find the full terms on https://portal.automagica.com/tos. Do you accept the terms? You will only be prompted once on this machine."
                ),
                parent=self.master,
            )

            if not accepted:
                return
            else:
                config["accepted_recorder_terms"] = True
                save_config(config)

        buffered = BytesIO()
        self.screenshot.save(buffered, format="PNG")
        image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

        data = {
            "bot_secret": config.get("bot_secret"),
            "image_base64": image_base64,
            "anchors": self.anchors,
            "target": self.target,
        }

        portal_url = config.get("portal_url")

        if not portal_url:
            portal_url = "https://portal.automagica.com"

        url = portal_url + "/api/wand/train"

        r = http_client.post(url, json=data)

        try:
            data = r.json()
        except Exception:
            print(url)
            print(r.content)

        if data.get("automagica_id"):
            return data["automagica_id"]

        else:
            try:
                tk.messagebox.showerror(_("Error"), data["error"])
            except Exception:
                tk.messagebox.showerror(_("Unknown error"), data)

    def save_clicked(self):
        """
        User clicks 'save'
        """
        automagica_id = self.save()

        if self.on_finish:
            self.on_finish(automagica_id)


class SnippingToolWindow(Window):
    def __init__(self, parent, screenshot, callback, *args, info="", **kwargs):
        """
        Starts a full screen snipping tool for selecting coordinates
        """
        super().__init__(parent, *args, **kwargs)

        self.bind("<Escape>", self.close)

        self.screenshot = screenshot
        self.callback = callback

        # Bring window to full screen and top most level
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)

        w = self.winfo_width()
        h = self.winfo_height()

        # Keep reference of some things
        self.x = self.y = 0
        self.rect = None
        self.start_x = None
        self.start_y = None

        # Create the canvas
        self.canvas = tk.Canvas(self, width=w, height=h, cursor="crosshair")

        self.canvas.pack()

        # Add the screenshot
        self.img = ImageTk.PhotoImage(self.screenshot)
        self.canvas.create_image((0, 0), image=self.img, anchor="nw")

        # Connect the event handlers
        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)

        if info:
            font_ = font.Font(family=config.FONT, size=40)

            self.canvas.create_text(
                int(w / 2),
                int(h * 2 / 3),
                text=info,
                fill="#1B97F3",
                font=font_,
            )

    def close(self):
        """
        Close the window
        """
        self.destroy()
        self.update()

    def on_button_press(self, event):
        """
        On button press
        """

        # Update coordinates
        self.start_x = event.x
        self.start_y = event.y

        # If no rectangle is drawn yet, draw one
        if not self.rect:
            self.rect = self.canvas.create_rectangle(
                self.x,
                self.y,
                1,
                1,
                outline="#1B97F3",
                fill="#1B97F3",
                stipple="gray12",
            )

    def on_move_press(self, event):
        """
        On move press
        """
        # Update coordinates
        self.end_x, self.end_y = (event.x, event.y)

        # expand rectangle as you drag the mouse
        self.canvas.coords(
            self.rect, self.start_x, self.start_y, self.end_x, self.end_y
        )

    def on_button_release(self, event):
        """
        On button release
        """

        coordinates = (
            min(self.start_x, self.end_x),
            min(self.start_y, self.end_y),
            max(self.start_x, self.end_x),
            max(self.start_y, self.end_y),
        )

        self.callback(coordinates)

        self.close()


class KeybindWindow(Window):
    """
    Keybind window
    """

    def __init__(self, *args, keybind=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not keybind:
            keybind = Keybind()

        self.manager = self.master.manager
        self.keybind = keybind

        self.layout()

    def layout(self):
        self.entries_frame = self.create_entries_frame()
        self.entries_frame.pack()

        self.buttons_frame = self.create_buttons_frame()
        self.buttons_frame.pack()

    def create_entries_frame(self):
        frame = tk.Frame(self)

        self.name_label = tk.Label(
            frame, text=_("Name"), font=(config.FONT, 10),
        )
        self.name_label.pack(side="left")

        self.name_entry = InputField(frame)
        self.name_entry.pack(side="left")

        if self.keybind.name:
            self.name_entry.insert(0, self.keybind.name)

        self.key_combination_entry = KeycombinationEntry(
            frame, key_combination=self.keybind.key_combination
        )
        self.key_combination_entry.pack(side="bottom")

        return frame

    def create_buttons_frame(self):
        frame = tk.Frame(self)

        self.cancel_button = Button(
            frame, text=_("Cancel"), command=self.cancel_button_clicked
        )
        self.cancel_button.pack(side="left")

        self.save_button = Button(
            frame, text="Save", command=self.save_button_clicked
        )
        self.save_button.pack(side="left")

        return frame

    def save_button_clicked(self):
        self.keybind.name = self.name_entry.get()
        self.keybind.key_combination = self.key_combination_entry.get()

        if self.keybind not in self.manager.keybinds:
            self.manager.keybinds.append(self.keybind)

        self.master.update()

        self.destroy()

    def cancel_button_clicked(self):
        self.destroy()

    def configure_window(self):
        self.title(_("Keybind"))


class KeybindsOverviewWindow(Window):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.manager = KeybindsManager(
            keybinds=[
                Keybind(name=_("Hello World"), key_combination=["ctrl", "F1"])
            ]
        )

        self.layout()
        self.configure_window()
        self.update()

    def update(self):
        self.names_listbox.delete(0, tk.END)
        self.keybinds_listbox.delete(0, tk.END)

        for keybind in self.manager.keybinds:
            self.names_listbox.insert(tk.END, keybind.name)
            self.keybinds_listbox.insert(tk.END, keybind.key_combination_label)

    def layout(self):
        self.keybinds_frame = self.create_keybinds_frame()
        self.keybinds_frame.pack()

        self.buttons_frame = self.create_buttons_frame()
        self.buttons_frame.pack()

    def add_button_clicked(self):
        return KeybindWindow(self)

    def remove_button_clicked(self):
        i = self.keybinds_listbox.curselection()[0]

        self.manager.keybinds.pop(i)
        self.update()

    def edit_button_clicked(self):
        i = self.keybinds_listbox.curselection()

        if i:
            keybind = self.manager.keybinds[i[0]]
            _ = KeybindWindow(self, keybind=keybind)

    def create_buttons_frame(self):
        frame = tk.Frame(self)

        add_button = Button(
            frame, text=_("Add"), command=self.add_button_clicked
        )
        add_button.pack(side="left")

        remove_button = Button(
            frame, text=_("Remove"), command=self.remove_button_clicked
        )
        remove_button.pack(side="left")

        edit_button = Button(
            frame, text=_("Edit"), command=self.edit_button_clicked
        )
        edit_button.pack(side="left")

        return frame

    def create_keybinds_frame(self):
        frame = tk.Frame(self)

        self.names_listbox = tk.Listbox(
            frame, highlightthickness=0, activestyle="none"
        )
        self.names_listbox.pack(side="left")

        self.keybinds_listbox = tk.Listbox(
            frame, highlightthickness=0, activestyle="none"
        )
        self.keybinds_listbox.pack(side="left")

        return frame

    def configure_window(self):
        self.title(_("Keybinds"))


class ConfigWindow(Window):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.parent = parent

        self.title("Settings")
        self.resizable(False, False)

        self.logo_frame = self.create_logo_frame()
        self.logo_frame.pack()

        self.form_frame = self.create_form_frame()
        self.form_frame.pack()

        self.buttons_frame = self.create_buttons_frame()
        self.buttons_frame.pack()

        self.config(bg=config.COLOR_0)

        self.center()
        self.bot_secret_entry.focus()

    def save_clicked(self):
        values = self.master.master.config.values

        values["portal_url"] = self.portal_url_entry.get().strip()
        values["user_secret"] = self.user_secret_entry.get().strip()
        values["bot_secret"] = self.bot_secret_entry.get().strip()
        values["locale"] = self.locale_entry.get().strip()

        self.master.master.config.save()

        os._exit(0)

    def create_form_frame(self):
        frame = tk.Frame(self)

        portal_url_label = tk.Label(
            self,
            text=_("Portal URL"),
            bg=config.COLOR_0,
            fg=config.COLOR_1,
            font=(config.FONT, 10),
            width=50,
        )
        portal_url_label.pack()

        self.portal_url_entry = InputField(self, width=40)
        self.portal_url_entry.pack()

        user_secret_label = tk.Label(
            self,
            text=_("User secret"),
            bg=config.COLOR_0,
            fg=config.COLOR_1,
            font=(config.FONT, 10),
            width=50,
        )
        user_secret_label.pack()

        self.user_secret_entry = InputField(self, width=40)
        self.user_secret_entry.pack()

        bot_secret_label = tk.Label(
            self,
            text=_("Bot secret"),
            bg=config.COLOR_0,
            fg=config.COLOR_1,
            font=(config.FONT, 10),
            width=50,
        )
        bot_secret_label.pack()

        self.bot_secret_entry = InputField(self, width=40)
        self.bot_secret_entry.pack()

        locale_label = tk.Label(
            self,
            text=_("Locale"),
            bg=config.COLOR_0,
            fg=config.COLOR_1,
            font=(config.FONT, 10),
            width=50,
        )
        locale_label.pack()

        self.locale_entry = InputField(self, width=40)
        self.locale_entry.pack()

        # Pre-fill fields
        self.portal_url_entry.insert(
            tk.END, self.master.master.config.values.get("portal_url", "")
        )
        self.user_secret_entry.insert(
            tk.END, self.master.master.config.values.get("user_secret", "")
        )
        self.bot_secret_entry.insert(
            tk.END, self.master.master.config.values.get("bot_secret", "")
        )
        self.locale_entry.insert(
            tk.END, self.master.master.config.values.get("locale", "")
        )

        return frame

    def create_buttons_frame(self):
        frame = tk.Frame(self)

        save_button = Button(self, text=_("Save"), command=self.save_clicked)
        save_button.configure(bg=config.COLOR_7)
        save_button.pack(padx=5, pady=5)

        add_to_startup_button = Button(
            self,
            text=_("Set up auto-start"),
            command=self.add_to_startup_clicked,
        )
        add_to_startup_button.configure(bg=config.COLOR_7)
        add_to_startup_button.pack(padx=5, pady=5)

        return frame

    def add_to_startup_clicked(self):
        from tkinter import messagebox

        self.master.master.config.add_bot_to_startup()

        messagebox.showinfo(
            _("Info"), _("Bot will auto-start on next system boot.")
        )

    def create_logo_frame(self):
        frame = tk.Frame(self)

        frame.configure(bg=config.COLOR_0)

        logo_path = os.path.join(
            os.path.abspath(__file__).replace(
                os.path.basename(os.path.realpath(__file__)), ""
            ),
            "icons",
            "logo.png",
        )

        self.logo_img_pil = Image.open(logo_path)
        self.logo_img = ImageTk.PhotoImage(image=self.logo_img_pil)

        logo_lbl = tk.Label(
            self,
            image=self.logo_img,
            bg=config.COLOR_0,
            font=(config.FONT, 10),
        )
        logo_lbl.pack(padx=20, pady=10)

        return frame


class VariableExplorerWindow(Window):
    def __init__(self, parent, *args, bot=None, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.bot = bot

        self.configure_window()
        self._layout()

        self.center(w=500, h=400)

    def configure_window(self):
        self.title(_("Variable Explorer"))

    @property
    def locals_(self):
        locals_ = {
            key: val
            for key, val in self.bot.interpreter.locals.items()
            if key not in ["__name__", "__doc__", "__builtins__"]
        }

        return locals_

    def _layout(self):
        self.variables_list = self.create_variables_list()
        self.variables_list.pack(fill="both", expand=True)

    def create_variables_list(self):
        frame = tk.Frame(self)

        def scroll(*args):
            self.variables.yview(*args)
            self.types.yview(*args)
            self.values.yview(*args)

        y_scrollbar = tk.Scrollbar(frame, command=scroll)
        y_scrollbar.grid(column=3, row=1, sticky="ns")

        variables_label = tk.Label(
            frame, text=_("Name"), fg=config.COLOR_11, font=(config.FONT, 10),
        )
        self.variables = tk.Listbox(
            frame, bd=0, highlightthickness=0, yscrollcommand=y_scrollbar.set
        )
        self.variables.bind("<MouseWheel>", self.on_mouse_wheel)

        types_label = tk.Label(
            frame, text=_("Type"), fg=config.COLOR_11, font=(config.FONT, 10),
        )
        self.types = tk.Listbox(
            frame, bd=0, highlightthickness=0, yscrollcommand=y_scrollbar.set
        )
        self.types.bind("<MouseWheel>", self.on_mouse_wheel)

        values_label = tk.Label(
            frame, text=_("Value"), fg=config.COLOR_11, font=(config.FONT, 10)
        )
        self.values = tk.Listbox(
            frame, bd=0, highlightthickness=0, yscrollcommand=y_scrollbar.set
        )
        self.values.bind("<MouseWheel>", self.on_mouse_wheel)

        for key, val in self.locals_.items():

            from types import ModuleType, FunctionType

            if not isinstance(val, (ModuleType, FunctionType, type)):
                self.variables.insert(tk.END, key)
                self.types.insert(tk.END, type(val).__name__)

                if isinstance(val, (int, dict)):
                    self.values.insert(tk.END, str(val))
                elif isinstance(val, str):
                    self.values.insert(tk.END, '"{}"'.format(val))
                else:
                    self.values.insert(tk.END, str(val))

        variables_label.place(relx=0, rely=0, relwidth=0.3, relheight=0.1)
        self.variables.place(relx=0, rely=0.1, relwidth=0.3, relheight=0.9)

        types_label.place(relx=0.3, rely=0, relwidth=0.3, relheight=0.1)
        self.types.place(relx=0.3, rely=0.1, relwidth=0.3, relheight=0.9)

        values_label.place(relx=0.6, rely=0, relwidth=0.3, relheight=0.1)
        self.values.place(relx=0.6, rely=0.1, relwidth=0.3, relheight=0.9)

        return frame

    def on_mouse_wheel(self, event):
        self.values.yview("scroll", event.delta, "units")
        self.types.yview("scroll", event.delta, "units")
        self.variables.yview("scroll", event.delta, "units")
        return "break"


class NodePropsWindow(Window):
    def __init__(self, parent, node, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.parent = parent
        self.node = node
        self.resizable(False, False)

        # Make sure this window is the only window
        # grabbing
        # events from the user
        try:
            self.grab_set()
        except Exception:
            pass

        self.title(_("Properties"))

        self.layout()

    def layout(self):
        self.button_frame = self.create_buttons_frame()
        self.button_frame.pack()

        self.center()

    def create_buttons_frame(self):
        frame = tk.Frame(self)

        frame.configure(bg=config.COLOR_4)

        save_button = Button(frame, text=_("Save"), command=self.save)
        save_button.configure(bg=config.COLOR_7)
        save_button.pack(side="right", padx=5, pady=5)

        cancel_button = Button(frame, text=_("Cancel"), command=self.cancel)
        cancel_button.pack(side="right", padx=5, pady=5)
        self.bind("<Escape>", lambda e: self.cancel())

        remove_button = Button(
            frame, text=_("Remove"), command=self.remove, underline=0
        )
        remove_button.configure(bg=config.COLOR_6)
        remove_button.pack(side="left", padx=5, pady=5)
        self.bind("<Alt-r>", lambda e: self.remove())

        return frame

    def save(self):
        # Save Node things
        self.node.label = self.label_entry.get()

        self.node.next_node = self.next_node_menu.get()

        self.parent.draw()

        # Release event
        self.grab_release()

        self.destroy()

        self.parent.update()

    def cancel(self):
        self._close()

    def _close(self):
        self.parent.update()
        self.parent.draw()
        self.grab_release()
        self.destroy()

    def remove(self):
        self.parent.parent.master.flow.nodes.remove(self.node)
        self._close()

    def create_node_frame(self):
        frame = LabelFrame(self, text=_("Node"))

        # UID Information
        uid_label_label = tk.Label(
            frame,
            text=_("Unique ID"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        uid_label_label.grid(row=0, column=0, sticky="w")
        uid_label = tk.Label(
            frame,
            text=self.node.uid,
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        uid_label.grid(row=0, column=1, sticky="w", padx=3, pady=3)

        help_button = HelpButton(
            frame,
            message=_(
                "This is the unique identifier for this specific node. \
                    It can be used to connect this node from other nodes."
            ),
        )
        help_button.grid(row=0, column=2)

        # Node Label
        label_label = tk.Label(
            frame,
            text=_("Label"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        label_label.grid(row=1, column=0, sticky="w")
        self.label_entry = InputField(frame)
        self.label_entry.grid(row=1, column=1, sticky="ew", padx=3, pady=3)

        help_button = HelpButton(
            frame, message=_("This label is shown in the Flow.")
        )
        help_button.grid(row=1, column=2)

        # Pre-fill label
        if self.node.label:
            self.label_entry.insert(tk.END, self.node.label)

        # Next node selection
        next_node_option_label = tk.Label(
            frame,
            text=_("Next Node"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        next_node_option_label.grid(row=2, column=0, sticky="w")
        self.next_node_menu = NodeSelectionInputWidget(
            frame,
            self.parent.master.master.flow.nodes,
            value=self.node.next_node,
        )
        self.next_node_menu.grid(row=2, column=1, sticky="ew", padx=3, pady=3)

        help_button = HelpButton(
            frame, message=_("This node will be the next node in the flow.")
        )
        help_button.grid(row=2, column=2)

        return frame


class ActivityNodePropsWindow(NodePropsWindow):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

    def layout(self):
        self.info_frame = self.create_info_frame()
        self.info_frame.pack(fill="x", padx=5, pady=5)

        self.options_frame = self.create_options_frame()
        self.options_frame.pack(fill="x", padx=5, pady=5)

        self.node_frame = self.create_node_frame()
        self.node_frame.pack(fill="x", padx=5, pady=5)

        self.buttons_frame = self.create_buttons_frame()
        self.buttons_frame.pack(fill="x", padx=5, pady=5)

    def create_info_frame(self):
        frame = LabelFrame(self, text=_("Activity"))

        name = tk.Label(
            frame,
            font=(config.FONT, 8),
            text=config.ACTIVITIES[self.node.activity]["name"],
            wraplength=250,
            justify="left",
            bg=config.COLOR_4,
            fg=config.COLOR_11,
        )
        name.pack(expand=True)

        description = tk.Label(
            frame,
            font=(config.FONT, 8),
            text=config.ACTIVITIES[self.node.activity]["description"],
            wraplength=250,
            justify="left",
            bg=config.COLOR_4,
            fg=config.COLOR_11,
        )
        description.pack(expand=True)

        return frame

    def create_options_frame(self):
        frame = LabelFrame(self, text=_("Options"))

        args = config.ACTIVITIES[self.node.activity]["args"]

        args_labels = {}

        self.args_inputs = {}

        i = 0

        for i, (name, arg) in enumerate(args.items()):
            label = name

            if name == "self":
                label = _("Object variable")
                arg["description"] = _(
                    "Name of the variable to assign the object to. \
                        If you want to have multiple instances of \
                            this object, give it a different name \
                                than the default name."
                )

            label = label.capitalize().replace("_", " ")

            if not config.ACTIVITIES[self.node.activity]["args"][name].get(
                "optional"
            ):
                label = label + " " + _("(required)")

            args_labels[name] = tk.Label(
                frame,
                text=label,
                bg=config.COLOR_4,
                fg=config.COLOR_11,
                font=(config.FONT, 10),
            )
            args_labels[name].grid(row=i, column=0, sticky="w")

            argtype = config.ACTIVITIES[self.node.activity]["args"][name].get(
                "type"
            )

            argextensions = config.ACTIVITIES[self.node.activity]["args"][
                name
            ].get("extensions")

            if argtype:
                if "input_file" in argtype:
                    self.args_inputs[name] = FilePathInputWidget(
                        frame, extensions=argextensions
                    )

                elif "output_file" in argtype:
                    self.args_inputs[name] = FilePathOutputWidget(
                        frame, extensions=argextensions
                    )

                elif "input_dir" in argtype:
                    self.args_inputs[name] = DirWidget(frame)

                elif "output_dir" in argtype:
                    self.args_inputs[name] = DirWidget(frame)

                elif "bool" in argtype:
                    self.args_inputs[name] = BooleanInputWidget(
                        frame,
                        value=self.node.args_.get(
                            name,
                            config.ACTIVITIES[self.node.activity]["args"][
                                name
                            ].get("default"),
                        ),
                    )

                elif "automagica_id" in argtype:
                    self.args_inputs[name] = AutomagicaIdInputWidget(frame)

                elif "text" in argtype:
                    self.args_inputs[name] = TextInputWidget(frame)

                else:
                    self.args_inputs[name] = InputWidget(
                        frame,
                        value=config.ACTIVITIES[self.node.activity]["args"][
                            name
                        ].get("default"),
                    )

            elif config.ACTIVITIES[self.node.activity]["args"][name].get(
                "options"
            ):
                self.args_inputs[name] = AutocompleteDropdown(
                    frame,
                    values=[
                        f"'{option}'"
                        for option in config.ACTIVITIES[self.node.activity][
                            "args"
                        ][name].get("options")
                    ],
                )

            else:
                self.args_inputs[name] = InputWidget(
                    frame,
                    value=config.ACTIVITIES[self.node.activity]["args"][
                        name
                    ].get("default"),
                )

            self.args_inputs[name].grid(
                row=i, column=1, sticky="w", padx=3, pady=3
            )

            HelpButton(frame, message=arg.get("description", "")).grid(
                row=i, column=2
            )

            if self.node.args_.get(name) is not None:
                self.args_inputs[name]._set(self.node.args_[name])

            else:
                default = config.ACTIVITIES[self.node.activity]["args"][
                    name
                ].get("default")

                if isinstance(default, str):
                    default = '"{}"'.format(default)

                self.args_inputs[name]._set(str(default))

        self.return_entry = None
        if config.ACTIVITIES[self.node.activity]["return"]:
            return_label = tk.Label(
                frame,
                text=_("Return variable"),
                bg=config.COLOR_4,
                fg=config.COLOR_11,
                font=(config.FONT, 10),
            )
            self.return_entry = InputField(frame)
            return_label.grid(row=i + 1, column=0, sticky="w")
            self.return_entry.grid(
                row=i + 1, column=1, sticky="w", padx=3, pady=3
            )

            if self.node.return_:
                self.return_entry.insert(tk.END, self.node.return_)

            return_variable_help = HelpButton(
                frame, message=_("Where to store the output of this activity.")
            )
            return_variable_help.grid(row=i + 1, column=2)

        return frame

    def create_node_frame(self):
        frame = LabelFrame(self, text=_("Node"))

        # UID Information
        uid_label_label = tk.Label(
            frame,
            text=_("Unique ID"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        uid_label_label.grid(row=0, column=0, sticky="w")
        uid_label = tk.Label(
            frame,
            text=self.node.uid,
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        uid_label.grid(row=0, column=1, sticky="w", padx=3, pady=3)

        help_button = HelpButton(
            frame,
            message=_(
                "This is the unique identifier for this specific node. \
                    It can be used to connect this node from other nodes."
            ),
        )
        help_button.grid(row=0, column=2)

        # Node Label
        label_label = tk.Label(
            frame,
            text=_("Label"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        label_label.grid(row=1, column=0, sticky="w")
        self.label_entry = InputField(frame)
        self.label_entry.grid(row=1, column=1, sticky="ew", padx=3, pady=3)

        help_button = HelpButton(
            frame, message=_("This label is shown in the Flow.")
        )
        help_button.grid(row=1, column=2)

        # Pre-fill label
        if self.node.label:
            self.label_entry.insert(tk.END, self.node.label)

        # Next node selection
        next_node_option_label = tk.Label(
            frame,
            text=_("Next Node"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        next_node_option_label.grid(row=2, column=0, sticky="w")
        self.next_node_menu = NodeSelectionInputWidget(
            frame,
            self.parent.master.master.flow.nodes,
            value=self.node.next_node,
        )
        self.next_node_menu.grid(row=2, column=1, sticky="ew", padx=3, pady=3)

        help_button = HelpButton(
            frame, message=_("This node will be the next node in the flow.")
        )
        help_button.grid(row=2, column=2)

        # Exception node selection
        on_exception_node_option_label = tk.Label(
            frame,
            text=_("On Exception Node"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        on_exception_node_option_label.grid(row=3, column=0, sticky="w")
        self.on_exception_node_menu = NodeSelectionInputWidget(
            frame,
            self.parent.master.master.flow.nodes,
            value=self.node.on_exception_node,
        )
        self.on_exception_node_menu.grid(
            row=3, column=1, sticky="ew", padx=3, pady=3
        )

        help_button = HelpButton(
            frame, message=_("This node will be the next node in the flow.")
        )
        help_button.grid(row=3, column=2)

        return frame

    def save(self):
        # Save args
        self.node.args_ = {
            key: val.get() for key, val in self.args_inputs.items()
        }

        if self.return_entry:
            self.node.return_ = self.return_entry.get()

        # Save Node things
        self.node.label = self.label_entry.get()

        self.node.next_node = self.next_node_menu.get()

        self.node.on_exception_node = self.on_exception_node_menu.get()

        self.parent.draw()

        # Release event
        self.grab_release()

        self.destroy()

        self.parent.update()


class StartNodePropsWindow(NodePropsWindow):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

    def layout(self):
        self.node_frame = self.create_node_frame()
        self.node_frame.pack(fill="x", padx=5, pady=5)

        self.buttons_frame = self.create_buttons_frame()
        self.buttons_frame.pack(fill="x", padx=5, pady=5)

        self.center()


class IfElseNodePropsWindow(NodePropsWindow):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

    def layout(self):
        self.node_frame = self.create_node_frame()
        self.node_frame.pack(fill="x", padx=5, pady=5)

        self.buttons_frame = self.create_buttons_frame()
        self.buttons_frame.pack(fill="x", padx=5, pady=5)

    def create_node_frame(self):
        frame = LabelFrame(self, text=_("Node"))

        # UID Information
        uid_label_label = tk.Label(
            frame,
            text=_("Unique ID"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        uid_label_label.grid(row=0, column=0, sticky="w")
        uid_label = tk.Label(
            frame,
            text=self.node.uid,
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        uid_label.grid(row=0, column=1, sticky="w", padx=3, pady=3)

        help_button = HelpButton(
            frame,
            message=_(
                "This is the unique identifier for this specific node. \
                    It can be used to connect this node from other nodes."
            ),
        )
        help_button.grid(row=0, column=2)

        # Node Label
        label_label = tk.Label(
            frame,
            text=_("Label"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        label_label.grid(row=1, column=0, sticky="w")
        self.label_entry = InputField(frame)
        self.label_entry.grid(row=1, column=1, sticky="ew", padx=3, pady=3)

        help_button = HelpButton(
            frame, message=_("This label is shown in the Flow.")
        )
        help_button.grid(row=1, column=2)

        # Pre-fill label
        if self.node.label:
            self.label_entry.insert(tk.END, self.node.label)

        # Condition Label
        condition_label = tk.Label(
            frame,
            text=_("Condition"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        condition_label.grid(row=2, column=0, sticky="w")
        self.condition_entry = InputField(frame)
        self.condition_entry.grid(row=2, column=1, sticky="ew", padx=3, pady=3)

        help_button = HelpButton(
            frame,
            message=_(
                "The condition to be evaluated. If the condition is true, \
                    the flow will continue to the next node. If the \
                        condition is false, the flow will go to the else node."
            ),
        )
        help_button.grid(row=2, column=2)

        # Pre-fill condition
        if self.node.condition:
            self.condition_entry.insert(tk.END, self.node.condition)

        # Next node selection
        next_node_option_label = tk.Label(
            frame,
            text=_("Next Node"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        next_node_option_label.grid(row=3, column=0, sticky="w")
        self.next_node_menu = NodeSelectionInputWidget(
            frame,
            self.parent.master.master.flow.nodes,
            value=self.node.next_node,
        )

        self.next_node_menu.grid(row=3, column=1, sticky="ew", padx=3, pady=3)

        help_button = HelpButton(
            frame, message=_("This node will be the next node in the flow.")
        )
        help_button.grid(row=3, column=2)

        # Else node selection
        else_node_option_label = tk.Label(
            frame,
            text=_("Else Node"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        else_node_option_label.grid(row=4, column=0, sticky="w")
        self.else_node_menu = NodeSelectionInputWidget(
            frame,
            self.parent.master.master.flow.nodes,
            value=self.node.else_node,
        )
        self.else_node_menu.grid(row=4, column=1, sticky="ew", padx=3, pady=3)

        help_button = HelpButton(
            frame,
            message=_(
                "This node will be the next node if the condition is not met."
            ),
        )
        help_button.grid(row=4, column=2)

        return frame

    def save(self):
        self.node.next_node = self.next_node_menu.get()
        self.node.else_node = self.else_node_menu.get()
        self.node.condition = self.condition_entry.get()
        self.node.label = self.label_entry.get()

        self.parent.draw()

        # Release event
        self.grab_release()

        self.destroy()

        self.parent.update()


class LoopNodePropsWindow(NodePropsWindow):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

    def layout(self):
        self.node_frame = self.create_node_frame()
        self.node_frame.pack(fill="x", padx=5, pady=5)

        self.buttons_frame = self.create_buttons_frame()
        self.buttons_frame.pack(fill="x", padx=5, pady=5)

    def create_node_frame(self):
        frame = LabelFrame(self, text="Node")

        # UID Information
        uid_label_label = tk.Label(
            frame,
            text=_("Unique ID"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        uid_label_label.grid(row=0, column=0, sticky="w")
        uid_label = tk.Label(
            frame,
            text=self.node.uid,
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        uid_label.grid(row=0, column=1, sticky="w")

        # Node Label
        label_label = tk.Label(
            frame,
            text=_("Label"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        label_label.grid(row=1, column=0, sticky="w")
        self.label_entry = InputField(frame)
        self.label_entry.grid(row=1, column=1, sticky="ew", padx=3, pady=3)

        if self.node.label:
            self.label_entry.insert(tk.END, self.node.label)

        help_button = HelpButton(
            frame, message=_("This label is shown in the Flow.")
        )
        help_button.grid(row=1, column=2)

        # Repeat N Times
        repeat_n_times_label = tk.Label(
            frame,
            text=_("Repeat loop N times"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        repeat_n_times_label.grid(row=2, column=0, sticky="w")
        self.repeat_n_times_entry = InputField(frame)
        self.repeat_n_times_entry.grid(row=2, column=1, sticky="w")

        # Pre-fill iterable
        if self.node.repeat_n_times:
            self.repeat_n_times_entry.insert(tk.END, self.node.repeat_n_times)

        help_button = HelpButton(
            frame,
            message=_("Number of times to repeat this part of the flow."),
        )
        help_button.grid(row=2, column=2)

        # Loop variable
        loop_variable_label = tk.Label(
            frame,
            text=_("Run loop for every "),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        loop_variable_label.grid(row=3, column=0, sticky="w")
        self.loop_variable_entry = InputField(frame)
        self.loop_variable_entry.grid(row=3, column=1, sticky="w")

        # Pre-fill loop variable
        if self.node.loop_variable:
            self.loop_variable_entry.insert(tk.END, self.node.loop_variable)

        help_button = HelpButton(
            frame,
            message=_(
                "The name of the variable to assign the single item \
                    of the collection/list to while iterating."
            ),
        )
        help_button.grid(row=3, column=2)

        # Iterable
        iterable_label = tk.Label(
            frame,
            text=_("in"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        iterable_label.grid(row=3, column=3, sticky="w")
        self.iterable_entry = InputField(frame)
        self.iterable_entry.grid(row=3, column=4, sticky="w")

        # Pre-fill iterable
        if self.node.iterable:
            self.iterable_entry.insert(tk.END, self.node.iterable)

        help_button = HelpButton(
            frame,
            message=_(
                "The collection or list to iterate over and repeat this \
                    part of the flow. This will override the default \
                        'repeat n times' setting."
            ),
        )
        help_button.grid(row=3, column=5)

        # Next node selection
        next_node_option_label = tk.Label(
            frame,
            text=_("After loop finish node"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        next_node_option_label.grid(row=4, column=0, sticky="w")
        self.next_node_menu = NodeSelectionInputWidget(
            frame,
            self.parent.master.master.flow.nodes,
            value=self.node.next_node,
        )

        self.next_node_menu.grid(row=4, column=1, sticky="w")

        # Else node selection
        loop_node_option_label = tk.Label(
            frame,
            text=_("Repeat flow starting with"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        loop_node_option_label.grid(row=5, column=0, sticky="w")
        self.loop_node_menu = NodeSelectionInputWidget(
            frame,
            self.parent.master.master.flow.nodes,
            value=self.node.loop_node,
        )

        self.loop_node_menu.grid(row=5, column=1, sticky="w")

        return frame

    def save(self):
        self.node.next_node = self.next_node_menu.get()
        self.node.loop_node = self.loop_node_menu.get()

        self.node.label = self.label_entry.get()

        self.node.iterable = self.iterable_entry.get()
        self.node.loop_variable = self.loop_variable_entry.get()
        self.node.repeat_n_times = self.repeat_n_times_entry.get()

        self.parent.draw()

        # Release event
        self.grab_release()

        self.destroy()

        self.parent.update()


class DotPyFileNodePropsWindow(NodePropsWindow):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

    def layout(self):
        self.node_frame = self.create_node_frame()
        self.node_frame.pack(fill="x", padx=5, pady=5)

        self.buttons_frame = self.create_buttons_frame()
        self.buttons_frame.pack(fill="x", padx=5, pady=5)

    def create_node_frame(self):
        frame = LabelFrame(self, text="Node")

        # UID Information
        uid_label_label = tk.Label(
            frame,
            text=_("Unique ID"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        uid_label_label.grid(row=0, column=0, sticky="w")
        uid_label = tk.Label(frame, text=self.node.uid, bg=config.COLOR_4)
        uid_label.grid(row=0, column=1, sticky="w")

        # Node Label
        label_label = tk.Label(
            frame,
            text=_("Label"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        label_label.grid(row=1, column=0, sticky="w")
        self.label_entry = InputField(frame)
        self.label_entry.grid(row=1, column=1, sticky="ew", padx=3, pady=3)

        help_button = HelpButton(
            frame, message=_("This label is shown in the Flow.")
        )
        help_button.grid(row=1, column=2)

        # Pre-fill label
        if self.node.label:
            self.label_entry.insert(tk.END, self.node.label)

        # Node Label
        dotpyfile_path_label = tk.Label(
            frame,
            text=_(".py-file path"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        dotpyfile_path_label.grid(row=2, column=0, sticky="w")
        self.dotpyfile_path_entry = FilePathInputWidget(
            frame, value=self.node.dotpyfile_path
        )
        self.dotpyfile_path_entry.grid(row=2, column=1, sticky="w")

        # Next node selection
        next_node_option_label = tk.Label(
            frame,
            text=_("Next Node"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        next_node_option_label.grid(row=3, column=0, sticky="w")
        self.next_node_menu = NodeSelectionInputWidget(
            frame,
            self.parent.master.master.flow.nodes,
            value=self.node.next_node,
        )
        self.next_node_menu.grid(row=3, column=1, sticky="w")

        # Else node selection
        on_exception_node_option_label = tk.Label(
            frame,
            text=_("On Exception Node"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        on_exception_node_option_label.grid(row=4, column=0, sticky="w")
        self.on_exception_node_menu = NodeSelectionInputWidget(
            frame,
            self.parent.master.master.flow.nodes,
            value=self.node.on_exception_node,
        )

        self.on_exception_node_menu.grid(row=4, column=1, sticky="w")

        return frame

    def save(self):
        self.node.next_node = self.next_node_menu.get()
        self.node.on_exception_node = self.on_exception_node_menu.get()
        self.node.dotpyfile_path = self.dotpyfile_path_entry.get()
        self.node.label = self.label_entry.get()

        self.parent.draw()

        # Release event
        self.grab_release()

        self.destroy()

        self.parent.update()


class PythonCodeNodePropsWindow(NodePropsWindow):
    """
    Python code node properties window
    """

    def __init__(self, parent, *args, **kwargs):
        """
        Create the Python code node properties window
        """
        super().__init__(parent, *args, **kwargs)

    def layout(self):
        """
        Layout the window
        """
        self.node_frame = self.create_node_frame()
        self.node_frame.pack(fill="x", padx=5, pady=5)

        self.buttons_frame = self.create_buttons_frame()
        self.buttons_frame.pack(fill="x", padx=5, pady=5)

    def create_buttons_frame(self):
        """
        Create the buttons frame
        """
        frame = tk.Frame(self)

        frame.configure(bg=config.COLOR_4)

        save_button = Button(frame, text=_("Save"), command=self.save)
        save_button.configure(bg=config.COLOR_7)
        save_button.pack(side="right", padx=5, pady=5)

        cancel_button = Button(frame, text=_("Cancel"), command=self.cancel)
        cancel_button.pack(side="right", padx=5, pady=5)
        self.bind("<Escape>", lambda e: self.cancel())

        remove_button = Button(
            frame, text=_("Remove"), command=self.remove, underline=0
        )
        remove_button.configure(bg=config.COLOR_6)
        remove_button.pack(side="left", padx=5, pady=5)
        self.bind("<Alt-r>", lambda e: self.remove())

        return frame

    def create_node_frame(self):
        """
        Create the node frame
        """
        frame = LabelFrame(self, text="Node")

        # UID Information
        uid_label_label = tk.Label(
            frame,
            text="Unique ID",
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        uid_label_label.grid(row=0, column=0, sticky="w")
        uid_label = tk.Label(
            frame,
            text=self.node.uid,
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        uid_label.grid(row=0, column=1, sticky="w")

        # Node Label
        label_label = tk.Label(
            frame,
            text=_("Label"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        label_label.grid(row=1, column=0, sticky="w")
        self.label_entry = InputField(frame)
        self.label_entry.grid(row=1, column=1, sticky="ew", padx=3, pady=3)

        help_button = HelpButton(
            frame, message=_("This label is shown in the Flow.")
        )
        help_button.grid(row=1, column=2)

        # Pre-fill label
        if self.node.label:
            self.label_entry.insert(tk.END, self.node.label)

        # Node Label
        code_label = tk.Label(
            frame,
            text=_("Code"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        code_label.grid(row=2, column=0, sticky="w")

        self.code_entry = tk.Text(frame)
        self.code_entry.config(font=("TkFixedFont"))
        self.code_entry.grid(row=2, column=1, sticky="w")

        # Pre-fill label
        if self.node.code:
            self.code_entry.insert(tk.END, self.node.code)

        # Next node selection
        next_node_option_label = tk.Label(
            frame,
            text=_("Next Node"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        next_node_option_label.grid(row=3, column=0, sticky="w")
        self.next_node_menu = NodeSelectionInputWidget(
            frame,
            self.parent.master.master.flow.nodes,
            value=self.node.next_node,
        )

        self.next_node_menu.grid(row=3, column=1, sticky="w")

        # Else node selection
        on_exception_node_option_label = tk.Label(
            frame,
            text=_("On Exception Node"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        on_exception_node_option_label.grid(row=4, column=0, sticky="w")
        self.on_exception_node_menu = NodeSelectionInputWidget(
            frame,
            self.parent.master.master.flow.nodes,
            value=self.node.on_exception_node,
        )

        self.on_exception_node_menu.grid(row=4, column=1, sticky="w")

        return frame

    def save(self):
        self.node.next_node = self.next_node_menu.get()
        self.node.on_exception_node = self.on_exception_node_menu.get()
        self.node.code = self.code_entry.get("1.0", tk.END)
        self.node.label = self.label_entry.get()

        self.parent.draw()

        # Release event
        self.grab_release()

        self.destroy()

        self.parent.update()


class CommentNodePropsWindow(NodePropsWindow):
    """
    Properties window for the Comment node
    """

    def __init__(self, parent, *args, **kwargs):
        """
        Create the properties window
        """
        super().__init__(parent, *args, **kwargs)

    def layout(self):
        """
        Layout the window
        """
        self.node_frame = self.create_node_frame()
        self.node_frame.pack(fill="x", padx=5, pady=5)

        self.buttons_frame = self.create_buttons_frame()
        self.buttons_frame.pack(fill="x", padx=5, pady=5)

    def create_node_frame(self):
        """
        Create the node frame
        """
        frame = LabelFrame(self, text=_("Node"))

        # UID Information
        uid_label_label = tk.Label(
            frame,
            text=_("Unique ID"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        uid_label_label.grid(row=0, column=0, sticky="w")
        uid_label = tk.Label(
            frame,
            text=self.node.uid,
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        uid_label.grid(row=0, column=1, sticky="w")

        # Comment
        comment_label = tk.Label(
            frame,
            text=_("Comment"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        comment_label.grid(row=1, column=0, sticky="w")
        self.comment_entry = InputField(frame)
        self.comment_entry.grid(row=1, column=1, sticky="w")

        # Pre-fill label
        if self.node.comment:
            self.comment_entry.insert(tk.END, self.node.comment)

        return frame

    def save(self):
        """
        Save the node properties
        """
        self.node.comment = self.comment_entry.get()

        self.parent.draw()

        # Release event
        self.grab_release()

        self.destroy()

        self.parent.update()


class SubFlowNodePropsWindow(NodePropsWindow):
    """
    Properties window for a Sub-flow node
    """

    def __init__(self, parent, *args, **kwargs):
        """
        Create the window
        """
        super().__init__(parent, *args, **kwargs)

    def layout(self):
        """
        Layout the window
        """
        self.node_frame = self.create_node_frame()
        self.node_frame.pack(fill="x", padx=5, pady=5)

        self.buttons_frame = self.create_buttons_frame()
        self.buttons_frame.pack(fill="x", padx=5, pady=5)

    def create_node_frame(self):
        """
        Create the node frame
        """
        frame = LabelFrame(self, text=_("Node"))

        # UID Information
        uid_label_label = tk.Label(
            frame,
            text=_("Unique ID"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        uid_label_label.grid(row=0, column=0, sticky="w")
        uid_label = tk.Label(
            frame,
            text=self.node.uid,
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        uid_label.grid(row=0, column=1, sticky="w")

        # Node Label
        label_label = tk.Label(
            frame,
            text=_("Label"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        label_label.grid(row=1, column=0, sticky="w")
        self.label_entry = InputField(frame)
        self.label_entry.grid(row=1, column=1, sticky="ew", padx=3, pady=3)

        help_button = HelpButton(
            frame, message=_("This label is shown in the Flow.")
        )
        help_button.grid(row=1, column=2)

        # Pre-fill label
        if self.node.label:
            self.label_entry.insert(tk.END, self.node.label)

        # Node Label
        subflow_path_label = tk.Label(
            frame,
            text=_("Flow path"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        subflow_path_label.grid(row=4, column=0, sticky="w")
        self.subflow_path_entry = FilePathInputWidget(
            frame, value=self.node.subflow_path
        )
        self.subflow_path_entry.grid(row=4, column=1, sticky="w")

        def edit():
            FlowDesignerWindow(
                self.parent.master.master.master,
                flow=Flow(self.node.subflow_path.replace('"', "")),
                bot=self.parent.master.master.master.bot,
            )
            self.close_window()

        self.edit_subflow_button = Button(frame, text="Edit", command=edit)
        self.edit_subflow_button.grid(row=4, column=2, sticky="w")

        # Next node selection
        next_node_option_label = tk.Label(
            frame,
            text=_("Next Node"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        next_node_option_label.grid(row=5, column=0, sticky="w")

        self.next_node_menu = NodeSelectionInputWidget(
            frame,
            self.parent.master.master.flow.nodes,
            value=self.node.next_node,
        )

        self.next_node_menu.grid(row=5, column=1, sticky="w")

        # Exception node selection
        on_exception_node_option_label = tk.Label(
            frame,
            text=_("On Exception Node"),
            bg=config.COLOR_4,
            fg=config.COLOR_11,
            font=(config.FONT, 10),
        )
        on_exception_node_option_label.grid(row=6, column=0, sticky="w")
        self.on_exception_node_menu = NodeSelectionInputWidget(
            frame,
            self.parent.master.master.flow.nodes,
            value=self.node.on_exception_node,
        )

        self.on_exception_node_menu.grid(row=6, column=1, sticky="w")

        return frame

    def close_window(self):
        """
        Close window
        """
        self.parent.draw()

        # Release event
        self.grab_release()

        self.destroy()

        self.parent.update()

    def save(self):
        """
        Save
        """
        self.node.next_node = self.next_node_menu.get()
        self.node.on_exception_node = self.on_exception_node_menu.get()
        self.node.subflow_path = self.subflow_path_entry.get()
        self.node.label = self.label_entry.get()

        self.close_window()
