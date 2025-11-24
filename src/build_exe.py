# launcher.py
import flet
from app import main   # ← CHANGE "your_main_file" to your actual filename (without .py)

if __name__ == "__main__":
    flet.app(target=main, assets_dir="assets")   # "assets" folder if you have images/icons later