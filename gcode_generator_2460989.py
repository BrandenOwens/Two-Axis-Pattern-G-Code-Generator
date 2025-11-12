#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List, Tuple, Optional

# --- plotting deps ---
try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
except Exception as e:
    raise SystemExit("This program needs matplotlib. Install it with: pip install matplotlib") from e

# --------------------------- helpers ---------------------------

TOL = 1e-9

def fmt_number(s: str) -> str:
    s = s.strip()
    if not s:
        return ""
    try:
        v = float(s)
        if abs(v - int(v)) < 1e-9:
            return str(int(v))
        return f"{v:.6f}".rstrip("0").rstrip(".")
    except ValueError:
        return ""

def parse_float(s: str, default=None):
    try:
        return float(s)
    except Exception:
        return default

def build_preview_line(x: str, y: str) -> str:
    x = fmt_number(x); y = fmt_number(y)
    if x and y:   return f"G1 X{x} Y{y}"
    if x:         return f"G1 X{x} Y?"
    if y:         return f"G1 X? Y{y}"
    return "G1 X? Y?"

def parse_g1_xy(line: str) -> Optional[Tuple[float, float]]:
    """
    Parse X and Y from a G-code-ish line. Ignores comments and M3/M5.
    Returns (x, y) or None if either is missing.
    """
    if ';' in line: line = line.split(';', 1)[0]
    if '#' in line: line = line.split('#', 1)[0]
    line = line.strip()
    if not line: return None
    U = line.upper()
    if U.startswith("M3") or U.startswith("M5"):
        return None
    x_val = None; y_val = None
    for token in line.replace(',', ' ').split():
        t = token.upper()
        if t.startswith("X"):
            try: x_val = float(token[1:])
            except ValueError: return None
        elif t.startswith("Y"):
            try: y_val = float(token[1:])
            except ValueError: return None
    if x_val is None or y_val is None:
        return None
    return (x_val, y_val)

def _eq(a: float, b: float, tol: float = TOL) -> bool:
    return abs(a - b) <= tol

# --------------------------- global state ---------------------------

gcode_lines: List[str] = []
last_snapshot: Optional[List[str]] = None

def snapshot():
    global last_snapshot
    last_snapshot = list(gcode_lines)

def restore_snapshot():
    global last_snapshot, gcode_lines
    if last_snapshot is None:
        return
    gcode_lines = list(last_snapshot)
    lines_listbox.delete(0, tk.END)
    for ln in gcode_lines:
        lines_listbox.insert(tk.END, ln)
    redraw_plot()

# --------------------------- core add/merge ---------------------------

def add_or_merge_line(xn: float, yn: float):
    """
    Append 'G1 X.. Y..', but if this would create 3+ consecutive lines
    with the SAME Y (horizontal) or SAME X (vertical), merge into last line.
    """
    new_text = f"G1 X{fmt_number(str(xn))} Y{fmt_number(str(yn))}"

    last_xy = parse_g1_xy(gcode_lines[-1]) if len(gcode_lines) >= 1 else None
    prev_xy = parse_g1_xy(gcode_lines[-2]) if len(gcode_lines) >= 2 else None

    # horizontal run (Y==Y==Y) -> update last line
    if last_xy and prev_xy and _eq(last_xy[1], yn) and _eq(prev_xy[1], yn):
        gcode_lines[-1] = new_text
        lines_listbox.delete(tk.END)
        lines_listbox.insert(tk.END, new_text)
        return

    # vertical run (X==X==X) -> update last line
    if last_xy and prev_xy and _eq(last_xy[0], xn) and _eq(prev_xy[0], xn):
        gcode_lines[-1] = new_text
        lines_listbox.delete(tk.END)
        lines_listbox.insert(tk.END, new_text)
        return

    # else append
    gcode_lines.append(new_text)
    lines_listbox.insert(tk.END, new_text)

# --------------------------- actions ---------------------------

def update_preview(*_):
    gcode_preview.set(build_preview_line(x_var.get(), y_var.get()))

def submit_line(event=None):
    x_txt = fmt_number(x_var.get()); y_txt = fmt_number(y_var.get())
    if not x_txt or not y_txt:
        messagebox.showwarning("Missing values", "Enter valid numeric values for both X and Y.")
        return
    snapshot()
    xn, yn = float(x_txt), float(y_txt)
    add_or_merge_line(xn, yn)
    update_preview(); redraw_plot()
    x_entry.focus_set(); x_entry.icursor(tk.END)

def undo_last():
    restore_snapshot()

def remove_selected():
    sel = list(lines_listbox.curselection())
    if not sel: return
    snapshot()
    for idx in reversed(sel):
        lines_listbox.delete(idx); del gcode_lines[idx]
    redraw_plot()

def clear_all_lines():
    if not gcode_lines: return
    if not messagebox.askyesno("Clear all", "Remove all G-code lines?"): return
    snapshot()
    gcode_lines.clear(); lines_listbox.delete(0, tk.END); redraw_plot()

def copy_current_preview():
    app.clipboard_clear(); app.clipboard_append(gcode_preview.get())

def save_gcode():
    if not gcode_lines:
        messagebox.showwarning("Nothing to save", "Add at least one G-code line (Submit) before saving.")
        return
    first = gcode_lines[0]
    if " F" not in first and "\tF" not in first:
        first = first + " F200"
    lines_to_save = ["M3", first] + gcode_lines[1:] + ["M5"]
    path = filedialog.asksaveasfilename(
        title="Save G-Code", defaultextension=".txt",
        filetypes=[("Text Files","*.txt"),("All Files","*.*")],
        initialfile="gcode_output.txt"
    )
    if not path: return
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines_to_save) + "\n")
        messagebox.showinfo("Saved", f"G-code saved to:\n{path}")
    except Exception as e:
        messagebox.showerror("Error", f"Could not save file:\n{e}")

def load_gcode():
    path = filedialog.askopenfilename(
        title="Load G-Code",
        filetypes=[("Text or G-code", "*.txt *.gcode *.nc *.tap *.job"), ("All Files", "*.*")]
    )
    if not path: 
        return
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw_lines = f.readlines()
    except Exception as e:
        messagebox.showerror("Error", f"Could not read file:\n{e}")
        return

    parsed: List[Tuple[float, float]] = []
    skipped = 0
    for ln in raw_lines:
        xy = parse_g1_xy(ln)
        if xy is None: skipped += 1
        else: parsed.append(xy)

    if not parsed:
        messagebox.showwarning("No X/Y found", "No usable X/Y moves were found in that file.")
        return

    do_replace = messagebox.askyesno(
        "Import", 
        f"Found {len(parsed)} X/Y moves (skipped {skipped}).\n\nReplace current lines?\n\nYes = Replace\nNo  = Append"
    )

    snapshot()
    if do_replace:
        gcode_lines.clear()
        lines_listbox.delete(0, tk.END)

    for xn, yn in parsed:
        add_or_merge_line(float(xn), float(yn))

    redraw_plot()
    messagebox.showinfo("Loaded", f"Imported {len(parsed)} lines (skipped {skipped}).")

def loop_block():
    """
    Use the CURRENT gcode_lines as the base block, then append offset copies:
      new_line = G1 X(x+ΔX*k) Y(y+ΔY*k)
    Repeat until any newly generated line would exceed MaxX or MaxY.
    """
    if not gcode_lines:
        messagebox.showwarning("Nothing to loop", "Submit at least one G-code line before looping.")
        return
    max_x = parse_float(max_x_var.get(), None)
    max_y = parse_float(max_y_var.get(), None)
    dx = parse_float(dx_var.get(), 0.0)
    dy = parse_float(dy_var.get(), 0.0)
    if max_x is None and max_y is None:
        messagebox.showwarning("No limits", "Enter at least Max X or Max Y as a stopping limit.")
        return

    # Base snapshot (so new lines don't change the base while looping)
    base_block = []
    for line in list(gcode_lines):
        xy = parse_g1_xy(line)
        if xy is None:
            messagebox.showerror("Parse error", f"Could not parse line:\n{line}")
            return
        base_block.append(xy)

    snapshot()
    k = 1; appended = 0
    while True:
        next_group = []
        violates = False
        for x0, y0 in base_block:
            xn, yn = x0 + dx*k, y0 + dy*k
            if max_x is not None and xn > max_x: violates = True; break
            if max_y is not None and yn > max_y: violates = True; break
            next_group.append((xn, yn))
        if violates or not next_group: break
        for xn, yn in next_group:
            add_or_merge_line(xn, yn)
        appended += 1; k += 1
    if appended == 0:
        messagebox.showinfo("Loop", "No additional groups appended (limits already reached).")
    redraw_plot()

# --------------------------- plotting ---------------------------

def collect_points(lines: List[str]) -> List[Tuple[float, float]]:
    pts = []
    for ln in lines:
        xy = parse_g1_xy(ln)
        if xy is not None: pts.append(xy)
    return pts

def apply_axes_limits():
    xmin = parse_float(xmin_var.get(), None)
    xmax = parse_float(xmax_var.get(), None)
    ymin = parse_float(ymin_var.get(), None)
    ymax = parse_float(ymax_var.get(), None)

    if None not in (xmin, xmax) and xmax > xmin:
        ax.set_xlim(xmin, xmax)
    else:
        ax.autoscale(enable=True, axis="x", tight=False)

    if None not in (ymin, ymax) and ymax > ymin:
        ax.set_ylim(ymin, ymax)
    else:
        ax.autoscale(enable=True, axis="y", tight=False)

    if lock_aspect_var.get():
        ax.set_aspect("equal", adjustable="datalim")
    else:
        ax.set_aspect("auto")

def redraw_plot():
    pts = collect_points(gcode_lines)
    ax.clear()
    ax.grid(True, which="both", linewidth=0.5)
    ax.set_title("Path preview (X/Y)")
    if len(pts) >= 1:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs, ys, linewidth=1.6)  # lines only
        # default padding if no manual limits
        if all(v.get()=="" for v in (xmin_var, xmax_var, ymin_var, ymax_var)):
            xmin, xmax = min(xs), max(xs)
            ymin, ymax = min(ys), max(ys)
            pad_x = max(1.0, (xmax - xmin) * 0.05) if xmax != xmin else 1.0
            pad_y = max(1.0, (ymax - ymin) * 0.05) if ymax != ymin else 1.0
            ax.set_xlim(xmin - pad_x, xmax + pad_x)
            ax.set_ylim(ymin - pad_y, ymax + pad_y)
    else:
        ax.set_xlim(0,10); ax.set_ylim(0,10)

    apply_axes_limits()
    canvas.draw_idle()

def apply_manual_scale():
    redraw_plot()

def auto_scale():
    xmin_var.set(""); xmax_var.set(""); ymin_var.set(""); ymax_var.set("")
    redraw_plot()

# --------------------------- UI ---------------------------

app = tk.Tk()
app.title("G-Code Generator")

# layout
app.columnconfigure(0, weight=0)
app.columnconfigure(1, weight=1)
app.rowconfigure(0, weight=1)

left = ttk.Frame(app, padding=12)
left.grid(row=0, column=0, sticky="nsw")
right = ttk.Frame(app, padding=12)
right.grid(row=0, column=1, sticky="nsew")
right.rowconfigure(4, weight=1)
right.columnconfigure(0, weight=1)

# --- Left: inputs & controls ---
ttk.Label(left, text="Inputs", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2, pady=(0,8), sticky="w")

x_var = tk.StringVar()
y_var = tk.StringVar()

ttk.Label(left, text="X:").grid(row=1, column=0, sticky="e", padx=(0,6))
x_entry = ttk.Entry(left, textvariable=x_var, width=12)
x_entry.grid(row=1, column=1, pady=4, sticky="w")

ttk.Label(left, text="Y:").grid(row=2, column=0, sticky="e", padx=(0,6))
y_entry = ttk.Entry(left, textvariable=y_var, width=12)
y_entry.grid(row=2, column=1, pady=4, sticky="w")

btns = ttk.Frame(left)
btns.grid(row=3, column=0, columnspan=2, pady=(10,0), sticky="w")
ttk.Button(btns, text="Submit line", command=submit_line).grid(row=0, column=0, padx=(0,8))
ttk.Button(btns, text="Copy preview", command=copy_current_preview).grid(row=0, column=1, padx=(0,8))

# Loop controls
loop_frame = ttk.Labelframe(left, text="Loop builder", padding=10)
loop_frame.grid(row=4, column=0, columnspan=2, pady=(16,0), sticky="ew")

max_x_var = tk.StringVar(value="82")
max_y_var = tk.StringVar(value="")
dx_var = tk.StringVar(value="2.25")
dy_var = tk.StringVar(value="0")

row = 0
ttk.Label(loop_frame, text="Max X:").grid(row=row, column=0, sticky="e", padx=(0,6))
ttk.Entry(loop_frame, textvariable=max_x_var, width=10).grid(row=row, column=1, sticky="w")
row += 1
ttk.Label(loop_frame, text="Max Y (optional):").grid(row=row, column=0, sticky="e", padx=(0,6))
ttk.Entry(loop_frame, textvariable=max_y_var, width=10).grid(row=row, column=1, sticky="w")
row += 1
ttk.Label(loop_frame, text="ΔX (offset per group):").grid(row=row, column=0, sticky="e", padx=(0,6))
ttk.Entry(loop_frame, textvariable=dx_var, width=10).grid(row=row, column=1, sticky="w")
row += 1
ttk.Label(loop_frame, text="ΔY (offset per group):").grid(row=row, column=0, sticky="e", padx=(0,6))
ttk.Entry(loop_frame, textvariable=dy_var, width=10).grid(row=row, column=1, sticky="w")
row += 1
ttk.Button(loop_frame, text="Loop", command=loop_block).grid(row=row, column=0, columnspan=2, pady=(8,0))

# Remove/Clear/Save/Load/Undo
btns2 = ttk.Frame(left); btns2.grid(row=5, column=0, columnspan=2, pady=(16,0), sticky="w")
ttk.Button(btns2, text="Remove selected", command=remove_selected).grid(row=0, column=0, padx=(0,8))
ttk.Button(btns2, text="Clear all", command=clear_all_lines).grid(row=0, column=1, padx=(0,8))
ttk.Button(btns2, text="Save .txt", command=save_gcode).grid(row=0, column=2, padx=(0,8))
ttk.Button(btns2, text="Load .txt", command=load_gcode).grid(row=0, column=3, padx=(0,8))
ttk.Button(btns2, text="Undo last op", command=undo_last).grid(row=0, column=4, padx=(0,8))

# --- Right: preview, list, plot, scale controls ---
ttk.Label(right, text="G-code Preview (next line)", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
gcode_preview = tk.StringVar(value="G1 X? Y?")
preview_lbl = ttk.Label(right, textvariable=gcode_preview, font=("Consolas", 14),
                        background="#111", foreground="#9fef00", padding=12)
preview_lbl.grid(row=1, column=0, sticky="ew", pady=(8,12))

ttk.Label(right, text="Submitted Lines (saved between M3 ... M5)", font=("Segoe UI", 11, "bold")).grid(row=2, column=0, sticky="w")

list_plot = ttk.Frame(right); list_plot.grid(row=3, column=0, sticky="nsew", pady=(6,0))
list_plot.columnconfigure(0, weight=1); list_plot.columnconfigure(1, weight=1)
list_plot.rowconfigure(0, weight=1)

# Listbox
list_frame = ttk.Frame(list_plot); list_frame.grid(row=0, column=0, sticky="nsew", padx=(0,8))
list_frame.rowconfigure(0, weight=1); list_frame.columnconfigure(0, weight=1)
lines_listbox = tk.Listbox(list_frame, font=("Consolas", 12))
lines_listbox.grid(row=0, column=0, sticky="nsew")
scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=lines_listbox.yview)
scrollbar.grid(row=0, column=1, sticky="ns")
lines_listbox.configure(yscrollcommand=scrollbar.set)

# Plot + toolbar
plot_frame = ttk.Frame(list_plot); plot_frame.grid(row=0, column=1, sticky="nsew")
fig = Figure(figsize=(5,4), dpi=100)
ax = fig.add_subplot(111)
ax.set_title("Path preview (X/Y)")
ax.grid(True, which="both", linewidth=0.5)
canvas = FigureCanvasTkAgg(fig, master=plot_frame)
canvas.get_tk_widget().pack(fill="both", expand=True)
toolbar = NavigationToolbar2Tk(canvas, plot_frame, pack_toolbar=False)
toolbar.update()
toolbar.pack(side="bottom", fill="x")   # Zoom / Pan / Home

# Manual scale controls
scale_frame = ttk.Labelframe(right, text="Scale / Zoom", padding=8)
scale_frame.grid(row=4, column=0, sticky="ew", pady=(10,0))
for i in range(11): scale_frame.columnconfigure(i, weight=0)

xmin_var = tk.StringVar(); xmax_var = tk.StringVar()
ymin_var = tk.StringVar(); ymax_var = tk.StringVar()
lock_aspect_var = tk.BooleanVar(value=True)

ttk.Label(scale_frame, text="Xmin").grid(row=0, column=0, padx=4)
ttk.Entry(scale_frame, textvariable=xmin_var, width=7).grid(row=0, column=1)
ttk.Label(scale_frame, text="Xmax").grid(row=0, column=2, padx=4)
ttk.Entry(scale_frame, textvariable=xmax_var, width=7).grid(row=0, column=3)
ttk.Label(scale_frame, text="Ymin").grid(row=0, column=4, padx=12)
ttk.Entry(scale_frame, textvariable=ymin_var, width=7).grid(row=0, column=5)
ttk.Label(scale_frame, text="Ymax").grid(row=0, column=6, padx=4)
ttk.Entry(scale_frame, textvariable=ymax_var, width=7).grid(row=0, column=7)

ttk.Button(scale_frame, text="Apply", command=apply_manual_scale).grid(row=0, column=8, padx=(12,4))
ttk.Button(scale_frame, text="Auto", command=auto_scale).grid(row=0, column=9)

ttk.Checkbutton(scale_frame, text="Lock aspect (1:1)", variable=lock_aspect_var,
                command=lambda: redraw_plot()).grid(row=0, column=10, padx=(12,0))

# live preview & keyboard
x_var.trace_add("write", update_preview)
y_var.trace_add("write", update_preview)
app.bind("<Return>", submit_line)

x_entry.focus_set()
redraw_plot()

app.mainloop()
