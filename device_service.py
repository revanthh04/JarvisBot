import platform
import psutil
import io
import os
import subprocess

def get_system_stats() -> dict:
    cpu_percent = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    battery = psutil.sensors_battery()

    battery_info = "N/A"
    if battery:
        battery_info = f"{battery.percent}% ({'Plugged in' if battery.power_plugged else 'On Battery'})"

    return {
        "os": f"{platform.system()} {platform.release()}",
        "cpu_percent": f"{cpu_percent}%",
        "ram_used": f"{round(mem.used / (1024**3), 2)} GB / {round(mem.total / (1024**3), 2)} GB ({mem.percent}%)",
        "disk_free": f"{round(disk.free / (1024**3), 2)} GB free of {round(disk.total / (1024**3), 2)} GB",
        "battery": battery_info
    }

def take_screenshot() -> bytes:
    if platform.system() != "Windows":
        raise RuntimeError("Desktop screenshots require Jarvis to run locally on your PC (Currently hosted on Cloud Linux).")
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        bio = io.BytesIO()
        bio.name = 'screenshot.png'
        img.save(bio, 'PNG')
        bio.seek(0)
        return bio.getvalue()
    except Exception as e:
        raise RuntimeError(f"Screenshot failed: {e}")

def lock_workstation() -> bool:
    if platform.system() == "Windows":
        import ctypes
        return bool(ctypes.windll.user32.LockWorkStation())
    return False

def set_volume(action: str) -> str:
    """Action: mute, unmute, up, down"""
    if platform.system() != "Windows":
        return "PC volume controls require Jarvis to run locally on your PC."
    action = action.lower().strip()
    key_map = {
        "mute": "0xAD",
        "down": "0xAE",
        "up": "0xAF"
    }
    if action in key_map:
        cmd = f"""powershell -c "$wscript = New-Object -ComObject WScript.Shell; $wscript.SendKeys([char]{key_map[action]})" """
        subprocess.run(cmd, shell=True)
        return f"Volume action '{action}' executed."
    return f"Volume action '{action}' executed."

def get_clipboard() -> str:
    if platform.system() == "Windows":
        try:
            res = subprocess.run(["powershell", "-command", "Get-Clipboard"], capture_output=True, text=True)
            return res.stdout.strip()
        except Exception as e:
            return f"Error reading clipboard: {e}"
    return "Clipboard access requires Jarvis to run locally on your PC."

def set_clipboard(text: str) -> str:
    if platform.system() == "Windows":
        try:
            p = subprocess.Popen(["clip"], stdin=subprocess.PIPE, text=True)
            p.communicate(input=text)
            return f"Copied '{text[:30]}...' to clipboard."
        except Exception as e:
            return f"Error setting clipboard: {e}"
    return "Clipboard access requires Jarvis to run locally on your PC."
