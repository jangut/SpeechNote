"""
SpeechNote entry.

python main.py          # CLI mode
python main.py --gui    # GUI mode
"""

import sys

from config import Config
from app import Application


def main() -> None:
    """Program entry."""
    config = Config()
    app = Application(config)
    app.initialize()

    if "--cli" in sys.argv:
        app.start()
        app.wait()
    else:
        from gui import start_gui
        start_gui(config, app)


if __name__ == "__main__":
    main()
