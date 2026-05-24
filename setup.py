#!/usr/bin/env python3
"""
Setup script for YouTube to GIF Converter
依存パッケージのインストールと環境確認
"""

import subprocess
import sys
import platform
import os
import shutil

def run_command(cmd, check=True):
    """Run a shell command and return result"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=check)
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)

def check_python():
    """Check Python version"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 7):
        print(f"❌ Python 3.7以上が必要です (現在: {version.major}.{version.minor})")
        return False
    print(f"✓ Python {version.major}.{version.minor} OK")
    return True

def check_command(cmd_name, install_hint=""):
    """Check if a command is available"""
    # 方法1: shutil.which() を使用（より確実）
    exe_path = shutil.which(cmd_name)
    
    # 方法2: Windows 環境では .exe を明示的に探す
    if not exe_path and sys.platform == "win32":
        exe_path = shutil.which(cmd_name + ".exe")
    
    # 方法3: 絶対パスで直接チェック
    if not exe_path:
        chocolatey_path = f"C:\\ProgramData\\chocolatey\\bin\\{cmd_name}.exe"
        if os.path.exists(chocolatey_path):
            exe_path = chocolatey_path
    
    if exe_path:
        print(f"✓ {cmd_name} インストール済み ({exe_path})")
        return True
    else:
        print(f"❌ {cmd_name} が見つかりません")
        if install_hint:
            print(f"   インストール方法: {install_hint}")
        return False

def install_pip_packages():
    """Install Python packages"""
    packages = ["yt-dlp", "pillow"]
    print("\n🔧 Pythonパッケージをインストール中...")
    
    for package in packages:
        print(f"  インストール中: {package}...", end=" ")
        success, output = run_command(f"{sys.executable} -m pip install {package}", check=False)
        if success:
            print("✓")
        else:
            print("❌")
            print(f"    エラー: {output[:100]}")
            return False
    return True

def main():
    print("=" * 60)
    print("YouTube to GIF Converter - セットアップスクリプト")
    print("=" * 60)
    
    # Python version check
    print("\n📋 環境確認中...\n")
    if not check_python():
        sys.exit(1)
    
    # OS-specific hints
    os_name = platform.system()
    if os_name == "Windows":
        ffmpeg_hint = "choco install ffmpeg (Chocolateyが必要) または https://ffmpeg.org/download.html"
        ffprobe_hint = "FFmpegに含まれます"
    elif os_name == "Darwin":  # macOS
        ffmpeg_hint = "brew install ffmpeg"
        ffprobe_hint = "FFmpegに含まれます"
    else:  # Linux
        ffmpeg_hint = "sudo apt-get install ffmpeg"
        ffprobe_hint = "FFmpegに含まれます"
    
    # Check commands
    print("\n🔍 必要なツールを確認中...\n")
    
    all_ok = True
    
    ffmpeg_ok = check_command("ffmpeg", ffmpeg_hint)
    ffprobe_ok = check_command("ffprobe", ffprobe_hint)
    
    if not (ffmpeg_ok and ffprobe_ok):
        all_ok = False
        print("\n⚠️  FFmpegをインストールしてください")
        if os_name == "Windows":
            print("  Windows:")
            print("    1. Chocolateyをインストール: https://chocolatey.org/install")
            print("    2. choco install ffmpeg")
        elif os_name == "Darwin":
            print("  macOS:")
            print("    1. Homebrewをインストール: https://brew.sh/")
            print("    2. brew install ffmpeg")
        else:
            print("  Linux:")
            print("    sudo apt-get install ffmpeg")
    
    # Install Python packages
    print()
    if not install_pip_packages():
        print("\n⚠️  Pythonパッケージのインストールに失敗しました")
        print("以下を手動で実行してください:")
        print(f"  {sys.executable} -m pip install yt-dlp pillow")
        all_ok = False
    
    # Final status
    print("\n" + "=" * 60)
    if all_ok:
        print("✅ セットアップ完了！")
        print("\n以下のコマンドで起動してください:")
        print(f"  python youtube_to_gif.py")
    else:
        print("⚠️  いくつかの依存関係がインストールされていません")
        print("上記の指示に従ってインストールしてください")
    print("=" * 60)

if __name__ == "__main__":
    main()