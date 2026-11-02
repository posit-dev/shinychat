import app as browser_app
from shiny import App

browser_app._restore_mode = "bookmark"


def app_ui(_request: object):
    return browser_app.app_ui


app = App(app_ui, browser_app.server, bookmark_store="server")
