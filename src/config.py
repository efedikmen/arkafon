"""Filesystem layout for the ArkaFon static-build pipeline.

Resolves every path the pipeline writes to or reads from relative to the
repo root, so the same constants work whether the code runs from the
project root, from CI, or from a sibling worktree.
"""
import os

BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RAW_DATA_DIR: str = os.path.join(BASE_DIR, "data", "raw")
PROCESSED_DATA_DIR: str = os.path.join(BASE_DIR, "data", "processed")

MASTER_DATA_PATH: str = os.path.join(PROCESSED_DATA_DIR, "master_flow_data.parquet")
MARKET_DATA_PATH: str = os.path.join(PROCESSED_DATA_DIR, "market_data.parquet")
