"""
main.py

Runs the full ETL pipeline in order:
    Extract -> Transform -> Validate -> Load

If any essential stage fails, the pipeline stops and exits with code 1,
so GitHub Actions marks the run as failed.

Data are MODEL-BASED ESTIMATES (Open-Meteo / CAMS), not direct
ground-station measurements.
"""

import logging
import sys
import time
from pathlib import Path

# Make the files inside src/ importable (config, extract, ...).
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import extract  # noqa: E402
import load  # noqa: E402
import transform  # noqa: E402
import validate  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("main")


def run_pipeline():
    started = time.time()

    logger.info("=== STAGE 1/4: EXTRACT ===")
    extracted = extract.extract_all()

    logger.info("=== STAGE 2/4: TRANSFORM ===")
    hourly_df, current_df = transform.transform_all(extracted)

    logger.info("=== STAGE 3/4: VALIDATE ===")
    valid_hourly, valid_current = validate.validate_all(hourly_df, current_df)

    logger.info("=== STAGE 4/4: LOAD ===")
    hourly_count, current_count = load.load_all(valid_hourly, valid_current)

    logger.info(
        "PIPELINE SUCCESS in %.1f s: %d hourly rows, %d current rows upserted",
        time.time() - started,
        hourly_count,
        current_count,
    )


if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception as exc:
        logger.error("PIPELINE FAILED: %s", exc)
        sys.exit(1)