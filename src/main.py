from pathlib import Path

from .graph.workflow import build_workflow


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    workflow = build_workflow()

    # Event processing will be implemented in the next stage.
    _ = workflow


if __name__ == "__main__":
    main()