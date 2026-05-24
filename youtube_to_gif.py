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

        # プレビュー表示関連
        self.preview_image = None       # PhotoImage (時間タブ)
        self.region_preview_image = None  # PhotoImage (領域タブ)
        self.preview_scale = 1.0        # 表示倍率 (元動画 → キャンバス)
        self.canvas_img_w = 0
        self.canvas_img_h = 0

        # マウスドラッグ用
        self.drag_start = None
        self.drag_rect = None

        self.setup_ui()
        self.log("アプリケーション起動")
        self.log(f"スクリプトディレクトリ: {Path(__file__).parent.resolve()}")
        if not PIL_AVAILABLE:
            self.log("⚠️  Pillow が見つかりません。プレビュー機能は無効です (pip install pillow)")

    def log(self, message):
        """ログメッセージを表示"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}"

        if hasattr(self, 'log_text'):
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, log_msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)

        print(log_msg)

    def setup_ui(self):
        # メインフレーム
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 左側: タブコントロール
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

        # 右側: ログウィンドウ
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

        # ローカルファイルを開くボタン
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

        self.time_canvas = tk.Canvas(preview_frame, bg="gray20", width=480, height=270)
        self.time_canvas.pack(fill=tk.BOTH, expand=True)

        # スライダー部分
        slider_frame = ttk.LabelFrame(frame, text="時間範囲を選択", padding=10)
        slider_frame.pack(fill=tk.X, pady=5)

        # シーク（プレビュー位置）スライダー
        ttk.Label(slider_frame, text="シーク位置 (秒):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.seek_time = tk.DoubleVar(value=0)
        self.seek_slider = ttk.Scale(slider_frame, from_=0, to=100, variable=self.seek_time,
                                     orient=tk.HORIZONTAL, command=self.on_seek_change)
        self.seek_slider.grid(row=0, column=1, sticky=tk.EW, padx=5)
        self.seek_label = ttk.Label(slider_frame, text="0.0s", width=8)
        self.seek_label.grid(row=0, column=2, padx=5)

        # 開始時刻
        ttk.Label(slider_frame, text="開始時刻 (秒):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.start_time = tk.DoubleVar(value=0)
        self.start_slider = ttk.Scale(slider_frame, from_=0, to=100, variable=self.start_time,
                                      orient=tk.HORIZONTAL, command=self.on_start_change)
        self.start_slider.grid(row=1, column=1, sticky=tk.EW, padx=5)
        self.start_spin = ttk.Spinbox(slider_frame, from_=0, to=3600, increment=0.5,
                                      textvariable=self.start_time, width=8,
                                      command=self.on_start_spin)
        self.start_spin.grid(row=1, column=2, padx=5)

        # 終了時刻
        ttk.Label(slider_frame, text="終了時刻 (秒):").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.end_time = tk.DoubleVar(value=5)
        self.end_slider = ttk.Scale(slider_frame, from_=0, to=100, variable=self.end_time,
                                    orient=tk.HORIZONTAL, command=self.on_end_change)
        self.end_slider.grid(row=2, column=1, sticky=tk.EW, padx=5)
        self.end_spin = ttk.Spinbox(slider_frame, from_=0, to=3600, increment=0.5,
                                    textvariable=self.end_time, width=8,
                                    command=self.on_end_spin)
        self.end_spin.grid(row=2, column=2, padx=5)

        # ボタン
        btn_frame = ttk.Frame(slider_frame)
        btn_frame.grid(row=3, column=0, columnspan=3, pady=10)
        ttk.Button(btn_frame, text="◀ 開始位置を表示", command=lambda: self.seek_to(self.start_time.get())).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="終了位置を表示 ▶", command=lambda: self.seek_to(self.end_time.get())).pack(side=tk.LEFT, padx=5)

        self.time_info = ttk.Label(slider_frame, text="選択範囲: 0.0s ~ 5.0s (5.0s)", foreground="blue")
        self.time_info.grid(row=4, column=0, columnspan=3, sticky=tk.W, pady=5)

        slider_frame.columnconfigure(1, weight=1)

    # ---------------- Tab 3: Region ----------------
    def setup_tab3(self, tab):
        frame = ttk.Frame(tab, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # プレビューキャンバス（ドラッグで領域選択）
        preview_frame = ttk.LabelFrame(frame, text="プレビュー (ドラッグで領域選択)", padding=5)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.region_canvas = tk.Canvas(preview_frame, bg="gray20", width=480, height=270, cursor="cross")
        self.region_canvas.pack(fill=tk.BOTH, expand=True)
        self.region_canvas.bind("<ButtonPress-1>", self.on_drag_start)
        self.region_canvas.bind("<B1-Motion>", self.on_drag_motion)
        self.region_canvas.bind("<ButtonRelease-1>", self.on_drag_end)

        # コントロール部分
        ctrl_frame = ttk.LabelFrame(frame, text="切り取り領域", padding=10)
        ctrl_frame.pack(fill=tk.X, pady=5)

        # プリセット
        preset_frame = ttk.Frame(ctrl_frame)
        preset_frame.grid(row=0, column=0, columnspan=4, sticky=tk.W, pady=5)
        ttk.Label(preset_frame, text="プリセット:").pack(side=tk.LEFT, padx=5)
        ttk.Button(preset_frame, text="全体", command=self.set_region_full).pack(side=tk.LEFT, padx=3)
        ttk.Button(preset_frame, text="中央1/2", command=self.set_region_center).pack(side=tk.LEFT, padx=3)
        ttk.Button(preset_frame, text="上半分", command=self.set_region_top).pack(side=tk.LEFT, padx=3)

        # 数値入力
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
        script_dir = Path(__file__).parent.resolve()
        self.output_path = tk.StringVar(value=str(script_dir / "output.gif"))
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
                    "-o", str(output_dir / "%(title)s.%(ext)s"),
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
                # プレビュー初期表示
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
                "-show_entries", "stream=width,height",
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
                except (ValueError, IndexError) as e:
                    self.log(f"    → パースエラー: {e}")

            if duration is not None:
                self.video_duration = duration
                minutes = int(duration) // 60
                seconds = int(duration) % 60
                self.duration_label.config(text=f"{minutes}分 {seconds}秒")
                self.log(f"✓ duration設定: {duration}秒")
                # スライダーの範囲を更新
                self._update_slider_ranges()

            if width is not None and height is not None:
                self.video_width = width
                self.video_height = height
                self.resolution_label.config(text=f"{width}x{height}")
                self.log(f"✓ 解像度設定: {width}x{height}")
                # 領域のデフォルトを全体に
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
        """動画の長さに応じてスライダーの範囲を更新"""
        d = self.video_duration
        if d <= 0:
            return
        self.seek_slider.config(to=d)
        self.start_slider.config(to=d)
        self.end_slider.config(to=d)
        # 終了時刻が動画長を超えていたら調整
        if self.end_time.get() > d or self.end_time.get() <= 0:
            self.end_time.set(min(5.0, d))
        self.update_time_info()
        self.log(f"スライダー範囲を更新: 0 ~ {d}秒")

    # ================= フレーム抽出・プレビュー =================
    def extract_frame(self, timestamp):
        """指定時刻のフレームをPNGとして抽出し、パスを返す"""
        if not self.video_path:
            return None
        try:
            tmp_dir = Path(tempfile.gettempdir())
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

    def seek_to(self, timestamp):
        """指定時刻のフレームを両方のキャンバスに表示"""
        if not PIL_AVAILABLE:
            self.log("⚠️  Pillow未インストールのためプレビュー不可")
            return
        if not self.video_path:
            return

        timestamp = max(0, min(timestamp, max(0, self.video_duration - 0.1)))
        self.seek_time.set(timestamp)
        self.seek_label.config(text=f"{timestamp:.1f}s")
        self.log(f"シーク: {timestamp:.1f}s のフレームを取得")

        def do_seek():
            frame_path = self.extract_frame(timestamp)
            if frame_path:
                self.root.after(0, lambda: self._display_frame(frame_path))

        threading.Thread(target=do_seek, daemon=True).start()

    def _display_frame(self, frame_path):
        """抽出したフレームをキャンバスに描画"""
        try:
            img = Image.open(frame_path)
            orig_w, orig_h = img.size

            # キャンバスサイズに合わせてリサイズ
            canvas_w = self.time_canvas.winfo_width()
            canvas_h = self.time_canvas.winfo_height()
            if canvas_w < 10:
                canvas_w = 480
            if canvas_h < 10:
                canvas_h = 270

            scale = min(canvas_w / orig_w, canvas_h / orig_h)
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)
            self.preview_scale = scale
            self.canvas_img_w = new_w
            self.canvas_img_h = new_h

            img_resized = img.resize((new_w, new_h), Image.LANCZOS)

            # 時間タブ
            self.preview_image = ImageTk.PhotoImage(img_resized)
            self.time_canvas.delete("all")
            self.time_canvas.create_image(new_w // 2, new_h // 2, image=self.preview_image)

            # 領域タブ
            self.region_preview_image = ImageTk.PhotoImage(img_resized)
            self.region_canvas.delete("all")
            self.region_canvas.create_image(new_w // 2, new_h // 2, image=self.region_preview_image)
            self._draw_region_rect()

            self.log(f"✓ プレビュー表示 (元:{orig_w}x{orig_h} → 表示:{new_w}x{new_h}, scale={scale:.3f})")
        except Exception as e:
            self.log(f"❌ プレビュー表示エラー: {e}")

    # ================= 時間スライダー =================
    def on_seek_change(self, value):
        t = float(value)
        self.seek_label.config(text=f"{t:.1f}s")

    def on_seek_release(self, event=None):
        self.seek_to(self.seek_time.get())

    def on_start_change(self, value):
        self.update_time_info()

    def on_end_change(self, value):
        self.update_time_info()

    def on_start_spin(self):
        self.update_time_info()

    def on_end_spin(self):
        self.update_time_info()

    def update_time_info(self):
        try:
            start = self.start_time.get()
            end = self.end_time.get()
            dur = end - start
            self.time_info.config(text=f"選択範囲: {start:.1f}s ~ {end:.1f}s ({dur:.1f}s)")
        except Exception:
            pass

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

        # 座標を正規化（左上→右下）
        cx0, cx1 = min(x0, x1), max(x0, x1)
        cy0, cy1 = min(y0, y1), max(y0, y1)

        # 画像表示範囲内にクリップ
        cx0 = max(0, min(cx0, self.canvas_img_w))
        cx1 = max(0, min(cx1, self.canvas_img_w))
        cy0 = max(0, min(cy0, self.canvas_img_h))
        cy1 = max(0, min(cy1, self.canvas_img_h))

        # キャンバス座標 → 元動画座標に変換
        orig_x = int(cx0 / self.preview_scale)
        orig_y = int(cy0 / self.preview_scale)
        orig_w = int((cx1 - cx0) / self.preview_scale)
        orig_h = int((cy1 - cy0) / self.preview_scale)

        if orig_w < 10 or orig_h < 10:
            self.log("⚠️  選択領域が小さすぎます")
            return

        # 偶数に丸める（ffmpegの要件対策）
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
        """現在の領域設定を赤枠でキャンバスに描画"""
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
    # シークスライダーは離したときにフレーム更新
    app.seek_slider.bind("<ButtonRelease-1>", app.on_seek_release)
    root.mainloop()