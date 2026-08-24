#!/usr/bin/env python3
"""Pre-generate all time-announcement mp3s with gtts-cli.

Creates ``say_time_HH_MM_AM/PM.mp3`` for every minute of the day in the
sound_effects directory, so the pomodoro never needs internet again.

Usage:
    python3 scripts/generate_say_times.py          # sequential (safe)
    python3 scripts/generate_say_times.py --jobs 4 # parallel (faster)

Resumable: existing files are skipped, so you can re-run anytime.
"""

import argparse
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from pomodoro_lib.constants import SOUNDS_DIR  # noqa: E402

PREFIX = "say_time"


def minute_text(hour: int, minute: int, meridiem: str) -> str:
    """Return the spoken sentence for a given time."""
    return f"The time is {hour:02d}:{minute:02d} {meridiem}"


def minute_filename(hour: int, minute: int, meridiem: str) -> str:
    """Return the cache filename for a given time."""
    return f"{PREFIX}_{hour:02d}_{minute:02d}_{meridiem}.mp3"


def generate_one(hour: int, minute: int, meridiem: str) -> tuple[str, str]:
    """Generate one mp3 if missing. Returns (filename, status)."""
    out_path = SOUNDS_DIR / minute_filename(hour, minute, meridiem)
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path.name, "cached"

    text = minute_text(hour, minute, meridiem)
    result = subprocess.run(
        ["gtts-cli", text, "--output", str(out_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return out_path.name, f"FAILED: {result.stderr.strip()[:100]}"
    return out_path.name, "generated"


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-generate say_time mp3s")
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Parallel workers (default 1; be gentle with Google's API)",
    )
    args = parser.parse_args()

    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)

    # Build the full list: 12 hours × 60 minutes × AM/PM = 1440
    tasks = [
        (hour, minute, meridiem)
        for hour in range(1, 13)
        for minute in range(60)
        for meridiem in ("AM", "PM")
    ]

    # Count how many already exist
    existing = sum(
        1 for h, m, mer in tasks if (SOUNDS_DIR / minute_filename(h, m, mer)).exists()
    )
    print(f"📁 {SOUNDS_DIR}")
    print(
        f"🎯 {len(tasks)} times total, {existing} already cached, "
        f"{len(tasks) - existing} to generate"
    )

    start = time.time()
    done = generated = failed = 0

    if args.jobs > 1:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = {
                pool.submit(generate_one, h, m, mer): (h, m, mer) for h, m, mer in tasks
            }
            for fut in as_completed(futures):
                name, status = fut.result()
                done += 1
                if status == "generated":
                    generated += 1
                elif status.startswith("FAILED"):
                    failed += 1
                    print(f"  ✗ {name}: {status}")
                if done % 50 == 0:
                    _progress(done, len(tasks), start)
    else:
        for h, m, mer in tasks:
            name, status = generate_one(h, m, mer)
            done += 1
            if status == "generated":
                generated += 1
            elif status.startswith("FAILED"):
                failed += 1
                print(f"  ✗ {name}: {status}")
            if done % 25 == 0:
                _progress(done, len(tasks), start)

    elapsed = time.time() - start
    print(
        f"\n✅ Done in {elapsed:.0f}s: {generated} generated, "
        f"{failed} failed, {len(tasks) - generated - failed} cached"
    )


def _progress(done: int, total: int, start: float) -> None:
    elapsed = time.time() - start
    rate = done / elapsed if elapsed > 0 else 0
    remaining = (total - done) / rate if rate > 0 else 0
    print(
        f"\r  {done}/{total}  ({rate:.1f}/s, ~{remaining:.0f}s left)   ",
        end="",
        flush=True,
    )


if __name__ == "__main__":
    main()
