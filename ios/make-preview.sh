#!/usr/bin/env bash
# Start / stop the App Store preview recording.
#
# Apple wants 15-30 s, H.264, 30 fps, at a real device resolution. simctl records at the
# device's native size (1320x2868 on a 6.9" iPhone), which is exactly the size class App
# Store Connect expects -- no scaling, no letterboxing.
#
# simctl has NO tap/type operation (only screenshot, recordVideo, enumerate), so the demo
# itself is driven from outside this script while the recording runs.
#
#   ./make-preview.sh start <udid>     # begins recording into preview/raw.mov
#   ./make-preview.sh stop             # finishes the file
#   ./make-preview.sh encode           # trim + 30fps + H.264 -> preview/preview.mov
set -euo pipefail
cd "$(dirname "$0")"
OUT=preview; mkdir -p "$OUT"
PIDFILE="$OUT/.recpid"

case "${1:-}" in
  start)
    D="${2:?need a device udid}"
    rm -f "$OUT/raw.mov"
    xcrun simctl io "$D" recordVideo --codec h264 --force "$OUT/raw.mov" >/dev/null 2>&1 &
    echo $! > "$PIDFILE"
    sleep 2
    echo "recording (pid $(cat "$PIDFILE"))"
    ;;
  stop)
    [ -f "$PIDFILE" ] || { echo "not recording"; exit 1; }
    kill -INT "$(cat "$PIDFILE")" 2>/dev/null || true
    for _ in $(seq 1 20); do kill -0 "$(cat "$PIDFILE")" 2>/dev/null || break; sleep 0.5; done
    rm -f "$PIDFILE"
    ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT/raw.mov" | awk '{printf "raw: %.1fs\n", $1}'
    ;;
  encode)
    IN="$OUT/raw.mov"
    # Trim the dead air at each end, force 30 fps, and cap at 29 s (Apple rejects 30.0+).
    START="${2:-0}"; DUR="${3:-28}"
    # A SILENT STEREO AAC TRACK IS MANDATORY. A video-only file uploads and commits fine,
    # then fails Apple's asset processing with MOV_RESAVE_STEREO and never gets a videoUrl
    # -- the only place that surfaces is appPreviews.assetDeliveryState, so poll it.
    ffmpeg -y -loglevel error -ss "$START" -i "$IN" \
      -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 -t "$DUR" \
      -vf "fps=30,scale=1320:2868:flags=lanczos" \
      -c:v libx264 -profile:v high -pix_fmt yuv420p -crf 20 \
      -c:a aac -b:a 128k -ar 44100 -ac 2 \
      -movflags +faststart -shortest "$OUT/preview.mov"
    ffprobe -v error -show_entries format=duration:stream=codec_type,codec_name,width,height,channels \
      -of default=noprint_wrappers=1 "$OUT/preview.mov"
    du -h "$OUT/preview.mov" | cut -f1
    ;;
  *) echo "usage: $0 start <udid> | stop | encode [startSec] [durSec]"; exit 1;;
esac
