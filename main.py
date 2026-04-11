# pyright: reportOptionalMemberAccess=false, reportIndexIssue=false
import textwrap
import threading
from io import BytesIO
from time import sleep
from tomllib import load as tl

import requests
from flask import Flask, request, send_file
from PIL import Image, ImageDraw, ImageFont

import env

# Global variables and caching
app = Flask(__name__)
trackdata = {}
titlefont = ImageFont.truetype("static/visitor1.ttf", size=20)
subtitlefont = ImageFont.truetype("static/visitor1.ttf", size=10)
nonasciifont = ImageFont.truetype("static/NotoSansJP-Regular.ttf", size=20)
nonasciisubfont = ImageFont.truetype("static/NotoSansJP-Regular.ttf", size=10)
if env.DARK_MODE:
    template_nowlistening = Image.open("static/template-nowlistening-dark.png")
    template_lastplayed = Image.open("static/template-lastplayed-dark.png")
else:
    template_nowlistening = Image.open("static/template-nowlistening-light.png")
    template_lastplayed = Image.open("static/template-lastplayed-light.png")
with open("pyproject.toml", "rb") as pptoml:
    version = tl(pptoml)["project"]["version"]


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
def fetch(noloop: bool = False):
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
            sleep(env.UPDATE_INTERVAL)


# Image compiler
def compile_image(tdata: dict):
    if tdata["np"]:
        canvas = template_nowlistening.copy()
    else:
        canvas = template_lastplayed.copy()
    if env.DARK_MODE:
        textcolor = "white"
    else:
        textcolor = "black"
    cover = Image.open(BytesIO(requests.get(tdata["cover"]).content))
    canvas.paste(cover, (4, 19))

    # 174px max length, 12 or 6px/char depending on font. 14ch max ASCII; ~8ch JP
    if tdata["title"].isascii():
        maxlength = 14
    else:
        maxlength = 8

    # Handle max lengths
    # Title has to be cut off after 3 lines
    # Artist and Album cap out at 29ch
    title_wrapped = textwrap.fill(tdata["title"], width=maxlength)
    lines = title_wrapped.split("\n", 3)
    title_wrapped = "\n".join(lines[:3])
    if len(tdata["artist"]) > 29:
        tdata["artist"] = tdata["artist"][:28] + "..."
    if len(tdata["album"]) > 29:
        tdata["album"] = tdata["album"][:28] + "..."

    draw = ImageDraw.Draw(canvas)

    # Check for presence of non-ASCII chars & draw text
    # Slightly messy, because if there's one among ASCII text - it goes weird
    # Also probably works poorly with Cyrillic
    if tdata["title"].isascii():
        draw.multiline_text((72, 15), title_wrapped, textcolor, titlefont)
    else:
        draw.multiline_text((72, 15), title_wrapped, textcolor, nonasciifont)
    if tdata["artist"].isascii():
        draw.text((72, 69), tdata["artist"], textcolor, subtitlefont)
    else:
        draw.text((72, 62), tdata["artist"], textcolor, nonasciisubfont)
    if tdata["album"].isascii():
        draw.text((72, 76), tdata["album"], textcolor, subtitlefont)
    else:
        draw.text((72, 74), tdata["album"], textcolor, nonasciisubfont)
    canvas.save("nowplaying.png", optimize=True)
    canvas.close()  # Minor memory optimization
    return True


# Daemonize main loop
update_thread = threading.Thread(target=fetch, daemon=True)
update_thread.start()


# Main route
@app.route("/")
def root():
    # /?force or /?force=1 to regenerate image ASAP
    if "force" in request.args:
        print("Forcing a re-fetch!")
        fetch(noloop=True)
    return send_file("nowplaying.png", mimetype="image/png")


# Direct API query with json response
@app.route("/plain")
def plain():
    tdata = handle_requests()
    return tdata


# WARNING: Live Reload tends to mess with the daemon by possibly creating several concurrent loops
if __name__ == "__main__":
    app.run(debug=True, port=env.PORT)
