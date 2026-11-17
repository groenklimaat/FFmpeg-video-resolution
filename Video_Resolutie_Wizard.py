"""
Video Resolutie Wizard — Microsoft Store (1920x1080)
GUI in Tkinter met FFmpeg. Sleep of kies een video, kies opties, start.

Start met:  python "Video_Resolutie_Wizard.py"
"""

import os
import sys
import shutil
import subprocess
import threading
import queue
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# --- FFmpeg zoeken ----------------------------------------------------------
def find_ffmpeg():
    # 1. PATH (via winget of handmatige installatie)
    for name in ("ffmpeg", "ffmpeg.exe"):
        p = shutil.which(name)
        if p:
            return p
    # 2. imageio-ffmpeg (pip package)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    # 3. Veelvoorkomende winget-locatie
    for base in (
        Path.home() / "AppData/Local/Microsoft/WinGet/Packages",
        Path("C:/ffmpeg/bin"),
    ):
        if base.exists():
            for p in base.rglob("ffmpeg.exe"):
                return str(p)
    return None


FFMPEG = find_ffmpeg()
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".wmv", ".m4v", ".flv")


# --- FFmpeg commando's ------------------------------------------------------
def bouw_commando(input_path, output_path, mode, crf, preset, remove_audio):
    """
    mode:
      - "crop"   : vult 1920x1080, snijdt overtollig weg (aanbevolen)
      - "pad"    : hele video zichtbaar, zwarte randen
      - "stretch": vervormt (niet aanbevolen)
    """
    W, H = 1920, 1080

    if mode == "crop":
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
              f"crop={W}:{H}")
    elif mode == "pad":
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
              f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black")
    else:  # stretch
        vf = f"scale={W}:{H}"

    cmd = [
        FFMPEG, "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
    ]
    if remove_audio:
        cmd += ["-an"]
    else:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += [output_path]
    return cmd


def video_duur(ffmpeg_path, input_path):
    """Duur in seconden via ffprobe of ffmpeg -i output."""
    ffprobe = Path(ffmpeg_path).with_name(
        "ffprobe.exe" if os.name == "nt" else "ffprobe")
    if ffprobe.exists():
        try:
            out = subprocess.check_output(
                [str(ffprobe), "-v", "error", "-show_entries",
                 "format=duration", "-of",
                 "default=noprint_wrappers=1:nokey=1", input_path],
                stderr=subprocess.DEVNULL, text=True).strip()
            return float(out)
        except Exception:
            return None
    return None


# --- GUI --------------------------------------------------------------------
class VideoWizard(tk.Tk):
    BG = "#0f0f14"
    PANEL = "#1a1a24"
    ACCENT = "#6366f1"
    ACCENT_HOVER = "#818cf8"
    TEXT = "#e5e7eb"
    MUTED = "#9ca3af"
    SUCCESS = "#10b981"
    DANGER = "#ef4444"

    def __init__(self):
        super().__init__()
        self.title("Video Resolutie Wizard — Microsoft Store 1920×1080")
        self.geometry("820x640")
        self.configure(bg=self.BG)
        self.minsize(720, 560)

        self.input_file = None
        self.output_dir = Path.home() / "store_video_output"
        self.output_dir.mkdir(exist_ok=True)
        self.log_queue = queue.Queue()
        self.proc = None
        self.running = False

        self._build_ui()
        self._poll_log()

        if not FFMPEG:
            self.after(300, self._ffmpeg_missing)

    # --- UI -----------------------------------------------------------------
    def _build_ui(self):
        header = tk.Frame(self, bg=self.BG, pady=16)
        header.pack(fill="x", padx=24)
        tk.Label(header, text="Video Resolutie Wizard",
                 bg=self.BG, fg=self.TEXT,
                 font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(header,
                 text="Zet elke video om naar 1920×1080 (Microsoft Store) — met FFmpeg",
                 bg=self.BG, fg=self.MUTED,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 0))

        # Invoer
        in_frame = tk.Frame(self, bg=self.PANEL)
        in_frame.pack(fill="x", padx=24, pady=8)
        tk.Label(in_frame, text="Video", bg=self.PANEL, fg=self.MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        self.input_label = tk.Label(
            in_frame, text="Geen video gekozen",
            bg=self.PANEL, fg=self.TEXT, font=("Segoe UI", 10),
            anchor="w", justify="left", wraplength=700)
        self.input_label.pack(fill="x", padx=10)
        row = tk.Frame(in_frame, bg=self.PANEL)
        row.pack(fill="x", padx=10, pady=8)
        self._btn(row, "Video kiezen…", self._choose_input, primary=True).pack(side="left")
        self._btn(row, "Uitvoermap…", self._choose_output, primary=False).pack(side="left", padx=8)
        self.out_label = tk.Label(row, text=str(self.output_dir),
                                  bg=self.PANEL, fg=self.MUTED,
                                  font=("Segoe UI", 9))
        self.out_label.pack(side="left", padx=8)

        # Opties
        opt = tk.Frame(self, bg=self.PANEL)
        opt.pack(fill="x", padx=24, pady=8)
        tk.Label(opt, text="Opties", bg=self.PANEL, fg=self.MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(8, 6))

        # Mode
        mode_row = tk.Frame(opt, bg=self.PANEL)
        mode_row.pack(fill="x", padx=10, pady=4)
        tk.Label(mode_row, text="Beeldvulling:", bg=self.PANEL, fg=self.TEXT,
                 font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
        self.mode_var = tk.StringVar(value="crop")
        for val, lbl in (("crop", "Crop (vult kader)"),
                         ("pad", "Zwarte randen"),
                         ("stretch", "Uitrekken")):
            tk.Radiobutton(mode_row, text=lbl, variable=self.mode_var, value=val,
                           bg=self.PANEL, fg=self.TEXT,
                           selectcolor=self.BG, activebackground=self.PANEL,
                           activeforeground=self.TEXT,
                           font=("Segoe UI", 9)).pack(side="left", padx=6)

        # CRF
        crf_row = tk.Frame(opt, bg=self.PANEL)
        crf_row.pack(fill="x", padx=10, pady=4)
        tk.Label(crf_row, text="Kwaliteit (CRF):", bg=self.PANEL, fg=self.TEXT,
                 font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
        self.crf_var = tk.IntVar(value=20)
        self.crf_label = tk.Label(crf_row, text="20", bg=self.PANEL,
                                  fg=self.ACCENT, font=("Segoe UI", 9, "bold"),
                                  width=4)
        self.crf_label.pack(side="right")
        tk.Scale(crf_row, from_=14, to=32, orient="horizontal",
                 variable=self.crf_var, bg=self.PANEL, fg=self.TEXT,
                 troughcolor=self.BG, highlightthickness=0, bd=0,
                 showvalue=False, sliderlength=20,
                 command=lambda v: self.crf_label.config(text=str(int(float(v))))
                 ).pack(side="left", fill="x", expand=True, padx=8)
        tk.Label(crf_row, text="(lager = betere kwaliteit, groter bestand)",
                 bg=self.PANEL, fg=self.MUTED,
                 font=("Segoe UI", 8)).pack(side="left")

        # Preset
        preset_row = tk.Frame(opt, bg=self.PANEL)
        preset_row.pack(fill="x", padx=10, pady=(4, 8))
        tk.Label(preset_row, text="Snelheid:", bg=self.PANEL, fg=self.TEXT,
                 font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
        self.preset_var = tk.StringVar(value="medium")
        ttk.Combobox(preset_row, textvariable=self.preset_var,
                     values=["ultrafast", "superfast", "veryfast", "faster",
                             "fast", "medium", "slow", "slower", "veryslow"],
                     state="readonly", width=14).pack(side="left", padx=4)
        self.remove_audio = tk.BooleanVar(value=False)
        tk.Checkbutton(preset_row, text="Audio verwijderen",
                       variable=self.remove_audio,
                       bg=self.PANEL, fg=self.TEXT, selectcolor=self.BG,
                       activebackground=self.PANEL, activeforeground=self.TEXT,
                       font=("Segoe UI", 9)).pack(side="left", padx=16)

        # Start/stop
        actions = tk.Frame(self, bg=self.BG)
        actions.pack(fill="x", padx=24, pady=8)
        self.btn_start = self._btn(actions, "▶  Start conversie",
                                   self._start, primary=True)
        self.btn_start.pack(side="left")
        self.btn_stop = self._btn(actions, "■  Stop", self._stop, primary=False)
        self.btn_stop.pack(side="left", padx=8)
        self.btn_stop.config(state="disabled")
        self.btn_stop.bind("<Button-1>", lambda e: None)

        # Voortgang
        prog = tk.Frame(self, bg=self.BG)
        prog.pack(fill="x", padx=24, pady=(0, 8))
        self.progress = ttk.Progressbar(prog, mode="determinate")
        self.progress.pack(fill="x")
        self.status = tk.Label(prog, text="Klaar om te starten",
                               bg=self.BG, fg=self.MUTED, font=("Segoe UI", 9),
                               anchor="w")
        self.status.pack(fill="x", pady=(4, 0))

        # Log
        log_frame = tk.Frame(self, bg=self.PANEL)
        log_frame.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        self.log_text = tk.Text(log_frame, height=8, bg=self.BG, fg=self.TEXT,
                                bd=0, highlightthickness=0,
                                font=("Consolas", 9), state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=8, pady=8)

    def _btn(self, parent, text, command, primary=False):
        bg = self.ACCENT if primary else self.PANEL
        fg = "white" if primary else self.TEXT
        hover = self.ACCENT_HOVER if primary else "#252532"
        b = tk.Label(parent, text=text, bg=bg, fg=fg,
                     font=("Segoe UI", 10, "bold" if primary else "normal"),
                     padx=14, pady=8, cursor="hand2")
        b.bind("<Button-1>", lambda e: command())
        b.bind("<Enter>", lambda e: b.config(bg=hover))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        b._hover = hover
        b._bg = bg
        return b

    # --- Acties -------------------------------------------------------------
    def _ffmpeg_missing(self):
        messagebox.showerror(
            "FFmpeg niet gevonden",
            "FFmpeg is nodig om video's te converteren.\n\n"
            "Installeer het met:\n\n"
            "  winget install Gyan.FFmpeg\n\n"
            "of:\n\n"
            "  pip install imageio-ffmpeg\n\n"
            "en start dit programma opnieuw.")

    def _choose_input(self):
        f = filedialog.askopenfilename(
            title="Kies een video",
            filetypes=[("Video's", "*.mp4 *.mov *.mkv *.avi *.webm *.wmv *.m4v *.flv"),
                       ("Alle bestanden", "*.*")])
        if f:
            self.input_file = f
            dur = video_duur(FFMPEG, f) if FFMPEG else None
            info = f"{Path(f).name}"
            if dur:
                info += f"  —  {int(dur // 60)}:{int(dur % 60):02d}"
            self.input_label.config(text=f"{info}\n{Path(f).parent}")
            self.status.config(text="Video geladen. Klik op Start.")

    def _choose_output(self):
        d = filedialog.askdirectory(title="Kies uitvoermap")
        if d:
            self.output_dir = Path(d)
            self.out_label.config(text=str(self.output_dir))

    def _start(self):
        if not FFMPEG:
            self._ffmpeg_missing()
            return
        if not self.input_file:
            messagebox.showwarning("Geen video", "Kies eerst een video.")
            return
        if self.running:
            return

        naam = Path(self.input_file).stem
        self.output_file = str(self.output_dir / f"{naam}_1920x1080.mp4")
        cmd = bouw_commando(
            self.input_file, self.output_file,
            self.mode_var.get(), self.crf_var.get(),
            self.preset_var.get(), self.remove_audio.get())

        self._log(f"\n--- Start ---\n{' '.join(cmd)}\n")
        self.progress["value"] = 0
        self.status.config(text="Bezig…", fg=self.TEXT)
        self.running = True
        self.btn_start.config(bg=self.MUTED)
        self.btn_stop.config(bg=self.DANGER, fg="white")
        self.btn_stop.bind("<Button-1>", lambda e: self._stop())

        threading.Thread(target=self._run_ffmpeg, args=(cmd,), daemon=True).start()

    def _run_ffmpeg(self, cmd):
        dur = video_duur(FFMPEG, self.input_file) or 0
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, universal_newlines=True)
            for line in self.proc.stdout:
                line = line.rstrip()
                if "time=" in line:
                    try:
                        t = line.split("time=")[1].split()[0]
                        h, m, s = t.split(":")
                        secs = int(h) * 3600 + int(m) * 60 + float(s)
                        if dur > 0:
                            pct = min(secs / dur * 100, 100)
                            self.after(0, lambda p=pct: self.progress.configure(value=p))
                            self.after(0, lambda t=t: self.status.config(
                                text=f"Bezig… {t} / {int(dur//60)}:{int(dur%60):02d}", fg=self.TEXT))
                    except Exception:
                        pass
                elif any(k in line.lower() for k in ("error", "invalid", "failed")):
                    self._log(line)
            self.proc.wait()
            rc = self.proc.returncode
        except Exception as e:
            self._log(f"FOUT: {e}")
            rc = -1

        self.running = False
        self.after(0, self._done, rc)

    def _stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self._log("Gestopt door gebruiker.")
            self.running = False

    def _done(self, rc):
        self.btn_start.config(bg=self.ACCENT)
        self.btn_stop.config(bg=self.PANEL, fg=self.TEXT)
        self.btn_stop.bind("<Button-1>", lambda e: None)
        if rc == 0:
            self.progress["value"] = 100
            self.status.config(text=f"Klaar: {self.output_file}", fg=self.SUCCESS)
            self._log(f"\n✓ Opgeslagen: {self.output_file}")
            messagebox.showinfo("Klaar", f"Video opgeslagen:\n{self.output_file}")
        else:
            self.status.config(text=f"Mislukt (code {rc})", fg=self.DANGER)

    # --- Log ----------------------------------------------------------------
    def _log(self, msg):
        self.log_queue.put(msg)

    def _poll_log(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_text.config(state="normal")
                self.log_text.insert("end", msg + "\n")
                self.log_text.see("end")
                self.log_text.config(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._poll_log)


if __name__ == "__main__":
    VideoWizard().mainloop()