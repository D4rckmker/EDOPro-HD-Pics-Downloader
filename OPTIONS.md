# EDOPro HD Pics Downloader — Python Options and Usage

[Leer en Español](OPTIONS_ES.md)

[Don’t have Python installed?](PYTHON_INSTALL.md)

## Quick Use (Python)
1. Run the script with Python and wait for `pics` detection.
2. If not detected, select the path manually.
3. (Optional) Adjust options.
4. Click **Start**.

## Options
- **Pics folder**: exact path to ProjectIgnis/EDOPro `pics`.
- **Force overwrite**: re-download everything.
- **Only missing**: download only files not present.
- **Validate existing**: re-download corrupted images.
- **Concurrency**: parallel downloads.
- **Retries**: attempts per image.
- **Timeout (s)**: per-image timeout.
- **Max KB/s**: per-download rate limit (0 = unlimited).
- **Type filter**: filter by card type (e.g., `Spell`, `Monster`, `Trap`).
- **Set filter**: filter by set name/code (e.g., `LOB (Legend of Blue Eyes White Dragon)`, `SDY (Starter Deck: Yugi)`).

## Buttons
- **Preview**: show how many images will be downloaded.
- **Start**: begin download.
- **Pause/Resume**: pause without cancel.
- **Cancel**: stop the download.

## Reports
Saved next to the script in `reports-reportes/`:
- `edopro_download_report_YYYYMMDD_HHMMSS.json`
- `edopro_download_report_YYYYMMDD_HHMMSS.md`
