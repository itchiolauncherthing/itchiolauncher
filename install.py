#!/usr/bin/env python3
import os
import shutil
import sqlite3
import tkinter as tk
from tkinter import filedialog
import subprocess 
import sys
installdir = tk.filedialog.askdirectory(title="Where would you like to install?")
os.makedirs(os.path.join(installdir, "cache", "images"), exist_ok=True)
os.makedirs(os.path.join(installdir, "cache", "zips"), exist_ok=True)
shutil.move(os.path.join(os.getcwd(), "itchiolauncher.py"), os.path.join(installdir, "itchiolauncher.py"))
shutil.move(os.path.join(os.getcwd(), "gui.py"), os.path.join(installdir, "gui.py"))
startconn = sqlite3.connect(os.path.join(installdir, "cache/games.sql"))
settingsconn = sqlite3.connect(os.path.join(installdir, "settings.sql"))
c = startconn.cursor()
s = settingsconn.cursor()
try:
	c.execute('CREATE TABLE allgames (name text, url text, cachedimage bool, localimage text, imageurl text, windows bool, linux bool, mac bool, windows_downloaded bool, linux_downloaded bool, mac_downloaded bool, claimurl text, gameid text);')
	c.execute('CREATE TABLE downloadedgames (name text, windowsinstall text, linuxinstall text, macinstall text, windowsexec text, linuxexec text, macexec text, defaultexecuteable text, gameid text);')
	startconn.commit()
	s.execute('CREATE TABLE defaultsettings (setting text, value text)')
	settingsconn.commit()
except sqlite3.OperationalError as e:
	print("There's already a sqlite database here")
	sys.exit()

try:
	import requests
except Exception as e:
	p = subprocess.check_call([sys.executable], "-m", "pip", "install requests")
try:
	from bs4 import BeautifulSoup
except:
	p = subprocess.check_call([sys.executable], "-m", "pip", "install beautifulsoup4")

