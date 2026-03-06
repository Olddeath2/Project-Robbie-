
import tkinter as tk
from tkinter import font as tkfont
import paho.mqtt.client as mqtt
import time
import math

# ── CONFIG ────────────────────────────────────────────────────────────────────
BROKER_HOST     = "broker.emqx.io"
BROKER_PORT     = 1883
TOPIC_CMD       = "robot/cmd"
TOPIC_STATUS    = "robot/status"
CLIENT_ID       = "robot_sequencer"

DEFAULT_SPEED   = 20
DEFAULT_STEPS   = 10
STEP_PIXELS     = 30
TURN_DEGREES    = 15
DELAY_PER_STEP  = 2    # seconds between commands

# ── COMMAND BUILDER ───────────────────────────────────────────────────────────
def build_cmd(mode, steps, speed, dir1, skip1, dir2, skip2):
    return f"{mode},{str(steps).zfill(3)},{str(speed).zfill(3)},{dir1},{skip1},{dir2},{skip2}"

STOP_CMD      = build_cmd(0, 0, 0, 1, 0, 1, 0)
MANUAL_CMD    = "mode,manual"
AUTO_CMD      = "mode,auto"
LINE_FIND_CMD = "mode,linefind"

# ── SYNTAX HIGHLIGHTING KEYWORDS ─────────────────────────────────────────────
KEYWORDS = {
    "move":       "#0077cc",
    "wait":       "#e67e00",
    "manual":     "#8e44ad",
    "autonomous": "#27ae60",
    "linefind":   "#16a085",
    "turnoff":    "#c0392b",
    "forward":    "#2980b9",
    "backward":   "#2980b9",
    "left":       "#2980b9",
    "right":      "#2980b9",
    "repeat":     "#f39c12",
    "loop":       "#f39c12",
    "#":          "#888888",   # comments
}

class RobotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Robot Mission Control")
        self.root.geometry("1000x640")

        self.robot_x   = 300
        self.robot_y   = 300
        self.angle     = -90
        self.executing = False
        self.connected = False

        self._build_ui()
        self._setup_mqtt()
        self._bind_keys()

    # ── MQTT ──────────────────────────────────────────────────────────────────
    def _setup_mqtt(self):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, CLIENT_ID)
        self.client.on_connect    = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message    = self._on_message
        try:
            self.client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            self.log(f"// MQTT failed: {e}")

    def _on_connect(self, c, u, f, rc):
        if rc == 0:
            self.connected = True
            self.client.subscribe(TOPIC_STATUS)
            self.root.after(0, lambda: self.conn_dot.config(fg="lime green"))
            self.root.after(0, lambda: self.log("// Connected to broker"))
        else:
            self.root.after(0, lambda: self.log(f"// Broker refused rc={rc}"))

    def _on_disconnect(self, c, u, rc):
        self.connected = False
        self.root.after(0, lambda: self.conn_dot.config(fg="red"))

    def _on_message(self, c, u, msg):
        txt = msg.payload.decode()
        self.root.after(0, lambda: self.log(f"// status: {txt}"))

    def publish(self, cmd):
        if self.connected:
            self.client.publish(TOPIC_CMD, cmd)
            self.log(f"// sent: {cmd}")
        else:
            self.log("// not connected")

    # ── COMMAND EXECUTION ─────────────────────────────────────────────────────
    def execute_cmd(self, line):
        """Parse and execute a single command line."""
        line = line.strip().lower()

        # Skip comments and blanks
        if not line or line.startswith("#") or line.startswith("//"):
            return True

        # move(forward);
        if "move(" in line:
            if "forward"  in line: self._move("forward")
            elif "backward" in line: self._move("backward")
            elif "left"   in line: self._move("left")
            elif "right"  in line: self._move("right")

        # wait(seconds);
        elif "wait(" in line:
            try:
                secs = float(line.split("(")[1].split(")")[0])
                self.log(f"// waiting {secs}s")
                time.sleep(secs)
            except Exception:
                self.log("// wait() parse error")

        # manual();
        elif "manual()" in line:
            self.log("// switching to MANUAL")
            self.publish(MANUAL_CMD)
            self.status_var.set("Mode: MANUAL")

        # autonomous();
        elif "autonomous()" in line:
            self.log("// switching to AUTONOMOUS")
            self.publish(AUTO_CMD)
            self.status_var.set("Mode: AUTONOMOUS")

        # linefind();
        elif "linefind()" in line:
            self.log("// starting line search")
            self.publish(LINE_FIND_CMD)
            self.status_var.set("Mode: LINE FIND")

        # turnoff();
        elif "turnoff()" in line:
            self.log("// sending stop")
            self.publish(STOP_CMD)
            self.status_var.set("Mode: OFF")

        else:
            self.log(f"// unknown: {line}")

        return True

    def _move(self, direction):
        rad = math.radians(self.angle)

        if direction == "forward":
            dx = math.cos(rad) * STEP_PIXELS
            dy = math.sin(rad) * STEP_PIXELS
            self.publish(build_cmd(1, DEFAULT_STEPS, DEFAULT_SPEED, 1, 0, 1, 0))
        elif direction == "backward":
            dx = -math.cos(rad) * STEP_PIXELS
            dy = -math.sin(rad) * STEP_PIXELS
            self.publish(build_cmd(1, DEFAULT_STEPS, DEFAULT_SPEED, 0, 0, 0, 0))
        elif direction == "left":
            self.angle -= TURN_DEGREES
            dx, dy = 0, 0
            self.publish(build_cmd(1, DEFAULT_STEPS, DEFAULT_SPEED, 1, 0, 1, 5))
        elif direction == "right":
            self.angle += TURN_DEGREES
            dx, dy = 0, 0
            self.publish(build_cmd(1, DEFAULT_STEPS, DEFAULT_SPEED, 1, 5, 1, 0))

        if direction in ("forward", "backward"):
            nx, ny = self.robot_x + dx, self.robot_y + dy
            self.canvas.create_line(self.robot_x, self.robot_y, nx, ny,
                                    fill="#e74c3c", width=2)
            self.robot_x, self.robot_y = nx, ny

        self.canvas.coords(self.dot,
                           self.robot_x-7, self.robot_y-7,
                           self.robot_x+7, self.robot_y+7)
        # Direction arrow
        rad2 = math.radians(self.angle)
        ax = self.robot_x + math.cos(rad2) * 12
        ay = self.robot_y + math.sin(rad2) * 12
        self.canvas.delete("arrow")
        self.canvas.create_line(self.robot_x, self.robot_y, ax, ay,
                                fill="black", width=2, arrow=tk.LAST,
                                tags="arrow")

    def parse_blocks(self, lines):
        """
        Parse lines into a flat execution list, expanding repeat/loop blocks.
        Returns list of (line_number, command_string) tuples.
        Each repeat(N){} block is expanded N times.
        loop(){} blocks are marked with sentinel for infinite loop.
        """
        result  = []
        i       = 0
        n_lines = len(lines)

        while i < n_lines:
            line    = lines[i].strip().lower()
            lineno  = i + 1

            # repeat(N) {
            if line.startswith("repeat(") and "{" in line:
                try:
                    count = int(line.split("(")[1].split(")")[0])
                except Exception:
                    count = 1
                # Collect block body until matching }
                block = []
                i += 1
                depth = 1
                block_start = i
                while i < n_lines and depth > 0:
                    bl = lines[i].strip().lower()
                    if "{" in bl: depth += 1
                    if "}" in bl: depth -= 1
                    if depth > 0:
                        block.append((i + 1, lines[i]))
                    i += 1
                # Expand block N times
                for _ in range(count):
                    result.extend(block)
                continue

            # loop() {  — infinite, runs until STOP pressed
            elif line.startswith("loop()") and "{" in line:
                block = []
                i += 1
                depth = 1
                while i < n_lines and depth > 0:
                    bl = lines[i].strip().lower()
                    if "{" in bl: depth += 1
                    if "}" in bl: depth -= 1
                    if depth > 0:
                        block.append((i + 1, lines[i]))
                    i += 1
                # Mark as infinite loop sentinel
                result.append((-1, "__loop_start__"))
                result.extend(block)
                result.append((-1, "__loop_end__"))
                continue

            # Skip bare braces
            elif line in ("{", "}"):
                i += 1
                continue

            else:
                result.append((lineno, lines[i]))
                i += 1

        return result

    def run_sequence(self):
        if self.executing:
            return
        self.executing = True
        self.run_btn.config(state=tk.DISABLED, text="EXECUTING...", bg="orange")

        raw_lines = self.code_input.get("1.0", tk.END).splitlines()
        flat      = self.parse_blocks(raw_lines)

        # Find loop boundaries
        loop_start_idx = None
        for idx, (_, cmd) in enumerate(flat):
            if cmd == "__loop_start__":
                loop_start_idx = idx

        exec_idx = 0
        while exec_idx < len(flat) and self.executing:
            lineno, cmd_str = flat[exec_idx]

            if cmd_str == "__loop_start__":
                exec_idx += 1
                continue
            if cmd_str == "__loop_end__":
                # Jump back to loop start
                exec_idx = loop_start_idx + 1
                continue

            # Highlight source line
            if lineno > 0:
                self.code_input.tag_remove("current_line", "1.0", tk.END)
                self.code_input.tag_add("current_line", f"{lineno}.0", f"{lineno}.end")
                self.root.update()

            self.execute_cmd(cmd_str)
            self.root.update()
            time.sleep(DELAY_PER_STEP)
            exec_idx += 1

        self.code_input.tag_remove("current_line", "1.0", tk.END)
        self.run_btn.config(state=tk.NORMAL, text="▶  RUN SEQUENCE", bg="#27ae60")
        self.executing = False

    def stop_sequence(self):
        self.executing = False
        self.publish(STOP_CMD)
        self.run_btn.config(state=tk.NORMAL, text="▶  RUN SEQUENCE", bg="#27ae60")
        self.log("// sequence stopped")

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Top bar
        top = tk.Frame(self.root, bg="#2c3e50", pady=4)
        top.pack(fill="x")

        tk.Label(top, text="Robot Mission Control", bg="#2c3e50", fg="white",
                 font=("Arial", 12, "bold")).pack(side="left", padx=10)

        self.conn_dot = tk.Label(top, text="●", fg="red", bg="#2c3e50",
                                 font=("Arial", 14))
        self.conn_dot.pack(side="right", padx=10)

        self.status_var = tk.StringVar(value="Mode: —")
        tk.Label(top, textvariable=self.status_var, bg="#2c3e50", fg="#ecf0f1",
                 font=("Arial", 10)).pack(side="right", padx=20)

        # Main paned window
        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashwidth=6,
                               sashrelief="raised")
        paned.pack(fill="both", expand=True)

        # ── LEFT: editor ──────────────────────────────────────────────────────
        left = tk.Frame(paned, bg="#1e1e2e")
        paned.add(left, minsize=320)

        tk.Label(left, text="Mission Script", bg="#1e1e2e", fg="#cdd6f4",
                 font=("Arial", 10, "bold")).pack(anchor="w", padx=8, pady=(6,2))

        # Reference card
        ref = tk.LabelFrame(left, text="Commands", bg="#1e1e2e", fg="#888",
                            font=("Courier New", 8))
        ref.pack(fill="x", padx=6, pady=(0,4))
        cmds = [
            "move(forward);    move(backward);",
            "move(left);       move(right);",
            "wait(seconds);    // e.g. wait(3);",
            "manual();         autonomous();",
            "linefind();       turnoff();",
            "repeat(N) { }     // run N times",
            "loop() { }        // run forever",
        ]
        for c in cmds:
            tk.Label(ref, text=c, bg="#1e1e2e", fg="#6c7086",
                     font=("Courier New", 8), anchor="w").pack(anchor="w", padx=4)

        # Code editor
        code_frame = tk.Frame(left, bg="#1e1e2e")
        code_frame.pack(fill="both", expand=True, padx=6)

        self.code_input = tk.Text(code_frame, font=("Courier New", 11),
                                  bg="#181825", fg="#cdd6f4",
                                  insertbackground="#cdd6f4",
                                  selectbackground="#45475a",
                                  relief="flat", undo=True)
        self.code_input.tag_config("current_line", background="#313244")
        scroll = tk.Scrollbar(code_frame, command=self.code_input.yview)
        self.code_input.configure(yscrollcommand=scroll.set)
        self.code_input.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.code_input.insert("1.0",
            "// Example mission\n"
            "autonomous();\n"
            "wait(5);\n"
            "manual();\n"
            "repeat(3) {\n"
            "    move(forward);\n"
            "    move(left);\n"
            "}\n"
            "wait(2);\n"
            "loop() {\n"
            "    move(forward);\n"
            "    move(right);\n"
            "}\n"
        )
        self.code_input.bind("<KeyRelease>", self._highlight)

        # Buttons
        btn_frame = tk.Frame(left, bg="#1e1e2e")
        btn_frame.pack(fill="x", padx=6, pady=6)

        self.run_btn = tk.Button(btn_frame, text="▶  RUN SEQUENCE",
                                 bg="#27ae60", fg="white",
                                 font=("Arial", 10, "bold"),
                                 relief="flat", command=self.run_sequence)
        self.run_btn.pack(fill="x", pady=(0,4))

        tk.Button(btn_frame, text="⬛  STOP", bg="#e74c3c", fg="white",
                  font=("Arial", 10, "bold"), relief="flat",
                  command=self.stop_sequence).pack(fill="x", pady=(0,4))

        tk.Button(btn_frame, text="Clear Map", bg="#45475a", fg="white",
                  relief="flat", command=self.reset_map).pack(fill="x")

        # Log
        log_frame = tk.Frame(left, bg="#1e1e2e")
        log_frame.pack(fill="x", padx=6, pady=(4,6))
        self.log_box = tk.Text(log_frame, height=5, bg="#11111b", fg="#a6e3a1",
                               font=("Courier New", 8), state="disabled",
                               relief="flat")
        self.log_box.pack(fill="x")

        # ── RIGHT: map canvas ─────────────────────────────────────────────────
        right = tk.Frame(paned, bg="white")
        paned.add(right, minsize=400)

        tk.Label(right, text="Map View", bg="#ecf0f1",
                 font=("Arial", 9, "bold")).pack(anchor="w", padx=6, pady=2)

        self.canvas = tk.Canvas(right, bg="white", relief="flat")
        self.canvas.pack(fill="both", expand=True, padx=6, pady=6)

        # Grid
        for x in range(0, 800, 30):
            self.canvas.create_line(x, 0, x, 800, fill="#f0f0f0")
        for y in range(0, 800, 30):
            self.canvas.create_line(0, y, 800, y, fill="#f0f0f0")

        # Robot dot + arrow
        self.dot = self.canvas.create_oval(
            self.robot_x-7, self.robot_y-7,
            self.robot_x+7, self.robot_y+7,
            fill="#e74c3c", outline="#c0392b", width=2
        )
        self.canvas.create_line(self.robot_x, self.robot_y,
                                self.robot_x, self.robot_y-14,
                                fill="black", width=2, arrow=tk.LAST,
                                tags="arrow")

    def _highlight(self, event=None):
        """Simple syntax highlighting."""
        self.code_input.tag_delete("kw")
        content = self.code_input.get("1.0", tk.END)
        for kw, color in KEYWORDS.items():
            start = "1.0"
            while True:
                pos = self.code_input.search(kw, start, stopindex=tk.END)
                if not pos:
                    break
                end = f"{pos}+{len(kw)}c"
                tag = f"kw_{kw}"
                self.code_input.tag_config(tag, foreground=color)
                self.code_input.tag_add(tag, pos, end)
                start = end

    def _bind_keys(self):
        self.root.bind("<F5>", lambda e: self.run_sequence())
        self.root.bind("<Escape>", lambda e: self.stop_sequence())

    def log(self, msg):
        self.log_box.config(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def reset_map(self):
        self.canvas.delete("all")
        # Redraw grid
        for x in range(0, 800, 30):
            self.canvas.create_line(x, 0, x, 800, fill="#f0f0f0")
        for y in range(0, 800, 30):
            self.canvas.create_line(0, y, 800, y, fill="#f0f0f0")
        self.robot_x, self.robot_y = 300, 300
        self.angle = -90
        self.dot = self.canvas.create_oval(
            self.robot_x-7, self.robot_y-7,
            self.robot_x+7, self.robot_y+7,
            fill="#e74c3c", outline="#c0392b", width=2
        )

    def on_close(self):
        self.publish(STOP_CMD)
        self.client.loop_stop()
        self.client.disconnect()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = RobotGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()