"""Start MT5 Strategy Tester using Win32 API + SendInput"""
import time
import os
import ctypes
from ctypes import wintypes

VK_CONTROL = 0x11
VK_F5 = 0x74
VK_R = 0x52
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def send_key(vk, hold=None):
    """Send keyboard input using SendInput (driver-level input)"""
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [('wVk', wintypes.WORD),
                    ('wScan', wintypes.WORD),
                    ('dwFlags', wintypes.DWORD),
                    ('time', wintypes.DWORD),
                    ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]

    class INPUT(ctypes.Structure):
        _fields_ = [('type', wintypes.DWORD),
                    ('ki', KEYBDINPUT)]

    def make_input(vk, flags=0):
        ki = KEYBDINPUT(vk, 0, flags, 0, None)
        inp = INPUT(INPUT_KEYBOARD, ki)
        return inp

    inputs_list = []
    mods = []
    if hold:
        if isinstance(hold, list):
            mods = hold
        else:
            mods = [hold]
    
    for m in mods:
        inputs_list.append(make_input(m))
    inputs_list.append(make_input(vk))
    inputs_list.append(make_input(vk, KEYEVENTF_KEYUP))
    for m in reversed(mods):
        inputs_list.append(make_input(m, KEYEVENTF_KEYUP))
    
    InputArray = INPUT * len(inputs_list)
    pInputs = InputArray(*inputs_list)
    return user32.SendInput(len(inputs_list), ctypes.byref(pInputs), ctypes.sizeof(INPUT))

def force_foreground(hwnd):
    """Force window to foreground using AttachThreadInput trick"""
    # Get current foreground window's thread
    fore_hwnd = user32.GetForegroundWindow()
    fore_tid = user32.GetWindowThreadProcessId(fore_hwnd, None)
    target_tid = user32.GetWindowThreadProcessId(hwnd, None)
    our_tid = kernel32.GetCurrentThreadId()
    
    # Attach to both threads
    if fore_tid != target_tid:
        user32.AttachThreadInput(our_tid, fore_tid, True)
        user32.AttachThreadInput(our_tid, target_tid, True)
    
    user32.BringWindowToTop(hwnd)
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    
    if fore_tid != target_tid:
        user32.AttachThreadInput(our_tid, fore_tid, False)
        user32.AttachThreadInput(our_tid, target_tid, False)

# Find MT5 window by HWND
# Use EnumWindows to find it
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)

hwnds = []
def callback(hwnd, lParam):
    length = user32.GetWindowTextLengthW(hwnd) + 1
    title = ctypes.create_unicode_buffer(length)
    user32.GetWindowTextW(hwnd, title, length)
    if 'Exness' in title.value and 'MT5' in title.value:
        hwnds.append(hwnd)
    return True

EnumWindows(EnumWindowsProc(callback), 0)

if not hwnds:
    print("MT5 window not found!")
    exit(1)

hwnd = hwnds[0]
print(f"Found HWND: {hwnd}")

# Force foreground
force_foreground(hwnd)
time.sleep(1)

# Ctrl+R
send_key(VK_R, VK_CONTROL)
print("Ctrl+R sent")
time.sleep(2)

# F5
send_key(VK_F5)
print("F5 sent")
time.sleep(5)

# Check log
log_dir = os.path.expandvars(
    r'%APPDATA%\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\Tester\logs')
logs = sorted(os.listdir(log_dir), reverse=True)
if logs:
    log_path = os.path.join(log_dir, logs[0])
    with open(log_path, 'rb') as f:
        data = f.read()
    text = data.decode('utf-8', errors='replace')
    lines = text.split('\n')
    # Print last 15 non-empty lines
    relevant = [l for l in lines if any(kw in l for kw in 
        ['OPEN ', 'final balance', 'BAR>', 'ORDER FAIL', 'OPEN ', 'ERROR'])]
    if relevant:
        for l in relevant[-10:]:
            print(l.strip())
    else:
        print("No relevant lines found. Last 5 lines:")
        for l in lines[-5:]:
            print(l.strip())
print("Done")
