import os, subprocess, json, tempfile
from flask import Flask, request, jsonify

ACOUSTID_KEY = os.environ.get("ACOUSTID_KEY")

app = Flask(__name__)

@app.route("/")
def home():
    return {
        "status": "SongID API running",
        "endpoint": "/identify-song (POST)"
    }

@app.route("/identify-song", methods=["POST"])
def identify_song():
    if 'file' not in request.files:
        return jsonify({"error": "no_file_provided"}), 400

    f = request.files['file']
    infile = tempfile.NamedTemporaryFile(delete=False)
    f.save(infile.name)

    wav_path = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name

    try:
        subprocess.check_output([
            "ffmpeg", "-y", "-i", infile.name,
            "-ac", "1", "-ar", "44100", wav_path
        ])
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "ffmpeg_failed", "detail": str(e)}), 500

    try:
        fp = subprocess.check_output(["fpcalc", "-json", wav_path])
        fp_data = json.loads(fp)
    except Exception as e:
        return jsonify({"error": "fpcalc_failed", "detail": str(e)}), 500

    if not ACOUSTID_KEY:
        return jsonify({"error": "missing_acoustid_key"}), 500

    import requests
    r = requests.get(
        "https://api.acoustid.org/v2/lookup",
        params={
            "client": ACOUSTID_KEY,
            "fingerprint": fp_data["fingerprint"],
            "duration": int(fp_data["duration"]),
            "meta": "recordings"
        },
        timeout=30
    )

    data = r.json()
    results = data.get("results", [])

    if not results:
        return jsonify({"status": "no_match"}), 200

    best = max(results, key=lambda x: x.get("score", 0))
    rec = best.get("recordings", [{}])[0]

    return jsonify({
        "status": "ok",
        "title": rec.get("title"),
        "artist": rec.get("artists", [{}])[0].get("name"),
        "score": best.get("score")
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
