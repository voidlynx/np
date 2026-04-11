# pyright: reportOptionalMemberAccess=false, reportIndexIssue=false
import os
import textwrap
import threading
import time
from io import BytesIO
from types import NoneType

import pylast
import requests
from flask import Flask, send_file
from PIL import Image, ImageDraw, ImageFont

import env

app = Flask(__name__)

trackdata = {}
titlefont = ImageFont.truetype("static/visitor1.ttf", size=20)
subtitlefont = ImageFont.truetype("static/visitor1.ttf", size=10)

# Authorising the account through the browser
SESSION_KEY_FILE = ".session_key"
network = pylast.LastFMNetwork(env.LFM_API_KEY, env.LFM_API_SECRET)
if not os.path.exists(SESSION_KEY_FILE):
    skg = pylast.SessionKeyGenerator(network)
    url = skg.get_web_auth_url()

    print(f"Please authorize this script to access your account: {url}\n")
    import time
    import webbrowser

    webbrowser.open(url)

    while True:
        try:
            session_key = skg.get_web_auth_session_key(url)
            with open(SESSION_KEY_FILE, "w") as f:
                f.write(session_key)
            break
        except pylast.WSError:
            time.sleep(1)
else:
    session_key = open(SESSION_KEY_FILE).read()

network.session_key = session_key
me = network.get_user(env.LFM_USERNAME)


def tdatafetch():
    global trackdata
    while True:
        tdata = {}
        track = me.get_now_playing()
        tdata["np"] = True
        if type(track) is NoneType:
            track = me.get_recent_tracks(1)[0].track
            tdata["np"] = False
        tdata["title"] = track.get_title()
        tdata["artist"] = track.get_artist().name
        try:
            tdata["album"] = track.get_album().title
            tdata["cover"] = track.get_cover_image(pylast.SIZE_MEDIUM)
        except pylast.WSError:
            tdata["album"] = None
            tdata["cover"] = None
        if tdata != trackdata:
            compile_image(tdata)
            trackdata = tdata
        else:
            continue
        time.sleep(60)


def compile_image(tdata: dict):
    if tdata["np"]:
        result = Image.open("static/template-nowlistening-dark.png")
    else:
        result = Image.open("static/template-lastplayed-dark.png")
    if tdata["cover"] is None:
        # Placeholder
        tdata["cover"] = (
            "https://lastfm.freetls.fastly.net/i/u/64s/4128a6eb29f94943c9d206c08e625904.jpg"
        )
    cover = Image.open(BytesIO(requests.get(tdata["cover"]).content))
    result.paste(cover, (4, 19))
    # 174px max length, 12 or 6px/char depending on font. 14ch before title wrap
    title_wrapped = textwrap.fill(tdata["title"], width=14)
    draw = ImageDraw.Draw(result)
    draw.multiline_text((72, 15), title_wrapped, "white", titlefont)
    draw.text((72, 69), tdata["artist"], "white", subtitlefont)
    if tdata["album"] is not None:
        draw.text((72, 76), tdata["album"], "white", subtitlefont)
    else:
        draw.text((72, 76), "Unknown Album", "white", subtitlefont)
    result.save("nowplaying.png", optimize=True)
    return True


update_thread = threading.Thread(target=tdatafetch, daemon=True)
update_thread.start()


@app.route("/")
def root():
    return send_file("nowplaying.png", mimetype="image/png")


@app.route("/plain")
def plain():
    track = me.get_now_playing()
    if type(track) is NoneType:
        track = me.get_recent_tracks(1)[0].track
    tdata = {}
    tdata["title"] = track.get_title()
    tdata["artist"] = track.get_artist().name
    try:
        tdata["album"] = track.get_album().title
        tdata["cover"] = track.get_cover_image(pylast.SIZE_MEDIUM)
    except pylast.WSError:
        tdata["album"] = None
        tdata["cover"] = None
    return tdata


if __name__ == "__main__":
    app.run(debug=True, port=env.PORT)
