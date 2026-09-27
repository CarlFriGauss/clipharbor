"""Windowless packaged entry point; intentionally separate from the dev server."""
from mediaforge.desktop import main

if __name__ == "__main__":
    raise SystemExit(main())
