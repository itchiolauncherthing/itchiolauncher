#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import urllib
import os
import pickle
import sqlite3
import enum
import zipfile
import threading
import re
import shutil

class platforms(enum.Enum):
	windows = 0
	linux = 1
	mac = 2


class ItchioLauncher:
	class Game:
		def __init__(self,name):
			self.name = name

	def __init__(self):
		self.session = requests.Session()
		self.session.headers.update({'User-Agent':'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:79.0) Gecko/20100101 Firefox/79.0'})
		self.homedir = os.getcwd()
		self.sqlconn = sqlite3.connect(os.path.join(self.homedir,"cache", "games.sql"), check_same_thread=False)
		self.sqllock = threading.Lock()

	def login(self,username,password,save=False):
		self.session.get('https://itch.io')
		data = {'csrf_token':urllib.parse.unquote(self.session.cookies['itchio_token']),'username':username,'password':password}
		self.session.post('https://itch.io/login',data=data)
		if save:
			with open(os.path.join(self.homedir,"cookies"),'wb') as f:
				pickle.dump(self.session.cookies,f)

	# Tries to load the previous session if it's there. Returns true on success, False on failure
	def load_saved_session(self):
		cookiepath=os.path.join(self.homedir,"cookies") 
		if os.path.exists(cookiepath):
			try:
				with open(cookiepath,"rb") as f:
					self.session.cookies.update(pickle.load(f))
				return True
			except Exception as e:
				print(e)
				return False

	def load_bundles(self):
		responseText = self.session.get('https://itch.io/my-purchases/bundles').text
		soup = BeautifulSoup(responseText,'html.parser')
		self.bundles = {}
		for bundle in soup.findChild('section',attrs={'class':'bundle_keys'}).findChildren('a'):
			self.bundles[bundle.getText()] = 'https://itch.io' + bundle.get('href')

	def process_bundle(self,bundle,maxpages=0):
		basepage = self.bundles[bundle]
		page = self.session.get(basepage).text
		listpage = BeautifulSoup(page,'html.parser')
		if maxpages == 0:
			maxpages = int(listpage.findChild('span',attrs={'class':'pager_label'}).findChild('a').getText())
		for i in range(1,maxpages+1):
			page = self.session.get(basepage+'?page=%d' % i).text
			listpage = BeautifulSoup(page,'html.parser')
			for gamerow in listpage.findChildren('div',attrs={'class':'game_row'}):
				imageurl = gamerow.findChild('div',attrs={'class':'game_thumb'}).get('data-background_image')
				gamename = gamerow.findChild('h2',attrs={'class':'game_title'}).getText()
				gamepage = gamerow.findChild('a').get('href')
				gameidElement = gamerow.findChild("input",attrs={"name":"game_id"})
				if gameidElement:
					gameid = gameidElement["value"]
				else:
					gameid = ""
				if gamerow.findChild('span',attrs={'class':'icon icon-tux'}):
					linux = True
				if gamerow.findChild('span',attrs={'class':'icon icon-apple'}):
					mac = True
				if gamerow.findChild('span',attrs={'class':'icon icon-windows8'}):
					windows = True
				claimpage = basepage
				self.cache_game(gamename,imageurl=imageurl,downloadpage=gamepage,linux=linux,windows=windows,mac=mac, claimpage=claimpage, gameid=gameid)
	def process_one(self,bundle,index):
		page = self.session.get(self.bundles[bundle]).text
		listpage = BeautifulSoup(page,'html.parser')
		gamerow = listpage.findChildren('div',attrs={'class':'game_row'})[index]
		imageurl = gamerow.findChild('div',attrs={'class':'game_thumb'}).get('data-background_image')
		gamename = gamerow.findChild('h2',attrs={'class':'game_title'}).getText()
		gamepage = gamerow.findChild('a').get('href')
		linux = False
		mac = False
		windows = False
		if gamerow.findChild('span',attrs={'class':'icon icon-tux'}):
			linux = True
		if gamerow.findChild('span',attrs={'class':'icon icon-apple'}):
			mac = True
		if gamerow.findChild('span',attrs={'class':'icon icon-windows8'}):
			windows = True
		self.cache_game(gamename,imageurl=imageurl,downloadpage=gamepage,linux=linux,windows=windows,mac=mac)

	def process_library(self, maxpages = 0):
		basepage = "https://itch.io/my-purchases"
		cellfinder = re.compile("game_cell.*cover")
		urlfinder = re.compile("url\('[^']*")
		if maxpages == 0:
			#TODO update this once I know what it lookslike
			maxpages = 1
		for i in range(1,maxpages+1):
			page = self.session.get(basepage+'?page=%d' % i).text
			listpage = BeautifulSoup(page,'html.parser')
			for gamecell in listpage.findChildren("div",attrs={"class":cellfinder}):
				thumb = gamecell.findChild("div",attrs={"class":"game_thumb"})
				if thumb:
					imageurl = urlfinder.search(thumb["style"])[0][5:]
				else:
					imageurl = ""
				gamename = gamecell.findChild("a", attrs={"class":"title game_link"}).text
				gamepage = gamecell.findChild("a", attrs={"class":"title game_link"})["href"]
				gameid = gamecell["data-game_id"]
				linux = False
				mac = False
				windows = False
				if gamecell.findChild('span',attrs={'class':'icon icon-tux'}):
					linux = True
				if gamecell.findChild('span',attrs={'class':'icon icon-apple'}):
					mac = True
				if gamecell.findChild('span',attrs={'class':'icon icon-windows8'}):
					windows = True
				self.cache_game(gamename,imageurl=imageurl,downloadpage=gamepage,linux=linux,windows=windows,mac=mac, gameid=gameid)

	def get_image(self, name, imageurl="",cookies=None):
		with open(os.path.join(self.homedir,"cache", "images", "%s.png" % name),"wb") as f:
			for chunk in requests.get(imageurl,cookies=cookies):
				f.write(chunk)
		c = self.sqlconn.cursor()
		with self.sqllock:
			c.execute('UPDATE allgames set cachedimage=True where name=?;', (name,))
			self.sqlconn.commit()

	def cache_game(self,name,imageurl="",downloadpage="", claimpage = "", linux=False, windows=False, mac=False, gameid=""):
		c = self.sqlconn.cursor()
		c.execute('SELECT name FROM allgames where name=?', (name,))
		if not c.fetchone():
			with self.sqllock:
				c.execute('INSERT INTO allgames VALUES (?, ?, False, "", ?, ?, ?, ?, False, False, False, ?, ?);', (name, downloadpage, imageurl, windows, linux, mac,claimpage,gameid,))
				self.sqlconn.commit()


	def nonsafe_download_game(self, name, platform=None, location='', overwrite=False,x64=True):
		ItchioLauncher.thread_safe_download_game(name, platform=platform, location=location, overwrite=overwrite, cookies=self.session.cookies,x64=x64, sqlconn = self.sqlconn, homedir=self.homedir)

	def thread_safe_download_game(name,platform=None,location=None,overwrite=False, cookies=None,x64=True, sqlconn = None, homedir = None, progressor=None, lock=None):
		#proxies = {"https":"127.0.0.1:8080"}
		#verify=False
		proxies = {}
		verify = True
		c = sqlconn.cursor()
		c.execute('SELECT windowsinstall, linuxinstall, macinstall FROM downloadedgames where name=?;', (name,))
		installs = c.fetchone()
		#if installs:
		if False:
			if installs[platform.value] != '':
				if platform == platforms.windows:
					c.execute('UPDATE downloadedgames set windowsinstall=? where name=?;', (location,name,))
				if platform == platforms.linux:
					c.execute('UPDATE downloadedgames set linuxinstall=? where name=?;', (location,name,))
				if platform == platforms.mac:
					c.execute('UPDATE downloadedgames set macinstall=? where name=?;', (location,name,))
			else:
				return False

		c.execute('SELECT url,claimurl,gameid from allgames where name=?', (name,))
		gamepageurl, claimurl, gameid = c.fetchone()
		data = {'csrf_token':urllib.parse.unquote(cookies['itchio_token']),'game_id':gameid,'action':"claim"}
		if claimurl != "":
			response = requests.post(claimurl, data=data, cookies=cookies, proxies=proxies, verify=verify)
			gamepageurl = response.url
			with lock:
				c.execute('UPDATE allgames set url=?,claimurl="" where name=?', (gamepageurl,name,))
				sqlconn.commit()
		
		gamepage = requests.get(gamepageurl, cookies=cookies, proxies=proxies, verify=verify).text
		gamesoup = BeautifulSoup(gamepage, 'html.parser')
		basename = gamesoup.findChild('div',attrs={'class':'header_nav_tabs'}).findChild('a', attrs={'class':'nav_btn return_link'}).get('href')
		icons = ['icon icon-windows8', 'icon icon-tux', 'icon icon-apple']
		mydownloadsections = gamesoup.findChildren('span',attrs={'class':icons[platform.value]})
		#TODO do something more intelligent than pikcing the first one
		if len(mydownloadsections) > 1:
			myspan = mydownloadsections[0]
		else:
			myspan = mydownloadsections[0]
		mysection = myspan.findParent('div',attrs={'class':'upload'})
		filenum = mysection.findChild('a',attrs={'class':'button download_btn'}).get('data-upload_id')
		key = gamepageurl[gamepageurl.rfind('/')+1:]
		data = {'csrf_token': urllib.parse.unquote(cookies['itchio_token'])}
		gameresp = requests.post(basename + "/file/%s?key=%s" % (filenum,key), data=data, cookies=cookies, proxies=proxies, verify=verify)
		thegame = requests.get(gameresp.json()['url'], cookies=cookies, stream=True, proxies=proxies, verify=verify)
		total_length = int(thegame.headers['Content-length'])
		filename = re.findall('filename="(.+)"', thegame.headers['content-disposition'])[0]

		fileloc = os.path.join(homedir, 'cache', 'zips', '%s' % (filename))
		amount_gotten = 0
		chunk_size = 500000
		with open(fileloc,'wb') as f:
			for chunk in thegame.iter_content(chunk_size=chunk_size):
				f.write(chunk)
				if progressor:
					amount_gotten += chunk_size
					with progressor.lock:
						progressor["value"] = int(100 * (amount_gotten / total_length))

		installdir = os.path.join(location, platform.name)
		extension = filename[-3:]

		if extension == "zip":
			with zipfile.ZipFile(fileloc) as zip_ref:
				zip_ref.extractall(installdir)
			os.remove(fileloc)
		elif extension == "exe":
			os.makedirs(installdir, exist_ok=overwrite)
			shutil.move(fileloc, os.path.join(installdir, filename))

		## update stuff
		downloadlocations = ['','','']
		downloadlocations[platform.value] = installdir
		with lock:
			c.execute('INSERT INTO downloadedgames VALUES (?, ?, ?, ?,"","","","",?);', (name, ) + tuple(downloadlocations) + (gameid,))
			if extension == "exe":
				c.execute('UPDATE downloadedgames set windowsexec=? where name=?;', (os.path.join(installdir, filename), name,))

			if platform == platforms.windows:
				c.execute('UPDATE allgames set  windows_downloaded=True where name=?;', (name,))
			if platform == platforms.linux:
				c.execute('UPDATE allgames set  linux_downloaded=True where name=?;', (name,))
			if platform == platforms.mac:
				c.execute('UPDATE allgames set  mac_downloaded=True where name=?;', (name,))
			sqlconn.commit()
			return True

	def process_all_bundles(self, maxpages=0):
		self.load_bundles()
		for bundle in self.bundles:
			self.process_bundle(bundle, maxpages=maxpages)
class DownloaderThread(threading.Thread):
	def __init__(self, downloadQueue, finishedQueue, sqlconn):
		threading.Thread.__init__(self, daemon=True)
		self.downloadQueue = downloadQueue
		self.finishedQueue = finishedQueue
		self.sqlconn = sqlconn
	def run(self):
		while True:
			name, platform, location, overwrite, cookies, x64, homedir, progressor, lock = self.downloadQueue.get(block=True)
			print("Install location is %s" % location)
			ItchioLauncher.thread_safe_download_game(name, platform=platform, location=location, overwrite=overwrite, cookies=cookies, x64 = x64, sqlconn = self.sqlconn, homedir = homedir, progressor = progressor, lock=lock)
		
#mylauncher = ItchioLauncher()
#mylauncher.session.proxies={'https':'127.0.0.1:8080'}
#mylauncher.session.verify=False
#mylauncher.load_saved_session()

#mylauncher.load_bundles()
#thebundle = mylauncher.bundles.__iter__().__next__()
#mylauncher.process_bundle(thebundle)
#mylauncher.download_game("Overland", location="/home/a/testout/Overland4", cookies=mylauncher.session.cookies, platform=platforms.linux)
#mylauncher.process_library()
#mylauncher.process_all_bundles(maxpages=5)
