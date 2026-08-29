# -*- coding: utf-8 -*-
"""Fullscreen Up/Down skip, only while a Douyin video is playing."""
from __future__ import annotations

import os

import xbmc
import xbmcgui
import xbmcvfs

KEYMAP_NAME = "plugin.video.douyin.play.xml"
PLAYING_PROP = "plugin.video.douyin.playing"
SKIP_PROP = "plugin.video.douyin.skipping"
SKIP_NEXT = "RunPlugin(plugin://plugin.video.douyin/?action=skip_next)"
SKIP_PREV = "RunPlugin(plugin://plugin.video.douyin/?action=skip_prev)"
# Remote Down = next video, Up = previous.
KEYMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<keymap>
  <FullscreenVideo>
    <keyboard>
      <down>%(next)s</down>
      <up>%(prev)s</up>
      <pagedown>%(next)s</pagedown>
      <pageup>%(prev)s</pageup>
    </keyboard>
    <remote>
      <down>%(next)s</down>
      <up>%(prev)s</up>
      <pagedown>%(next)s</pagedown>
      <pageup>%(prev)s</pageup>
      <skipnext>%(next)s</skipnext>
      <skipprevious>%(prev)s</skipprevious>
    </remote>
  </FullscreenVideo>
  <VideoOSD>
    <keyboard>
      <down>%(next)s</down>
      <up>%(prev)s</up>
    </keyboard>
    <remote>
      <down>%(next)s</down>
      <up>%(prev)s</up>
      <skipnext>%(next)s</skipnext>
      <skipprevious>%(prev)s</skipprevious>
    </remote>
  </VideoOSD>
  <VideoMenu>
    <remote>
      <down>%(next)s</down>
      <up>%(prev)s</up>
    </remote>
  </VideoMenu>
</keymap>
""" % {
    "next": SKIP_NEXT,
    "prev": SKIP_PREV,
}


def _keymap_path():
    folder = xbmcvfs.translatePath("special://profile/keymaps")
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except OSError:
            xbmcvfs.mkdirs(folder)
    return os.path.join(folder, KEYMAP_NAME)


def mark_douyin_playing():
    xbmcgui.Window(10000).setProperty(PLAYING_PROP, "1")


def clear_douyin_playing():
    xbmcgui.Window(10000).clearProperty(PLAYING_PROP)


def douyin_keymap_wanted():
    win = xbmcgui.Window(10000)
    if win.getProperty(SKIP_PROP) == "1":
        return True
    path = (
        (xbmc.getInfoLabel("Player.Filenameandpath") or "")
        + " "
        + (xbmc.getInfoLabel("Player.FileName") or "")
    ).lower()
    if "plugin.video.bili" in path or "plugin.video.acfun" in path or "plugin.video.bilibili" in path:
        return False
    if "plugin.video." in path and "plugin.video.douyin" not in path:
        return False
    if not xbmc.Player().isPlaying() and win.getProperty(PLAYING_PROP) != "1":
        return False
    return win.getProperty(PLAYING_PROP) == "1"


def install_play_keymap():
    path = _keymap_path()
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(KEYMAP_XML)
    except OSError:
        return
    xbmc.executebuiltin("ReloadKeymaps")


def remove_play_keymap():
    path = _keymap_path()
    existed = False
    try:
        if os.path.isfile(path):
            os.remove(path)
            existed = True
    except OSError:
        existed = False
    if existed:
        xbmc.executebuiltin("ReloadKeymaps")
