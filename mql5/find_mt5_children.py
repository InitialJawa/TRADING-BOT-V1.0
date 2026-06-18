import ctypes, time
from ctypes import wintypes

user32 = ctypes.windll.user32

# Find MT5 main window
EnumWindows = user32.EnumWindows
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)

hwnd = None
results = []

def callback(h, lp):
    global hwnd
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(h, buf, 256)
    if 'Exness' in buf.value and 'MT5' in buf.value:
        hwnd = h
    return True

EnumWindows(WNDENUMPROC(callback), 0)
print(f'MT5 HWND: {hwnd}')

if not hwnd:
    exit()

# Get all child windows
child_hwnds = []
def enum_child(h, lp):
    child_hwnds.append(h)
    return True
user32.EnumChildWindows(hwnd, WNDENUMPROC(enum_child), 0)

for h in child_hwnds:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(h, buf, 256)
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(h, cls, 64)
    if buf.value or True:
        print(f'  Child HWND={h} Class={cls.value} Text="{buf.value}"')

print(f'\nTotal child windows: {len(child_hwnds)}')
