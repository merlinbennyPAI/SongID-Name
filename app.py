import os
import subprocess
import json
import tempfile
from flask import Flask, request, jsonify

# Read AcoustID API key from environment (set in Render)
ACOUSTID_KEY = os.environ.get("ACOUSTID_KEY")

app = Flask(__name__)

# Health check / root endpoint (required for MCP & platform validation)
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "ok",
        "service": "Song Identification API",
        "endpoint": "/identify-song",
        "method": "POST"
    }), 200


# Main song identification endpoint
@app.route("/identify-song", methods=["POST"])
def identify_song():
    # Expect audio file via multipart/form-data with key "file"
    if "file" not in request.files:
        return jsonify({"error": "no_file_provided"}), 400

    f = request.files["file"]

    infile = tempfile.NamedTemporaryFile(delete=False, suffix=".input")
    f.save(infile.name)
    infile_path = infile.name

    # Convert input audio to WAV mono 44.1kHz using ffmpeg
    wav_path = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", infile_path,
        "-ac", "1",
        "-ar", "44100",
        "-vn",
        wav_path
    ]

    try:
        subprocess.check_output(ffmpeg_cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        return jsonify({
            "error": "ffmpeg_failed",
            "detail": e.output.decode(errors="ignore")
        }), 500

    # Generate fingerprint using fpcalc (Chromaprint)
    try:
        fp_output = subprocess.check_output(
            ["fpcalc", "-json", wav_path],
            stderr=subprocess.DEVNULL
        )
        fp_json = json.loads(fp_output)
        fingerprint = fp_json.get("fingerprint")
        duration = int(fp_json.get("duration", 0))
    except Exception as e:
        return jsonify({
            "error": "fpcalc_failed",
            "detail": str(e)
        }), 500

    # Ensure AcoustID key is available
    if not ACOUSTID_KEY:
        return jsonify({"error": "missing_acoustid_key"}), 500

    # Query AcoustID API
    import requests

    params = {
        "client": ACOUSTID_KEY,
        "fingerprint": fingerprint,
        "duration": duration,
        "meta": "recordings+releases+releasegroups+tracks"
    }

    try:
        r = requests.get(
            "https://api.acoustid.org/v2/lookup",
            params=params,
            timeout=30
        )
        res = r.json()
    except Exception as e:
        return jsonify({
            "error": "acoustid_request_failed",
            "detail": str(e)
        }), 500

    # Parse best match
    results = res.get("results", [])
    if not results:
        return jsonify({"status": "no_match"}), 200

    best = max(results, key=lambda x: x.get("score", 0))
    score = best.get("score", 0)

    title = None
    artist = None
    mbid = None

    recordings = best.get("recordings", [])
    if recordings:
        rec = recordings[0]
        title = rec.get("title")
        mbid = rec.get("id")
        artists = rec.get("artists", [])
        if artists:
            artist = artists[0].get("name")

    return jsonify({
        "status": "ok",
        "method": "fingerprint",
        "score": score,
        "title": title,
        "artist": artist,
        "musicbrainz_id": mbid,
        "raw": res
    }), 200


# Start Flask app (Render uses the PORT environment variable)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


