#!/usr/bin/env python3
"""
YouTube to GIF converter with region and time selection GUI
動画プレビュー + マウス領域選択 + デバッグ機能付き版
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import subprocess
import os
import sys
from pathlib import Path
import json
import tempfile
from datetime import datetime

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class YouTubeToGifConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube to GIF Converter")
        self.root.geometry("1200x800")

        self.video_path = None
        self.video_duration = 0.0
        self.video_width = 0
        self.video_height = 0
        self.video_fps = 25.0

        # プレビュー表示関連
        self.preview_image = None
        self.region_preview_image = None
        self.preview_scale = 1.0
        self.canvas_img_w = 0
        self.canvas_img_h = 0

        # マウスドラッグ用
        self.drag_start = None
        self.drag_rect = None

        # シーク制御
        self.is_playing = False
        self._play_job = None
        self._drag_debounce = None
        self._seek_seq = 0

        # ズーム
        self._current_zoom = 1.0
        self.zoom_start = 0.0
        self.zoom_end = 0.0  # 0 = video_duration と同義

        self.setup_ui()
        self._setup_keybindings()
        self.log("アプリケーション起動")
        self.log(f"スクリプトディレクトリ: {Path(__file__).parent.resolve()}")
        if not PIL_AVAILABLE:
            self.log("⚠️  Pillow が見つかりません。プレビュー機能は無効です (pip install pillow)")

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        if hasattr(self, 'log_text'):
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, log_msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        print(log_msg)

    def setup_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        notebook = ttk.Notebook(left_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        tab1 = ttk.Frame(notebook)
        notebook.add(tab1, text="ダウンロード & プレビュー")
        self.setup_tab1(tab1)

        tab2 = ttk.Frame(notebook)
        notebook.add(tab2, text="時間を選択")
        self.setup_tab2(tab2)

        tab3 = ttk.Frame(notebook)
        notebook.add(tab3, text="領域を選択")
        self.setup_tab3(tab3)

        tab4 = ttk.Frame(notebook)
        notebook.add(tab4, text="GIFに変換")
        self.setup_tab4(tab4)

        right_frame = ttk.LabelFrame(main_frame, text="デバッグログ", padding=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=10, pady=10)

        self.log_text = tk.Text(right_frame, height=40, width=42, state=tk.DISABLED, bg="black", fg="lime")
        scrollbar = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.config(yscroll=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # ---------------- Tab 1: Download ----------------
    def setup_tab1(self, tab):
        frame = ttk.LabelFrame(tab, text="YouTube動画情報", padding=10)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(frame, text="YouTube URL:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.url_entry = ttk.Entry(frame, width=45)
        self.url_entry.grid(row=0, column=1, sticky=tk.EW, pady=5, padx=5)
        ttk.Button(frame, text="ダウンロード", command=self.download_video).grid(row=0, column=2, padx=5)

        ttk.Button(frame, text="ローカル動画を開く", command=self.open_local_video).grid(row=1, column=2, padx=5, pady=5)

        self.status_label = ttk.Label(frame, text="待機中...", foreground="gray")
        self.status_label.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=10)

        info_frame = ttk.LabelFrame(frame, text="動画情報", padding=10)
        info_frame.grid(row=3, column=0, columnspan=3, sticky=tk.EW, pady=10)

        ttk.Label(info_frame, text="ファイル:").grid(row=0, column=0, sticky=tk.W)
        self.file_label = ttk.Label(info_frame, text="-", foreground="blue")
        self.file_label.grid(row=0, column=1, sticky=tk.W)

        ttk.Label(info_frame, text="duration:").grid(row=1, column=0, sticky=tk.W)
        self.duration_label = ttk.Label(info_frame, text="-")
        self.duration_label.grid(row=1, column=1, sticky=tk.W)

        ttk.Label(info_frame, text="解像度:").grid(row=2, column=0, sticky=tk.W)
        self.resolution_label = ttk.Label(info_frame, text="-")
        self.resolution_label.grid(row=2, column=1, sticky=tk.W)

        frame.columnconfigure(1, weight=1)

    # ---------------- Tab 2: Time ----------------
    def setup_tab2(self, tab):
        frame = ttk.Frame(tab, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # プレビューキャンバス
        preview_frame = ttk.LabelFrame(frame, text="プレビュー", padding=5)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.time_canvas = tk.Canvas(preview_frame, bg="gray20", width=480, height=240)
        self.time_canvas.pack(fill=tk.BOTH, expand=True)

        # タイムラインバー（クリック/ドラッグでシーク可能）
        self.timeline_canvas = tk.Canvas(preview_frame, bg="#1a1a1a", height=40, cursor="sb_h_double_arrow")
        self.timeline_canvas.pack(fill=tk.X, padx=2, pady=(2, 0))
        self.timeline_canvas.bind("<ButtonPress-1>", self.on_timeline_press)
        self.timeline_canvas.bind("<B1-Motion>", self.on_timeline_drag)
        self.timeline_canvas.bind("<ButtonRelease-1>", self.on_timeline_release)

        # スライダー部分
        slider_frame = ttk.LabelFrame(frame, text="時間範囲を選択", padding=8)
        slider_frame.pack(fill=tk.X, pady=5)

        # Row 0: シーク
        ttk.Label(slider_frame, text="シーク:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.seek_time = tk.DoubleVar(value=0)
        self.seek_slider = ttk.Scale(slider_frame, from_=0, to=100, variable=self.seek_time,
                                     orient=tk.HORIZONTAL, command=self.on_seek_change)
        self.seek_slider.grid(row=0, column=1, sticky=tk.EW, padx=5)
        self.seek_label = ttk.Label(slider_frame, text="00:00.000  (0.0s)", width=20)
        self.seek_label.grid(row=0, column=2, columnspan=2, padx=5)

        # Row 1: ステップボタン
        step_frame = ttk.Frame(slider_frame)
        step_frame.grid(row=1, column=0, columnspan=4, pady=3)
        ttk.Button(step_frame, text="◀1s",  width=5, command=lambda: self.seek_by_time(-1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(step_frame, text="◀10f", width=5, command=lambda: self.seek_by_frames(-10)).pack(side=tk.LEFT, padx=2)
        ttk.Button(step_frame, text="◀1f",  width=5, command=lambda: self.seek_by_frames(-1)).pack(side=tk.LEFT, padx=2)
        ttk.Label(step_frame, text="    ").pack(side=tk.LEFT)
        ttk.Button(step_frame, text="▶1f",  width=5, command=lambda: self.seek_by_frames(1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(step_frame, text="▶10f", width=5, command=lambda: self.seek_by_frames(10)).pack(side=tk.LEFT, padx=2)
        ttk.Button(step_frame, text="▶1s",  width=5, command=lambda: self.seek_by_time(1)).pack(side=tk.LEFT, padx=2)

        # Row 2: 開始/終了設定ボタン + 再生
        set_frame = ttk.Frame(slider_frame)
        set_frame.grid(row=2, column=0, columnspan=4, pady=3)
        ttk.Button(set_frame, text="ここを開始に設定", command=self.set_start_here).pack(side=tk.LEFT, padx=5)
        ttk.Button(set_frame, text="ここを終了に設定", command=self.set_end_here).pack(side=tk.LEFT, padx=5)
        self.play_btn = ttk.Button(set_frame, text="▶ 再生  [Space]", command=self.toggle_play)
        self.play_btn.pack(side=tk.LEFT, padx=15)

        # Row 3: 開始時刻
        ttk.Label(slider_frame, text="開始時刻:").grid(row=3, column=0, sticky=tk.W, pady=3)
        self.start_time = tk.DoubleVar(value=0)
        self.start_slider = ttk.Scale(slider_frame, from_=0, to=100, variable=self.start_time,
                                      orient=tk.HORIZONTAL, command=self.on_start_change)
        self.start_slider.grid(row=3, column=1, sticky=tk.EW, padx=5)
        self.start_spin = ttk.Spinbox(slider_frame, from_=0, to=3600, increment=0.5,
                                      textvariable=self.start_time, width=8,
                                      command=self.on_start_spin)
        self.start_spin.grid(row=3, column=2, padx=5)
        self.start_mmss = ttk.Label(slider_frame, text="00:00.000", foreground="gray", width=10)
        self.start_mmss.grid(row=3, column=3, padx=5)

        # Row 4: 終了時刻
        ttk.Label(slider_frame, text="終了時刻:").grid(row=4, column=0, sticky=tk.W, pady=3)
        self.end_time = tk.DoubleVar(value=5)
        self.end_slider = ttk.Scale(slider_frame, from_=0, to=100, variable=self.end_time,
                                    orient=tk.HORIZONTAL, command=self.on_end_change)
        self.end_slider.grid(row=4, column=1, sticky=tk.EW, padx=5)
        self.end_spin = ttk.Spinbox(slider_frame, from_=0, to=3600, increment=0.5,
                                    textvariable=self.end_time, width=8,
                                    command=self.on_end_spin)
        self.end_spin.grid(row=4, column=2, padx=5)
        self.end_mmss = ttk.Label(slider_frame, text="00:05.000", foreground="gray", width=10)
        self.end_mmss.grid(row=4, column=3, padx=5)

        # Row 5: ズームコントロール
        zoom_frame = ttk.Frame(slider_frame)
        zoom_frame.grid(row=5, column=0, columnspan=4, sticky=tk.EW, pady=3)
        ttk.Label(zoom_frame, text="シークZoom:").pack(side=tk.LEFT, padx=5)
        self.zoom_level = tk.DoubleVar(value=1.0)
        self._zoom_scale = ttk.Scale(zoom_frame, from_=1, to=20, variable=self.zoom_level,
                                     orient=tk.HORIZONTAL, command=self.on_zoom_change)
        self._zoom_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.zoom_label_w = ttk.Label(zoom_frame, text="x1", width=4)
        self.zoom_label_w.pack(side=tk.LEFT)
        ttk.Button(zoom_frame, text="全体表示", command=self._reset_zoom).pack(side=tk.LEFT, padx=5)

        # Row 6: ナビボタン
        nav_frame = ttk.Frame(slider_frame)
        nav_frame.grid(row=6, column=0, columnspan=4, pady=4)
        ttk.Button(nav_frame, text="◀ 開始位置を表示",
                   command=lambda: self.seek_to(self.start_time.get())).pack(side=tk.LEFT, padx=5)
        ttk.Button(nav_frame, text="終了位置を表示 ▶",
                   command=lambda: self.seek_to(self.end_time.get())).pack(side=tk.LEFT, padx=5)

        # Row 7: 時間情報
        self.time_info = ttk.Label(slider_frame,
                                   text="選択範囲: 00:00.000 ~ 00:05.000  (5.0s)",
                                   foreground="blue")
        self.time_info.grid(row=7, column=0, columnspan=4, sticky=tk.W, pady=4)

        slider_frame.columnconfigure(1, weight=1)

    # ---------------- Tab 3: Region ----------------
    def setup_tab3(self, tab):
        frame = ttk.Frame(tab, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        preview_frame = ttk.LabelFrame(frame, text="プレビュー (ドラッグで領域選択)", padding=5)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.region_canvas = tk.Canvas(preview_frame, bg="gray20", width=480, height=270, cursor="cross")
        self.region_canvas.pack(fill=tk.BOTH, expand=True)
        self.region_canvas.bind("<ButtonPress-1>", self.on_drag_start)
        self.region_canvas.bind("<B1-Motion>", self.on_drag_motion)
        self.region_canvas.bind("<ButtonRelease-1>", self.on_drag_end)

        ctrl_frame = ttk.LabelFrame(frame, text="切り取り領域", padding=10)
        ctrl_frame.pack(fill=tk.X, pady=5)

        preset_frame = ttk.Frame(ctrl_frame)
        preset_frame.grid(row=0, column=0, columnspan=4, sticky=tk.W, pady=5)
        ttk.Label(preset_frame, text="プリセット:").pack(side=tk.LEFT, padx=5)
        ttk.Button(preset_frame, text="全体", command=self.set_region_full).pack(side=tk.LEFT, padx=3)
        ttk.Button(preset_frame, text="中央1/2", command=self.set_region_center).pack(side=tk.LEFT, padx=3)
        ttk.Button(preset_frame, text="上半分", command=self.set_region_top).pack(side=tk.LEFT, padx=3)

        ttk.Label(ctrl_frame, text="x:").grid(row=1, column=0, padx=5, pady=5)
        self.region_x = tk.IntVar(value=0)
        ttk.Spinbox(ctrl_frame, from_=0, to=4000, textvariable=self.region_x, width=8,
                    command=self.on_region_spin).grid(row=1, column=1, padx=5)

        ttk.Label(ctrl_frame, text="y:").grid(row=1, column=2, padx=5)
        self.region_y = tk.IntVar(value=0)
        ttk.Spinbox(ctrl_frame, from_=0, to=4000, textvariable=self.region_y, width=8,
                    command=self.on_region_spin).grid(row=1, column=3, padx=5)

        ttk.Label(ctrl_frame, text="width:").grid(row=2, column=0, padx=5, pady=5)
        self.region_w = tk.IntVar(value=640)
        ttk.Spinbox(ctrl_frame, from_=10, to=4000, textvariable=self.region_w, width=8,
                    command=self.on_region_spin).grid(row=2, column=1, padx=5)

        ttk.Label(ctrl_frame, text="height:").grid(row=2, column=2, padx=5)
        self.region_h = tk.IntVar(value=360)
        ttk.Spinbox(ctrl_frame, from_=10, to=4000, textvariable=self.region_h, width=8,
                    command=self.on_region_spin).grid(row=2, column=3, padx=5)

        self.region_info = ttk.Label(ctrl_frame, text="領域: 640x360 (x=0, y=0)", foreground="blue")
        self.region_info.grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=5)

    # ---------------- Tab 4: Convert ----------------
    def setup_tab4(self, tab):
        frame = ttk.LabelFrame(tab, text="GIF変換設定", padding=15)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        grid_frame = ttk.Frame(frame)
        grid_frame.pack(fill=tk.X)

        ttk.Label(grid_frame, text="FPS:").grid(row=0, column=0, sticky=tk.W, pady=10)
        self.fps = tk.IntVar(value=10)
        ttk.Spinbox(grid_frame, from_=1, to=30, textvariable=self.fps, width=10).grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Label(grid_frame, text="(推奨: 10)", foreground="gray").grid(row=0, column=2, sticky=tk.W)

        ttk.Label(grid_frame, text="色数:").grid(row=1, column=0, sticky=tk.W, pady=10)
        self.colors = tk.IntVar(value=256)
        ttk.Combobox(grid_frame, textvariable=self.colors, values=["16", "64", "128", "256"],
                     width=10, state="readonly").grid(row=1, column=1, sticky=tk.W, padx=5)
        ttk.Label(grid_frame, text="(多いほど高品質)", foreground="gray").grid(row=1, column=2, sticky=tk.W)

        ttk.Label(grid_frame, text="スケール:").grid(row=2, column=0, sticky=tk.W, pady=10)
        self.scale = tk.DoubleVar(value=1.0)
        ttk.Combobox(grid_frame, textvariable=self.scale,
                     values=["0.5", "0.75", "1.0", "1.5", "2.0"],
                     width=10, state="readonly").grid(row=2, column=1, sticky=tk.W, padx=5)
        ttk.Label(grid_frame, text="(ファイル size 削減用)", foreground="gray").grid(row=2, column=2, sticky=tk.W)

        ttk.Label(grid_frame, text="出力先:").grid(row=3, column=0, sticky=tk.W, pady=10)
        
        
        # script_dir = Path(__file__).parent.resolve()
        # self.output_path = tk.StringVar(value=str(script_dir / "output.gif"))
        script_dir = Path(__file__).parent.resolve()
        output_dir = script_dir / "gif_output"
        output_dir.mkdir(parents=True, exist_ok=True)  # フォルダがなければ作成
        self.output_path = tk.StringVar(value=str(output_dir / "output.gif"))
        
        
        
        ttk.Entry(grid_frame, textvariable=self.output_path, width=40).grid(row=3, column=1, columnspan=2, sticky=tk.EW, padx=5)
        ttk.Button(grid_frame, text="参照", command=self.select_output).grid(row=3, column=3, padx=5)
        grid_frame.columnconfigure(1, weight=1)

        ttk.Button(frame, text="GIFに変換", command=self.convert_to_gif).pack(pady=20)

        self.progress = ttk.Progressbar(frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=10)

        self.result_label = ttk.Label(frame, text="", foreground="green")
        self.result_label.pack(anchor=tk.W, pady=10)

    # ================= 動画読み込み =================
    def open_local_video(self):
        file = filedialog.askopenfilename(
            title="動画ファイルを選択",
            filetypes=[("動画ファイル", "*.mp4 *.mkv *.webm *.avi *.mov"), ("All files", "*.*")]
        )
        if file:
            self.video_path = file
            self.log(f"ローカル動画を開く: {file}")
            self.status_label.config(text=f"読み込み: {Path(file).name}", foreground="green")
            self._update_video_info()
            self.seek_to(0)

    def download_video(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("エラー", "URLを入力してください")
            return

        self.log(f"ダウンロード開始: {url}")
        self.status_label.config(text="ダウンロード中...", foreground="orange")
        self.root.update()

        def download():
            try:
                script_dir = Path(__file__).parent.resolve()
                output_dir = script_dir / "youtube_temp"
                self.log(f"出力ディレクトリ: {output_dir}")
                output_dir.mkdir(parents=True, exist_ok=True)

                downloader = "yt-dlp" if self._check_command("yt-dlp") else "youtube-dl"
                self.log(f"ダウンローダー: {downloader}")

                cmd = [
                    downloader, "-f", "best",
                    # "-o", str(output_dir / "%(title)s.%(ext)s"),
                    "-o", str(output_dir / "%(title).50s.%(ext)s"),
                    "--restrict-filenames",
                    "--print", "after_move:filepath", url
                ]
                self.log(f"コマンド実行: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True)
                self.log(f"リターンコード: {result.returncode}")
                if result.stderr:
                    self.log(f"stderr: {result.stderr[:200]}")

                if result.returncode != 0:
                    raise Exception(f"ダウンロードに失敗: {result.stderr}")

                filepath = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
                self.log(f"ファイルパス候補: {filepath}")

                if filepath and Path(filepath).exists():
                    self.video_path = filepath
                else:
                    files = sorted(output_dir.glob("*"), key=lambda f: f.stat().st_mtime)
                    if not files:
                        raise Exception("ファイルが見つかりません")
                    self.video_path = str(files[-1])
                self.log(f"動画ファイル: {self.video_path}")

                self._update_video_info()
                self.status_label.config(text=f"ダウンロード完了: {Path(self.video_path).name}", foreground="green")
                self.log("ダウンロード完了")
                self.root.after(100, lambda: self.seek_to(0))

            except Exception as e:
                self.log(f"❌ ダウンロードエラー: {str(e)}")
                self.status_label.config(text=f"エラー: {str(e)}", foreground="red")

        threading.Thread(target=download, daemon=True).start()

    def _check_command(self, cmd):
        try:
            subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
            self.log(f"✓ コマンド確認: {cmd}")
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self.log(f"✗ コマンドなし: {cmd}")
            return False

    def _update_video_info(self):
        if not self.video_path:
            self.log("エラー: video_path が設定されていません")
            return
        try:
            self.log(f"動画情報取得開始: {self.video_path}")
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-show_entries", "stream=width,height,r_frame_rate",
                "-of", "default=noprint_wrappers=1",
                self.video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            self.log(f"ffprobeリターンコード: {result.returncode}")

            self.file_label.config(text=Path(self.video_path).name)

            if result.returncode != 0 or not result.stdout:
                self.log(f"⚠️  ffprobeエラーまたは出力なし: {result.stderr}")
                return

            self.log(f"ffprobe出力:\n{result.stdout}")

            duration = None
            width = None
            height = None
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                try:
                    if line.startswith('duration='):
                        duration = float(line.split('=')[1])
                    elif line.startswith('width='):
                        width = int(line.split('=')[1])
                    elif line.startswith('height='):
                        height = int(line.split('=')[1])
                    elif line.startswith('r_frame_rate='):
                        rate = line.split('=')[1].strip()
                        if '/' in rate:
                            num, den = rate.split('/')
                            den_f = float(den)
                            if den_f > 0:
                                self.video_fps = float(num) / den_f
                        elif rate and rate != 'N/A':
                            self.video_fps = float(rate)
                        self.log(f"✓ FPS設定: {self.video_fps:.3f}")
                except (ValueError, IndexError) as e:
                    self.log(f"    → パースエラー: {e}")

            if duration is not None:
                self.video_duration = duration
                minutes = int(duration) // 60
                seconds = int(duration) % 60
                self.duration_label.config(text=f"{minutes}分 {seconds}秒")
                self.log(f"✓ duration設定: {duration}秒")
                self._update_slider_ranges()

            if width is not None and height is not None:
                self.video_width = width
                self.video_height = height
                self.resolution_label.config(text=f"{width}x{height}")
                self.log(f"✓ 解像度設定: {width}x{height}")
                self.region_x.set(0)
                self.region_y.set(0)
                self.region_w.set(width)
                self.region_h.set(height)
                self.update_region_info()

            self.log("動画情報取得完了")
        except Exception as e:
            self.log(f"❌ 動画情報取得エラー: {e}")
            self.file_label.config(text=Path(self.video_path).name if self.video_path else "-")

    def _update_slider_ranges(self):
        d = self.video_duration
        if d <= 0:
            return
        self.seek_slider.config(to=d)
        self.start_slider.config(to=d)
        self.end_slider.config(to=d)
        if self.end_time.get() > d or self.end_time.get() <= 0:
            self.end_time.set(min(5.0, d))
        # ズームをリセット
        self._current_zoom = 1.0
        self.zoom_start = 0.0
        self.zoom_end = d
        self.zoom_level.set(1.0)
        if hasattr(self, 'zoom_label_w'):
            self.zoom_label_w.config(text="x1")
        self.update_time_info()
        self.update_timeline_bar()
        self.log(f"スライダー範囲を更新: 0 ~ {d}秒")

    # ================= フレーム抽出・プレビュー =================
    def extract_frame(self, timestamp, low_quality=False):
        if not self.video_path:
            return None
        try:
            tmp_dir = Path(tempfile.gettempdir())
            if low_quality:
                frame_path = tmp_dir / "ytgif_preview_lq.png"
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(timestamp),
                    "-i", self.video_path,
                    "-frames:v", "1",
                    "-q:v", "10",
                    "-vf", "scale=320:-1",
                    str(frame_path)
                ]
            else:
                frame_path = tmp_dir / "ytgif_preview_frame.png"
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(timestamp),
                    "-i", self.video_path,
                    "-frames:v", "1",
                    "-q:v", "2",
                    str(frame_path)
                ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.log(f"⚠️  フレーム抽出失敗: {result.stderr[-200:]}")
                return None
            if frame_path.exists():
                return str(frame_path)
            return None
        except Exception as e:
            self.log(f"❌ フレーム抽出エラー: {e}")
            return None

    def seek_to(self, timestamp, low_quality=False):
        if not PIL_AVAILABLE:
            self.log("⚠️  Pillow未インストールのためプレビュー不可")
            return
        if not self.video_path:
            return

        timestamp = max(0, min(timestamp, max(0, self.video_duration - 0.1)))
        self.seek_time.set(timestamp)
        self.seek_label.config(text=f"{self.format_time(timestamp)}  ({timestamp:.1f}s)")
        if not low_quality:
            self.log(f"シーク: {timestamp:.1f}s のフレームを取得")

        self._seek_seq += 1
        current_seq = self._seek_seq
        self.update_timeline_bar()

        def do_seek():
            frame_path = self.extract_frame(timestamp, low_quality=low_quality)
            if frame_path and self._seek_seq == current_seq:
                self.root.after(0, lambda: self._display_frame(frame_path))

        threading.Thread(target=do_seek, daemon=True).start()

    def _display_frame(self, frame_path):
        try:
            img = Image.open(frame_path)
            orig_w, orig_h = img.size

            canvas_w = self.time_canvas.winfo_width()
            canvas_h = self.time_canvas.winfo_height()
            if canvas_w < 10:
                canvas_w = 480
            if canvas_h < 10:
                canvas_h = 240

            scale = min(canvas_w / orig_w, canvas_h / orig_h)
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)
            self.preview_scale = scale
            self.canvas_img_w = new_w
            self.canvas_img_h = new_h

            img_resized = img.resize((new_w, new_h), Image.LANCZOS)

            self.preview_image = ImageTk.PhotoImage(img_resized)
            self.time_canvas.delete("all")
            self.time_canvas.create_image(new_w // 2, new_h // 2, image=self.preview_image)

            self.region_preview_image = ImageTk.PhotoImage(img_resized)
            self.region_canvas.delete("all")
            self.region_canvas.create_image(new_w // 2, new_h // 2, image=self.region_preview_image)
            self._draw_region_rect()

            self.log(f"✓ プレビュー表示 (元:{orig_w}x{orig_h} → 表示:{new_w}x{new_h}, scale={scale:.3f})")
        except Exception as e:
            self.log(f"❌ プレビュー表示エラー: {e}")

    # ================= 時間スライダー =================
    def format_time(self, t: float) -> str:
        t = max(0.0, t)
        m = int(t) // 60
        s = int(t) % 60
        ms = int(round((t % 1) * 1000))
        if ms >= 1000:
            ms = 0
            s += 1
        return f"{m:02d}:{s:02d}.{ms:03d}"

    def on_seek_change(self, value):
        t = float(value)
        self.seek_label.config(text=f"{self.format_time(t)}  ({t:.1f}s)")
        # デバウンス: 80ms後に低画質シーク
        if self._drag_debounce:
            self.root.after_cancel(self._drag_debounce)
        self._drag_debounce = self.root.after(80, lambda: self.seek_to(t, low_quality=True))
        self.update_timeline_bar()

    def on_seek_release(self, event=None):
        # デバウンスをキャンセルして高画質で再取得
        if self._drag_debounce:
            self.root.after_cancel(self._drag_debounce)
            self._drag_debounce = None
        self.seek_to(self.seek_time.get(), low_quality=False)

    def on_start_change(self, value):
        self.start_mmss.config(text=self.format_time(float(value)))
        self.update_time_info()
        self.update_timeline_bar()

    def on_end_change(self, value):
        self.end_mmss.config(text=self.format_time(float(value)))
        self.update_time_info()
        self.update_timeline_bar()

    def on_start_spin(self):
        v = self.start_time.get()
        self.start_mmss.config(text=self.format_time(v))
        self.update_time_info()
        self.update_timeline_bar()

    def on_end_spin(self):
        v = self.end_time.get()
        self.end_mmss.config(text=self.format_time(v))
        self.update_time_info()
        self.update_timeline_bar()

    def update_time_info(self):
        try:
            start = self.start_time.get()
            end = self.end_time.get()
            dur = end - start
            self.time_info.config(
                text=f"選択範囲: {self.format_time(start)} ~ {self.format_time(end)}  ({dur:.1f}s)"
            )
        except Exception:
            pass

    # ================= タイムラインバー =================
    def update_timeline_bar(self):
        if not hasattr(self, 'timeline_canvas'):
            return
        c = self.timeline_canvas
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10:
            w = 480
        if h < 10:
            h = 40

        dur = self.video_duration
        c.delete("all")

        # 背景
        c.create_rectangle(0, 0, w, h, fill="#1a1a1a", outline="")

        if dur <= 0:
            c.create_text(w // 2, h // 2, text="動画を読み込んでください", fill="gray50", font=("", 9))
            return

        # メインバー（灰色のトラック）
        bar_y0 = h // 2 - 5
        bar_y1 = h // 2 + 5
        c.create_rectangle(2, bar_y0, w - 2, bar_y1, fill="#404040", outline="")

        def t_to_x(t):
            return int(t / dur * (w - 4)) + 2

        # 選択範囲（緑）
        start = self.start_time.get()
        end = self.end_time.get()
        x0 = max(2, t_to_x(start))
        x1 = min(w - 2, t_to_x(end))
        if x1 > x0:
            c.create_rectangle(x0, bar_y0, x1, bar_y1, fill="#4CAF50", outline="")

        # ズームウィンドウ表示（黄色の枠）
        if self._current_zoom > 1.0:
            zx0 = max(2, t_to_x(self.zoom_start))
            zx1 = min(w - 2, t_to_x(self.zoom_end))
            if zx1 > zx0:
                c.create_rectangle(zx0, 2, zx1, h - 2, outline="#FFD700", width=1)

        # 開始/終了マーカー（点線）
        xs = t_to_x(start)
        xe = t_to_x(end)
        if 2 <= xs <= w - 2:
            c.create_line(xs, bar_y0 - 4, xs, bar_y1 + 4, fill="#00CC44", width=2)
        if 2 <= xe <= w - 2:
            c.create_line(xe, bar_y0 - 4, xe, bar_y1 + 4, fill="#FF4444", width=2)

        # シーク位置（白い縦線）
        seek = self.seek_time.get()
        xseek = t_to_x(seek)
        if 2 <= xseek <= w - 2:
            c.create_line(xseek, 0, xseek, h, fill="white", width=2)

        # 時刻ラベル（両端）
        c.create_text(4, h - 3, text="0:00", fill="gray60", font=("", 7), anchor="sw")
        c.create_text(w - 4, h - 3, text=self.format_time(dur), fill="gray60", font=("", 7), anchor="se")

    def on_timeline_press(self, event):
        self._seek_from_timeline(event.x, low_quality=True)

    def on_timeline_drag(self, event):
        self._seek_from_timeline(event.x, low_quality=True)

    def on_timeline_release(self, event):
        self._seek_from_timeline(event.x, low_quality=False)

    def _seek_from_timeline(self, x, low_quality):
        dur = self.video_duration
        if dur <= 0:
            return
        w = self.timeline_canvas.winfo_width()
        if w < 10:
            w = 480
        t = (x - 2) / (w - 4) * dur
        self.seek_to(t, low_quality=low_quality)

    # ================= 開始/終了設定・ステップ移動 =================
    def set_start_here(self):
        t = self.seek_time.get()
        self.start_time.set(t)
        self.start_mmss.config(text=self.format_time(t))
        self.update_time_info()
        self.update_timeline_bar()
        self.log(f"開始時刻を設定: {self.format_time(t)}")

    def set_end_here(self):
        t = self.seek_time.get()
        self.end_time.set(t)
        self.end_mmss.config(text=self.format_time(t))
        self.update_time_info()
        self.update_timeline_bar()
        self.log(f"終了時刻を設定: {self.format_time(t)}")

    def seek_by_frames(self, n: int):
        fps = max(1.0, self.video_fps)
        delta = n / fps
        t = self.seek_time.get() + delta
        self.seek_to(t)

    def seek_by_time(self, delta: float):
        t = self.seek_time.get() + delta
        self.seek_to(t)

    # ================= 再生/停止 =================
    def toggle_play(self):
        if self.is_playing:
            self.is_playing = False
            if self._play_job:
                self.root.after_cancel(self._play_job)
                self._play_job = None
            self.play_btn.config(text="▶ 再生  [Space]")
            self.log("再生停止")
        else:
            if not self.video_path:
                return
            self.is_playing = True
            self.play_btn.config(text="■ 停止  [Space]")
            self.log("再生開始")
            self._play_next_frame()

    def _play_next_frame(self):
        if not self.is_playing:
            return
        fps = max(1.0, self.video_fps)
        step = 5.5 / fps
        t = self.seek_time.get() + step
        if t >= self.video_duration:
            self.is_playing = False
            self.play_btn.config(text="▶ 再生  [Space]")
            self.log("再生終了（末尾に到達）")
            return

        self._seek_seq += 1
        current_seq = self._seek_seq
        self.seek_time.set(t)
        self.seek_label.config(text=f"{self.format_time(t)}  ({t:.1f}s)")
        self.update_timeline_bar()

        def do_frame():
            frame_path = self.extract_frame(t, low_quality=True)
            if frame_path and self._seek_seq == current_seq:
                self.root.after(0, lambda: (
                    self._display_frame(frame_path),
                    self._play_next_frame() if self.is_playing else None
                ))

        threading.Thread(target=do_frame, daemon=True).start()

    # ================= ズーム =================
    def on_zoom_change(self, value):
        zoom = max(1.0, float(value))
        self._current_zoom = zoom
        label = f"x{int(zoom)}" if zoom == int(zoom) else f"x{zoom:.1f}"
        self.zoom_label_w.config(text=label)

        dur = self.video_duration
        if dur <= 0:
            return
        center = self.seek_time.get()
        window = dur / zoom
        half_w = window / 2
        z_start = max(0.0, center - half_w)
        z_end = min(dur, z_start + window)
        # 端に当たった場合の調整
        if z_end >= dur:
            z_end = dur
            z_start = max(0.0, dur - window)
        self.zoom_start = z_start
        self.zoom_end = z_end

        self.seek_slider.config(from_=z_start, to=z_end)
        self.update_timeline_bar()

    def _reset_zoom(self):
        self._current_zoom = 1.0
        self.zoom_level.set(1.0)
        self.zoom_label_w.config(text="x1")
        dur = self.video_duration
        self.zoom_start = 0.0
        self.zoom_end = dur if dur > 0 else 1.0
        self.seek_slider.config(from_=0, to=max(1, dur))
        self.update_timeline_bar()
        self.log("ズームをリセット")

    # ================= キーボードショートカット =================
    def _setup_keybindings(self):
        self.root.bind("<Left>", self._on_key)
        self.root.bind("<Right>", self._on_key)
        self.root.bind("<Shift-Left>", self._on_key)
        self.root.bind("<Shift-Right>", self._on_key)
        self.root.bind("<space>", self._on_space_key)

    def _on_key(self, event):
        focused = self.root.focus_get()
        if isinstance(focused, (ttk.Entry, ttk.Spinbox, tk.Entry, tk.Text)):
            return
        shift = bool(event.state & 0x1)
        if event.keysym == "Left":
            if shift:
                self.seek_by_time(-1)
            else:
                self.seek_by_frames(-1)
        elif event.keysym == "Right":
            if shift:
                self.seek_by_time(1)
            else:
                self.seek_by_frames(1)

    def _on_space_key(self, event):
        focused = self.root.focus_get()
        if isinstance(focused, (ttk.Entry, ttk.Spinbox, tk.Entry, tk.Text)):
            return
        self.toggle_play()

    # ================= 領域選択（マウスドラッグ） =================
    def on_drag_start(self, event):
        self.drag_start = (event.x, event.y)
        if self.drag_rect:
            self.region_canvas.delete(self.drag_rect)
            self.drag_rect = None

    def on_drag_motion(self, event):
        if not self.drag_start:
            return
        x0, y0 = self.drag_start
        x1, y1 = event.x, event.y
        if self.drag_rect:
            self.region_canvas.delete(self.drag_rect)
        self.drag_rect = self.region_canvas.create_rectangle(
            x0, y0, x1, y1, outline="red", width=2
        )

    def on_drag_end(self, event):
        if not self.drag_start:
            return
        if self.preview_scale <= 0 or not self.video_path:
            self.log("⚠️  動画を読み込んでから領域を選択してください")
            return

        x0, y0 = self.drag_start
        x1, y1 = event.x, event.y

        cx0, cx1 = min(x0, x1), max(x0, x1)
        cy0, cy1 = min(y0, y1), max(y0, y1)

        cx0 = max(0, min(cx0, self.canvas_img_w))
        cx1 = max(0, min(cx1, self.canvas_img_w))
        cy0 = max(0, min(cy0, self.canvas_img_h))
        cy1 = max(0, min(cy1, self.canvas_img_h))

        orig_x = int(cx0 / self.preview_scale)
        orig_y = int(cy0 / self.preview_scale)
        orig_w = int((cx1 - cx0) / self.preview_scale)
        orig_h = int((cy1 - cy0) / self.preview_scale)

        if orig_w < 10 or orig_h < 10:
            self.log("⚠️  選択領域が小さすぎます")
            return

        orig_w = orig_w - (orig_w % 2)
        orig_h = orig_h - (orig_h % 2)

        self.region_x.set(orig_x)
        self.region_y.set(orig_y)
        self.region_w.set(orig_w)
        self.region_h.set(orig_h)
        self.update_region_info()
        self.log(f"領域選択(ドラッグ): x={orig_x}, y={orig_y}, w={orig_w}, h={orig_h}")
        self._draw_region_rect()

    def _draw_region_rect(self):
        if self.preview_scale <= 0:
            return
        if self.drag_rect:
            self.region_canvas.delete(self.drag_rect)
        x = self.region_x.get() * self.preview_scale
        y = self.region_y.get() * self.preview_scale
        w = self.region_w.get() * self.preview_scale
        h = self.region_h.get() * self.preview_scale
        self.drag_rect = self.region_canvas.create_rectangle(
            x, y, x + w, y + h, outline="red", width=2
        )

    def on_region_spin(self):
        self.update_region_info()
        self._draw_region_rect()

    def update_region_info(self):
        x, y, w, h = self.region_x.get(), self.region_y.get(), self.region_w.get(), self.region_h.get()
        self.region_info.config(text=f"領域: {w}x{h} (x={x}, y={y})")

    def set_region_full(self):
        if self.video_width > 0:
            self.set_region(0, 0, self.video_width, self.video_height)
        else:
            self.set_region(0, 0, 640, 360)

    def set_region_center(self):
        if self.video_width > 0:
            w = self.video_width // 2
            h = self.video_height // 2
            self.set_region(self.video_width // 4, self.video_height // 4, w, h)

    def set_region_top(self):
        if self.video_width > 0:
            self.set_region(0, 0, self.video_width, self.video_height // 2)

    def set_region(self, x, y, w, h):
        self.region_x.set(x)
        self.region_y.set(y)
        self.region_w.set(w)
        self.region_h.set(h)
        self.update_region_info()
        self._draw_region_rect()
        self.log(f"領域を設定: x={x}, y={y}, w={w}, h={h}")

    # ================= 出力 =================
    def select_output(self):
        file = filedialog.asksaveasfilename(
            defaultextension=".gif",
            filetypes=[("GIF files", "*.gif"), ("All files", "*.*")]
        )
        if file:
            self.output_path.set(file)
            self.log(f"出力先設定: {file}")

    def convert_to_gif(self):
        self.log("=== GIF変換開始 ===")
        if not self.video_path:
            self.log("❌ エラー: 動画がダウンロードされていません")
            messagebox.showerror("エラー", "動画をダウンロードしてください")
            return

        try:
            start = self.start_time.get()
            end = self.end_time.get()
            x = self.region_x.get()
            y = self.region_y.get()
            w = self.region_w.get()
            h = self.region_h.get()
            fps = self.fps.get()
            colors = self.colors.get()
            scale = float(self.scale.get())
            output = self.output_path.get()

            self.log(f"パラメータ:")
            self.log(f"  動画: {self.video_path}")
            self.log(f"  時間範囲: {start}秒 ~ {end}秒")
            self.log(f"  領域: x={x}, y={y}, w={w}, h={h}")
            self.log(f"  FPS: {fps}, 色数: {colors}, スケール: {scale}")
            self.log(f"  出力先: {output}")

            if start >= end:
                self.log("❌ エラー: 開始時刻 >= 終了時刻")
                messagebox.showerror("エラー", "開始時刻は終了時刻より前にしてください")
                return

            self.progress.start()
            self.result_label.config(text="変換中...")
            self.root.update()

            def convert():
                try:
                    duration = end - start
                    self.log(f"変換時間: {duration}秒")

                    filters = [f"fps={fps}", f"crop={w}:{h}:{x}:{y}"]
                    if scale != 1.0:
                        new_w = int(w * scale)
                        filters.append(f"scale={new_w}:-1:flags=lanczos")
                    filter_str = ",".join(filters)
                    self.log(f"ffmpegフィルター: {filter_str}")

                    palette_path = Path(output).with_suffix(".png")
                    self.log("ステップ1: パレット生成開始")
                    palette_cmd = [
                        "ffmpeg", "-y",
                        "-ss", str(start), "-t", str(duration),
                        "-i", self.video_path,
                        "-vf", f"{filter_str},palettegen=max_colors={colors}",
                        str(palette_path)
                    ]
                    r1 = subprocess.run(palette_cmd, capture_output=True, text=True)
                    self.log(f"パレット生成リターンコード: {r1.returncode}")
                    if r1.returncode != 0:
                        self.log(f"stderr: {r1.stderr[-500:]}")
                        raise Exception(f"パレット生成失敗:\n{r1.stderr[-500:]}")
                    self.log("✓ パレット生成完了")

                    self.log("ステップ2: GIF生成開始")
                    gif_cmd = [
                        "ffmpeg", "-y",
                        "-ss", str(start), "-t", str(duration),
                        "-i", self.video_path,
                        "-i", str(palette_path),
                        "-lavfi", f"{filter_str} [x]; [x][1:v] paletteuse",
                        output
                    ]
                    r2 = subprocess.run(gif_cmd, capture_output=True, text=True)
                    self.log(f"GIF生成リターンコード: {r2.returncode}")
                    if r2.returncode != 0:
                        self.log(f"stderr: {r2.stderr[-500:]}")

                    if palette_path.exists():
                        palette_path.unlink()
                        self.log("✓ パレットファイル削除")

                    if r2.returncode == 0 and Path(output).exists():
                        file_size = Path(output).stat().st_size / (1024 * 1024)
                        self.result_label.config(
                            text=f"完了: {output} ({file_size:.2f} MB)", foreground="green")
                        self.log(f"✓✓✓ GIF変換完了: {file_size:.2f} MB")
                    else:
                        raise Exception(f"GIF変換失敗:\n{r2.stderr[-500:]}")

                except Exception as e:
                    self.log(f"❌ 変換エラー: {str(e)}")
                    self.result_label.config(text=f"エラー: {str(e)}", foreground="red")
                finally:
                    self.progress.stop()

            threading.Thread(target=convert, daemon=True).start()

        except Exception as e:
            self.log(f"❌ 予期しないエラー: {str(e)}")
            messagebox.showerror("エラー", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = YouTubeToGifConverter(root)
    app.seek_slider.bind("<ButtonRelease-1>", app.on_seek_release)
    root.mainloop()
