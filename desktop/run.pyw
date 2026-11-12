import sys
import ctypes

# Hide console window
if sys.platform == 'win32':
    wh = ctypes.windll.kernel32.GetConsoleWindow()
    if wh:
        ctypes.windll.user32.ShowWindow(wh, 0)

from main import main
main()
