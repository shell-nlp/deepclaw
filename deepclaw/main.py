import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if __name__ == "__main__":
    import uvicorn
    from deepclaw.web_backend.app import create_app

    uvicorn.run(create_app(), host="0.0.0.0", port=7869)
