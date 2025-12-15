import os
import subprocess
import json
import tempfile
from flask import Flask, request, jsonify

ACOUSTID_KEY = os.environ.get("ACOUSTID_KEY")

app = Flask(__name__)

# Health / sanity check route
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "SongID API running",
        "endpoints": {
            "identify": "POST /identify-song"
        }
    })

@app.route("/identify-song", methods=["POST"])
def identify_song():
    # Check file
    if "file" not in request.files:
        return jsonify({"error": "no_file_provided"}), 400

    f = request.files["file"]

    # Save uploaded file
    infile = tempfile.NamedTemporaryFile(delete=False, suffix=".input")
    f.save(infile.name)
    infile_path = infile.name

    # Convert to wav
    wav_path = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", infile_path,
        "-ac", "1", "-ar", "44100", "-vn", wav_path
    ]

    try:
        subprocess.check_output(ffmpeg_cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        return jsonify({
            "error": "ffmpeg_failed",
            "detail": e.output.decode(errors="ignore")
        }), 500

    # Generate fingerprint
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

    if not ACOUSTID_KEY:
        return jsonify({"error": "missing_acoustid_key"}), 500

    # Query AcoustID
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

    results = res.get("results", [])
    if not results:
        return jsonify({"status": "no_match"}), 200

    best = max(results, key=lambda x: x.get("score", 0))

    title = artist = mbid = None
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
        "score": best.get("score", 0),
        "title": title,
        "artist": artist,
        "musicbrainz_id": mbid
    }), 200



