import sqlite3
from pathlib import Path


class StateStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.connection = sqlite3.connect(database_path)

    def close(self) -> None:
        self.connection.close()