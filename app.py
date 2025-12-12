import os, subprocess, json, tempfile
from flask import Flask, request, jsonify

ACOUSTID_KEY = os.environ.get("ACOUSTID_KEY")  # set this on Render as a secret

app = Flask(__name__)

@app.route("/identify-song", methods=["POST"])
def identify_song():
    # Accept file via multipart/form-data 'file'
    if 'file' in request.files:
        f = request.files['file']
        infile = tempfile.NamedTemporaryFile(delete=False, suffix=".input")
        f.save(infile.name)
        infile_path = infile.name
    else:
        return jsonify({"error":"no_file_provided"}), 400

    # convert to wav mono 44100 using ffmpeg
    wav_path = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
    ffmpeg_cmd = ["ffmpeg", "-y", "-i", infile_path, "-ac", "1", "-ar", "44100", "-vn", wav_path]
    try:
        subprocess.check_output(ffmpeg_cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        return jsonify({"error":"ffmpeg_failed","detail": e.output.decode(errors='ignore')}), 500

    # run fpcalc to get fingerprint (json)
    try:
        fp_output = subprocess.check_output(["fpcalc", "-json", wav_path], stderr=subprocess.DEVNULL)
        fp_json = json.loads(fp_output)
        fingerprint = fp_json.get("fingerprint")
        duration = int(fp_json.get("duration", 0))
    except Exception as e:
        return jsonify({"error":"fpcalc_failed","detail": str(e)}), 500

    # call AcoustID lookup
    if not ACOUSTID_KEY:
        return jsonify({"error":"missing_acoustid_key"}), 500

    import requests
    params = {
        "client": ACOUSTID_KEY,
        "fingerprint": fingerprint,
        "duration": duration,
        "meta": "recordings+releases+releasegroups+tracks"
    }
    try:
        r = requests.get("https://api.acoustid.org/v2/lookup", params=params, timeout=30)
        res = r.json()
    except Exception as e:
        return jsonify({"error":"acoustid_request_failed","detail": str(e)}), 500

    # parse best match
    results = res.get("results", [])
    if not results:
        return jsonify({"status":"no_match"}), 200

    best = max(results, key=lambda x: x.get("score", 0))
    score = best.get("score", 0)

    # extract title/artist from recordings if present
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
        "status":"ok",
        "method":"fingerprint",
        "score": score,
        "title": title,
        "artist": artist,
        "musicbrainz_id": mbid,
        "raw": res
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)))
