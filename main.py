# pyright: reportOptionalMemberAccess=false, reportIndexIssue=false
import textwrap
import threading
import time
import tomllib
from io import BytesIO

import requests
from flask import Flask, request, send_file
from PIL import Image, ImageDraw, ImageFont

import env

# Global variables
app = Flask(__name__)
trackdata = {}
titlefont = ImageFont.truetype("static/visitor1.ttf", size=20)
subtitlefont = ImageFont.truetype("static/visitor1.ttf", size=10)
nonasciifont = ImageFont.truetype("static/NotoSansJP-Regular.ttf", size=20)
nonasciisubfont = ImageFont.truetype("static/NotoSansJP-Regular.ttf", size=10)
with open("pyproject.toml", "rb") as pptoml:
    version = tomllib.load(pptoml)["project"]["version"]


# Main function to get the data for the last played song
def handle_requests():
    r = requests.get(
        f"http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={env.LFM_USERNAME}&api_key={env.LFM_API_KEY}&format=json&limit=1",
        headers={"User-Agent": f"np/{version} (+https://github.com/voidlynx/np)"},
    ).json()
    try:
        rawtrack = r["recenttracks"]["track"][0]
    # If the request breaks, send error to calling function
    except KeyError as e:
        return {"error": str(e)}
    tdata = {}
    # Check if the track in question is "Now Playing" or not
    try:
        tdata["np"] = bool(rawtrack["@attr"]["nowplaying"])
    except KeyError:
        tdata["np"] = False
    tdata["artist"] = rawtrack["artist"]["#text"]
    tdata["title"] = rawtrack["name"]
    tdata["album"] = rawtrack["album"]["#text"]
    tdata["cover"] = rawtrack["image"][1]["#text"]
    # Handle optonal fields
    if tdata["album"] == "":
        tdata["album"] = "Unknown Album"
    if tdata["cover"] == "":
        tdata["cover"] = (
            "https://lastfm.freetls.fastly.net/i/u/64s/4128a6eb29f94943c9d206c08e625904.jpg"
        )
    return tdata


# Main loop
def tdatafetch(noloop: bool = False):
    global trackdata
    while True:
        try:
            tdata = handle_requests()
            if tdata.get("error") is not None:
                print("ERROR:", tdata["error"])
            elif tdata != trackdata or noloop:
                compile_image(tdata)
                trackdata = tdata
        except Exception as e:
            print("ERROR:", e)
        if noloop:
            break
        else:
            time.sleep(60)


# Image compiler
def compile_image(tdata: dict):
    if tdata["np"]:
        result = Image.open("static/template-nowlistening-dark.png")
    else:
        result = Image.open("static/template-lastplayed-dark.png")
    cover = Image.open(BytesIO(requests.get(tdata["cover"]).content))
    result.paste(cover, (4, 19))

    # 174px max length, 12 or 6px/char depending on font. 14ch max ASCII; 8ch JP
    if tdata["title"].isascii():
        maxlength = 14
    else:
        maxlength = 8
    # Three lines max, otherwise it overflows onto artist/album
    title_wrapped = textwrap.fill(tdata["title"], width=maxlength)
    lines = title_wrapped.split("\n", 3)
    title_wrapped = "\n".join(lines[:3])
    draw = ImageDraw.Draw(result)

    # Check for presence of non-ASCII chars
    # Slightly messy, because if there's one among ASCII text - it goes weird
    # Also probably works poorly with Cyrillic
    if not tdata["title"].isascii():
        draw.multiline_text((72, 15), title_wrapped, "white", nonasciifont)
    else:
        draw.multiline_text((72, 15), title_wrapped, "white", titlefont)
    if not tdata["artist"].isascii():
        draw.text((72, 69), tdata["artist"], "white", nonasciisubfont)
    else:
        draw.text((72, 69), tdata["artist"], "white", subtitlefont)
    if not tdata["album"].isascii():
        draw.text((72, 76), tdata["album"], "white", nonasciisubfont)
    else:
        draw.text((72, 76), tdata["album"], "white", subtitlefont)
    result.save("nowplaying.png", optimize=True)
    return True


# Daemonize main loop
update_thread = threading.Thread(target=tdatafetch, daemon=True)
update_thread.start()


# Main route
@app.route("/")
def root():
    # /?force or /?force=1 to regenerate image ASAP
    if "force" in request.args:
        print("Forcing a re-fetch!")
        tdatafetch(noloop=True)
    return send_file("nowplaying.png", mimetype="image/png")


# Direct API query with json response
@app.route("/plain")
def plain():
    tdata = handle_requests()
    return tdata


if __name__ == "__main__":
    app.run(debug=True, port=env.PORT)
