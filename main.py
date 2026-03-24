import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import serial
import serial.tools.list_ports
import time
import threading
import json
import os

# --- THEME CONFIGURATION ---
ctk.set_appearance_mode("Dark")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

# Custom Colors
COLOR_DANGER = "#C62828"
COLOR_DANGER_HOVER = "#B71C1C"
COLOR_SUCCESS = "#2E7D32"
COLOR_WARNING = "#F9A825"
COLOR_PANEL = "#2B2B2B"


class RobotArmGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("ROBOT ARM PRO - PRECISION DASHBOARD")
        self.geometry("1100x800")
        self.minsize(900, 700)

        # Logical Variables (Kept exactly as your original)
        self.ser = None
        self.is_connected = False
        self.serial_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.pick_points = []
        self.place_points = []
        self.home_position = {'j1': 0.00, 'j2': 0.00, 'z': 0.00, 'grip': 0.00}

        self._init_ui()

    def _init_ui(self):
        # Grid Layout: 1 column for sidebar, 1 for main content
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main_area()

    def _build_sidebar(self):
        # Sidebar Frame
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1)  # Spacer

        # Logo / Title
        logo_label = ctk.CTkLabel(self.sidebar_frame, text="ROBOT ARM\nPRO", font=ctk.CTkFont(size=24, weight="bold"))
        logo_label.grid(row=0, column=0, padx=20, pady=(30, 20))

        # --- CONNECTION CARD ---
        conn_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        conn_frame.grid(row=1, column=0, padx=15, pady=10, sticky="ew")

        ctk.CTkLabel(conn_frame, text="CONNECTION", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray").pack(
            anchor="w", pady=(0, 5))

        self.combo_ports = ctk.CTkOptionMenu(conn_frame, values=[])
        self.combo_ports.pack(fill="x", pady=5)
        self.refresh_ports()

        btn_refresh = ctk.CTkButton(conn_frame, text="↻ Refresh Ports", fg_color="#444444", hover_color="#555555",
                                    command=self.refresh_ports)
        btn_refresh.pack(fill="x", pady=(0, 5))

        self.btn_connect = ctk.CTkButton(conn_frame, text="CONNECT", font=ctk.CTkFont(weight="bold"),
                                         command=self.toggle_connection)
        self.btn_connect.pack(fill="x", pady=5)

        # --- DATA MANAGEMENT CARD ---
        data_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        data_frame.grid(row=2, column=0, padx=15, pady=30, sticky="ew")

        ctk.CTkLabel(data_frame, text="DATA MANAGEMENT", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="gray").pack(anchor="w", pady=(0, 5))

        ctk.CTkButton(data_frame, text="💾 Save Workspace", fg_color="#1E88E5", hover_color="#1565C0",
                      command=self.save_data_to_file).pack(fill="x", pady=5)
        ctk.CTkButton(data_frame, text="📂 Load Workspace", fg_color="#43A047", hover_color="#2E7D32",
                      command=self.load_data_from_file).pack(fill="x", pady=5)

    def _build_main_area(self):
        self.main_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.main_frame.grid_columnconfigure((0, 1), weight=1)

        # --- EMERGENCY STOP ---
        self.btn_stop = ctk.CTkButton(self.main_frame, text="⚠ EMERGENCY STOP ⚠",
                                      font=ctk.CTkFont(size=20, weight="bold"),
                                      fg_color=COLOR_DANGER, hover_color=COLOR_DANGER_HOVER,
                                      height=60, corner_radius=8, command=self.emergency_stop)
        self.btn_stop.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 20))

        # --- KINEMATICS CONTROL (LEFT SIDE) ---
        self.manual_frame = ctk.CTkFrame(self.main_frame, corner_radius=15)
        self.manual_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        ctk.CTkLabel(self.manual_frame, text="FORWARD KINEMATICS (MANUAL)",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=20, pady=(15, 10))

        self.slider_j1 = self._create_modern_slider(self.manual_frame, "Joint 1 (J1)", -180, 180,
                                                    self.home_position['j1'], 0.5)
        self.slider_j2 = self._create_modern_slider(self.manual_frame, "Joint 2 (J2)", -180, 180,
                                                    self.home_position['j2'], 0.5)
        self.slider_z = self._create_modern_slider(self.manual_frame, "Z-Axis", 0, 100, self.home_position['z'], 0.5)
        self.slider_grip = self._create_modern_slider(self.manual_frame, "Gripper", 0.0, 75, self.home_position['grip'],
                                                      1.0)

        btn_row = ctk.CTkFrame(self.manual_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=20)

        self.btn_move = ctk.CTkButton(btn_row, text="MOVE TO POS", height=40, font=ctk.CTkFont(weight="bold"),
                                      command=self.send_current_pos)
        self.btn_move.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.btn_home = ctk.CTkButton(btn_row, text="GO HOME", height=40, fg_color="#00509E",
                                      font=ctk.CTkFont(weight="bold"), command=self.go_to_home)
        self.btn_home.pack(side="left", fill="x", expand=True, padx=(5, 0))

        # --- TEACH & AUTO CYCLE (RIGHT SIDE) ---
        right_panel = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        right_panel.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)

        # 1. Teach Points Card
        teach_card = ctk.CTkFrame(right_panel, corner_radius=15)
        teach_card.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(teach_card, text="TEACH POINTS", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w",
                                                                                                     padx=20,
                                                                                                     pady=(15, 5))

        # Pick Controls
        pick_frame = ctk.CTkFrame(teach_card, fg_color=COLOR_PANEL, corner_radius=10)
        pick_frame.pack(fill="x", padx=15, pady=10)
        ctk.CTkLabel(pick_frame, text="PICK LOCATIONS", font=ctk.CTkFont(weight="bold"), text_color="#64B5F6").pack(
            anchor="w", padx=10, pady=(5, 0))

        p_row = ctk.CTkFrame(pick_frame, fg_color="transparent")
        p_row.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(p_row, text="SAVE", width=60, command=self.add_pick_point).pack(side="left", padx=2)
        ctk.CTkButton(p_row, text="GOTO", width=60, fg_color="#1E88E5", command=self.goto_last_pick).pack(side="left",
                                                                                                          padx=2)
        ctk.CTkButton(p_row, text="UNDO", width=60, fg_color=COLOR_WARNING, text_color="black", hover_color="#FBC02D",
                      command=self.undo_pick_point).pack(side="left", padx=2)
        ctk.CTkButton(p_row, text="CLEAR", width=60, fg_color="gray", command=self.reset_pick_points).pack(side="left",
                                                                                                           padx=2)
        self.lbl_pick_count = ctk.CTkLabel(pick_frame, text="Saved: 0", font=ctk.CTkFont(weight="bold"))
        self.lbl_pick_count.pack(anchor="e", padx=10, pady=(0, 5))

        # Place Controls
        place_frame = ctk.CTkFrame(teach_card, fg_color=COLOR_PANEL, corner_radius=10)
        place_frame.pack(fill="x", padx=15, pady=(0, 15))
        ctk.CTkLabel(place_frame, text="PLACE LOCATIONS", font=ctk.CTkFont(weight="bold"), text_color="#81C784").pack(
            anchor="w", padx=10, pady=(5, 0))

        pl_row = ctk.CTkFrame(place_frame, fg_color="transparent")
        pl_row.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(pl_row, text="SAVE", width=60, command=self.add_place_point).pack(side="left", padx=2)
        ctk.CTkButton(pl_row, text="GOTO", width=60, fg_color="#1E88E5", command=self.goto_last_place).pack(side="left",
                                                                                                            padx=2)
        ctk.CTkButton(pl_row, text="UNDO", width=60, fg_color=COLOR_WARNING, text_color="black", hover_color="#FBC02D",
                      command=self.undo_place_point).pack(side="left", padx=2)
        ctk.CTkButton(pl_row, text="CLEAR", width=60, fg_color="gray", command=self.reset_place_points).pack(
            side="left", padx=2)
        self.lbl_place_count = ctk.CTkLabel(place_frame, text="Saved: 0", font=ctk.CTkFont(weight="bold"))
        self.lbl_place_count.pack(anchor="e", padx=10, pady=(0, 5))

        # 2. Automation Loop Card
        auto_card = ctk.CTkFrame(right_panel, corner_radius=15)
        auto_card.pack(fill="x")
        ctk.CTkLabel(auto_card, text="AUTOMATION LOOP", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w",
                                                                                                       padx=20,
                                                                                                       pady=(15, 5))

        row = ctk.CTkFrame(auto_card, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(5, 15))
        ctk.CTkLabel(row, text="Safe Z-Axis:").pack(side="left")

        self.entry_zsafe = ctk.CTkEntry(row, width=80, justify='center')
        self.entry_zsafe.insert(0, "10.00")
        self.entry_zsafe.pack(side="left", padx=10)

        self.btn_run = ctk.CTkButton(row, text="▶ RUN PROGRAM", fg_color=COLOR_SUCCESS, hover_color="#1B5E20",
                                     font=ctk.CTkFont(weight="bold"), command=self.start_auto_cycle)
        self.btn_run.pack(side="right", fill="x", expand=True)

        # --- LOG CONSOLE ---
        log_frame = ctk.CTkFrame(self.main_frame, corner_radius=15)
        log_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=10)
        ctk.CTkLabel(log_frame, text="SYSTEM LOGS", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray").pack(
            anchor="w", padx=20, pady=(10, 0))

        self.log_text = ctk.CTkTextbox(log_frame, height=120, fg_color="#1A1A1A", text_color="#A9B7C6",
                                       font=("Consolas", 12))
        self.log_text.pack(fill="both", expand=True, padx=15, pady=15)
        self.log_text.configure(state='disabled')

    def _create_modern_slider(self, parent, label, min_val, max_val, default, step=0.5):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(fill="x", padx=20, pady=8)

        header = ctk.CTkFrame(box, fg_color="transparent")
        header.pack(fill="x")

        ctk.CTkLabel(header, text=label, font=ctk.CTkFont(weight="bold")).pack(side="left")

        var_dict = {'val': default}

        # Value Entry
        entry = ctk.CTkEntry(header, width=70, justify="center")
        entry.insert(0, f"{default:.2f}")
        entry.pack(side="right", padx=(5, 0))

        # Plus / Minus Buttons
        btn_plus = ctk.CTkButton(header, text="+", width=30, fg_color="#444444", command=lambda: adjust_val(step))
        btn_plus.pack(side="right", padx=(2, 0))

        btn_minus = ctk.CTkButton(header, text="-", width=30, fg_color="#444444", command=lambda: adjust_val(-step))
        btn_minus.pack(side="right", padx=(5, 2))

        # The Slider Widget
        slider = ctk.CTkSlider(box, from_=min_val, to=max_val, command=lambda v: update_from_slider(v))
        slider.set(default)
        slider.pack(fill="x", pady=(10, 0))

        def update_ui():
            entry.delete(0, tk.END)
            entry.insert(0, f"{var_dict['val']:.2f}")
            slider.set(var_dict['val'])

        def adjust_val(amount):
            new_val = round(var_dict['val'] + amount, 2)
            if new_val < min_val: new_val = min_val
            if new_val > max_val: new_val = max_val
            var_dict['val'] = new_val
            update_ui()

        def update_from_slider(value):
            var_dict['val'] = round(value, 2)
            entry.delete(0, tk.END)
            entry.insert(0, f"{var_dict['val']:.2f}")

        def on_entry_submit(event):
            try:
                val = float(entry.get())
                if val < min_val: val = min_val
                if val > max_val: val = max_val
                var_dict['val'] = round(val, 2)
                update_ui()
            except ValueError:
                pass

        entry.bind("<Return>", on_entry_submit)

        # Attach our custom var_dict dictionary to the slider object so we can read it later
        slider.var_dict = var_dict
        slider.update_ui = update_ui  # Expose method to update manually
        return slider

    # ================= LOGIC FUNCTIONS (Kept Exact Same as Original) =================

    def log(self, msg):
        self.log_text.configure(state='normal')
        self.log_text.insert('end', f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def refresh_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        ports.append("socket://192.168.1.100:5000")
        self.combo_ports.configure(values=ports)
        if ports: self.combo_ports.set(ports[0])

    def toggle_connection(self):
        if not self.is_connected:
            try:
                port = self.combo_ports.get()
                self.ser = serial.serial_for_url(port, baudrate=9600, timeout=1)
                time.sleep(2)
                self.is_connected = True
                self.btn_connect.configure(text="DISCONNECT", fg_color=COLOR_DANGER, hover_color=COLOR_DANGER_HOVER)
                self.log(f"Connected to {port}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
        else:
            if self.ser: self.ser.close()
            self.is_connected = False
            self.btn_connect.configure(text="CONNECT", fg_color=COLOR_SUCCESS, hover_color="#1B5E20")
            self.log("Disconnected")

    def emergency_stop(self):
        self.stop_event.set()
        if self.ser and self.is_connected:
            with self.serial_lock:
                self.ser.write(b"STOP\n")
        self.log("!!! STOP SIGNAL SENT !!!")

    def send_command(self, j1, j2, z, grip, wait=False):
        if not self.is_connected: return
        cmd = f"{float(j1):.2f},{float(j2):.2f},{float(z):.2f},{int(grip)}\n"
        try:
            with self.serial_lock:
                if wait: self.ser.reset_input_buffer()
                self.ser.write(cmd.encode())
                if not wait:
                    self.log(f"Move -> {cmd.strip()}")
            if wait:
                self.wait_for_robot()
        except Exception as e:
            self.log(f"TX Error: {e}")

    def wait_for_robot(self):
        start_time = time.time()
        while not self.stop_event.is_set():
            if self.ser.in_waiting:
                try:
                    line = self.ser.readline().decode().strip()
                    if line == "DONE": return
                except:
                    pass
            if time.time() - start_time > 15:
                break
            time.sleep(0.05)

    def send_current_pos(self):
        self.send_command(self.slider_j1.var_dict['val'], self.slider_j2.var_dict['val'],
                          self.slider_z.var_dict['val'], self.slider_grip.var_dict['val'], wait=False)

    def go_to_home(self):
        h = self.home_position
        self.slider_j1.var_dict['val'] = h['j1']
        self.slider_j2.var_dict['val'] = h['j2']
        self.slider_z.var_dict['val'] = h['z']
        self.slider_grip.var_dict['val'] = h['grip']

        self.slider_j1.update_ui()
        self.slider_j2.update_ui()
        self.slider_z.update_ui()
        self.slider_grip.update_ui()

        self.log("Going to HOME position...")
        self.send_command(h['j1'], h['j2'], h['z'], h['grip'], wait=False)

    def add_pick_point(self):
        pos = {
            'j1': self.slider_j1.var_dict['val'],
            'j2': self.slider_j2.var_dict['val'],
            'z': self.slider_z.var_dict['val'],
            'grip': self.slider_grip.var_dict['val']
        }
        self.pick_points.append(pos)
        self.lbl_pick_count.configure(text=f"Saved: {len(self.pick_points)}")
        self.log(f"Added Exact Pick #{len(self.pick_points)}")

    def undo_pick_point(self):
        if self.pick_points:
            self.pick_points.pop()
            self.lbl_pick_count.configure(text=f"Saved: {len(self.pick_points)}")
            self.log("Removed last Pick point")

    def goto_last_pick(self):
        if not self.pick_points: return
        pt = self.pick_points[-1]
        self.send_command(pt['j1'], pt['j2'], pt['z'], pt['grip'], wait=False)

    def reset_pick_points(self):
        self.pick_points = []
        self.lbl_pick_count.configure(text="Saved: 0")
        self.log("Cleared picks")

    def add_place_point(self):
        pos = {
            'j1': self.slider_j1.var_dict['val'],
            'j2': self.slider_j2.var_dict['val'],
            'z': self.slider_z.var_dict['val'],
            'grip': self.slider_grip.var_dict['val']
        }
        self.place_points.append(pos)
        self.lbl_place_count.configure(text=f"Saved: {len(self.place_points)}")
        self.log(f"Added Exact Place #{len(self.place_points)}")

    def undo_place_point(self):
        if self.place_points:
            self.place_points.pop()
            self.lbl_place_count.configure(text=f"Saved: {len(self.place_points)}")
            self.log("Removed last Place point")

    def goto_last_place(self):
        if not self.place_points: return
        pt = self.place_points[-1]
        self.send_command(pt['j1'], pt['j2'], pt['z'], pt['grip'], wait=False)

    def reset_place_points(self):
        self.place_points = []
        self.lbl_place_count.configure(text="Saved: 0")
        self.log("Cleared places")

    def save_data_to_file(self):
        if not self.pick_points and not self.place_points:
            messagebox.showwarning("Warning", "No data to save!")
            return
        data = {
            "pick_points": self.pick_points,
            "place_points": self.place_points,
            "z_safe": self.entry_zsafe.get()
        }
        try:
            with open("robot_data.json", "w") as f:
                json.dump(data, f, indent=4)
            messagebox.showinfo("Success", "Data Saved to 'robot_data.json'")
            self.log("Data Saved Successfully")
        except Exception as e:
            messagebox.showerror("Error", f"Save Failed: {e}")

    def load_data_from_file(self):
        if not os.path.exists("robot_data.json"):
            messagebox.showwarning("Error", "File 'robot_data.json' not found!")
            return
        try:
            with open("robot_data.json", "r") as f:
                data = json.load(f)

            self.pick_points = data.get("pick_points", [])
            self.place_points = data.get("place_points", [])

            self.lbl_pick_count.configure(text=f"Saved: {len(self.pick_points)}")
            self.lbl_place_count.configure(text=f"Saved: {len(self.place_points)}")

            if "z_safe" in data:
                self.entry_zsafe.delete(0, tk.END)
                self.entry_zsafe.insert(0, data["z_safe"])

            self.log("Data Loaded Successfully")
        except Exception as e:
            messagebox.showerror("Error", f"Load Failed: {e}")

    def start_auto_cycle(self):
        if not self.is_connected:
            messagebox.showwarning("Connection", "Please Connect First!")
            return
        if not self.pick_points or not self.place_points:
            messagebox.showwarning("Data Missing", "Need at least 1 Pick AND 1 Place point.")
            return

        self.stop_event.clear()
        self.log(f">>> STARTING LOOP <<<")
        threading.Thread(target=self.run_sequence, daemon=True).start()

    def run_sequence(self):
        self.btn_run.configure(state='disabled', text="RUNNING...")
        try:
            z_safe = float(self.entry_zsafe.get())
            step_index = 0
            while not self.stop_event.is_set():
                current_pick = self.pick_points[step_index % len(self.pick_points)]
                current_place = self.place_points[step_index % len(self.place_points)]

                grip_close = current_pick['grip']
                grip_open = current_place['grip']

                step_display = step_index + 1
                self.log(f"--- Cycle #{step_display}: Grip={grip_close}, Rel={grip_open} ---")

                self.send_command(current_pick['j1'], current_pick['j2'], z_safe, grip_open, wait=True)
                self.send_command(current_pick['j1'], current_pick['j2'], current_pick['z'], grip_open, wait=True)
                self.send_command(current_pick['j1'], current_pick['j2'], current_pick['z'], grip_close, wait=True)
                time.sleep(0.5)
                self.send_command(current_pick['j1'], current_pick['j2'], z_safe, grip_close, wait=True)
                self.send_command(current_place['j1'], current_place['j2'], z_safe, grip_close, wait=True)
                self.send_command(current_place['j1'], current_place['j2'], current_place['z'], grip_close, wait=True)
                self.send_command(current_place['j1'], current_place['j2'], current_place['z'], grip_open, wait=True)
                time.sleep(0.5)
                self.send_command(current_place['j1'], current_place['j2'], z_safe, grip_open, wait=True)

                step_index += 1
                time.sleep(0.2)

            self.log(">>> LOOP STOPPED <<<")
        except Exception as e:
            self.log(f"Loop Error: {e}")
        finally:
            self.btn_run.configure(state='normal', text="▶ RUN PROGRAM")


if __name__ == "__main__":
    app = RobotArmGUI()
    app.mainloop()