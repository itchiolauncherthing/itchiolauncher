#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from itchiolauncher import *
import queue
import os
import sys
import platform
from subprocess import Popen, PIPE
import time
import sqlite3
import re

class gui(tk.Frame):
	def __init__(self, master=None):
		super().__init__(master)
		self.master = master
		self.launcher = ItchioLauncher()
		if not self.launcher.load_saved_session():
			loginframe = LoginFrame(self)
			loginframe.pack()
		else:
			self.setup()
		

		
	def setup(self):
		self.installpath = os.getcwd()
		self.settingsconn = sqlite3.connect(os.path.join(self.installpath, "settings.sql"))
		settingcursor = self.settingsconn.cursor()
		settingcursor.execute('SELECT value from defaultsettings where setting = "defaultGameLocation"')
		gl = settingcursor.fetchone()
		if gl:
			self.defaultGameLocation = gl[0]
		else:
			self.defaultGameLocation = tk.filedialog.askdirectory(title="Where would you like the default install directory to be?")
			with self.launcher.sqllock:
				settingcursor.execute('INSERT INTO defaultsettings VALUES ("defaultGameLocation", ?);', (self.defaultGameLocation,))
				self.settingsconn.commit()
		if platform.system() == "Windows":
			self.platform = platforms.windows
		elif platform.system() == "Linux":
			self.platform = platforms.linux
		## TODO: figure out how macs report
		self.filterOS = tk.BooleanVar()
		self.filterOS.set(True)
		self.launcher.process_library()
		self.widgetSize = 0
		self.makeGameList()
		self.getDownloaded()

		self.downloadQueue = queue.Queue()
		self.finishedQueue = queue.Queue()
		self.downloadThread = DownloaderThread(self.downloadQueue, self.finishedQueue, self.launcher.sqlconn)
		self.downloadThread.start()
		self.imageThread = ImageThread(self.launcher.sqlconn, self.launcher.sqllock)
		self.imageThread.start()


		self.pack()
		self.lib = self.makelib()
		self.navFrame = ""
		self.navFrame = self.makenav()
		self.navFrame.pack(side="left")

		self.libCanvas = self.makelib()
		self.gameFrame = self.libCanvas.gameFrame
		self.libCanvas.pack(side="right",fill="both",expand=True)
		self.refreshAllGamesList()
	def populateStyle(self):
		self.style = ttk.Style()
		self.style.configure("OneGame.TButton", foreground="#B0B0B0", background="#202020")

	def processBundles(self):
		self.launcher.process_all_bundles()
		self.makeGameList()

	def makenav(self):
		navFrame = tk.Frame(self.master)
		navFrame.allgames = ttk.Button(navFrame, text="All Games", command=self.showAllGames)
		navFrame.downloadedgames = ttk.Button(navFrame, text="Downloaded Games", command=self.showDownloadedGames)
		navFrame.played = ttk.Button(navFrame, text="Played Games")
		navFrame.unplayed = ttk.Button(navFrame, text="Unplayed Games")
		navFrame.process_bundles = ttk.Button(navFrame, text="Process Bundles", command=self.processBundles)
		maxwidth= navFrame.downloadedgames.winfo_width()

		navFrame.clearImageCache = ttk.Button(navFrame, text="Clear image cache", command=self.clearImageCache)

		for thisbutton in navFrame.winfo_children():
			thisbutton.pack(side="top", fill="x")
		return navFrame

	def clearImageCache(self):
		c = self.launcher.sqlconn.cursor()
		with self.launcher.sqllock:
			c.execute('UPDATE allgames set cachedimage=False, localimage="";')
			self.launcher.sqlconn.commit()
		self.showGames()

	def showAllGames(self):
		self.gameFrame.page = 0
		self.gamelist = self.allgameslist
		self.showGames()

	def showDownloadedGames(self):
		self.gameFrame.page = 0
		self.getDownloaded()
		self.gamelist = self.downloadedGamesList.copy()
		self.showGames()

	def showGames(self):
		for widget in self.gameFrame.winfo_children(): widget.destroy()
		minGame = self.gameFrame.page * self.gameFrame.gamesPerPage
		maxGame = minGame + self.gameFrame.gamesPerPage
		gamesToShow = self.gamelist[minGame:maxGame]
		self.gameWidgets = self.makeWidgets(games=gamesToShow,container=self.gameFrame)
		self.gameFrame.maxpages = len(self.gamelist) // self.gameFrame.gamesPerPage
		self.gameFrame.pageLabel.configure(text = "page %d of %d" % (self.gameFrame.page + 1, self.gameFrame.maxpages + 1))
		self.drawWidgets(gameWidgets=self.gameWidgets,container=self.gameFrame)
		
	def refreshAllGamesList(self):
		self.makeGameList()
		self.showAllGames()


	def makeGameList(self):
		c = self.launcher.sqlconn.cursor()
		#c.execute("SELECT name from allgames;")
		#self.allgameslist = [*map(lambda x: x[0], c.fetchall())]
		if self.filterOS.get():
			c.execute("SELECT gameid,name from allgames where %s=True;" % (self.platform.name))
		else:
			c.execute("SELECT gameid,name from allgames;")
		self.allgameslist = c.fetchall()

	def makeWidgets(self,games=None,container=None):
		gamewidgets = []
		for thisgame in games:
#			gamewidgets.append(self.makeGameWidget(game=thisgame, parentframe=container))
			gamewidgets.append(GameWidget(parentframe=container, game=thisgame, fullGui=self))
		return gamewidgets

	def drawWidgets(self,gameWidgets=None,container=None):
		gameiter = gameWidgets.__iter__()
		self.libCanvas.canvas.yview_moveto(0)
		self.update()
		if self.widgetSize == 0:
			self.widgetSize = gameWidgets[0].winfo_reqwidth()
		container.maxColumns = (self.libCanvas.winfo_width() // self.widgetSize)
		for row in range(-(-len(gameWidgets) // container.maxColumns)):
			for column in range(container.maxColumns):
				try:
					gameiter.__next__().grid(row=row, column = column)
					pass
				except StopIteration:
					pass

	def makelib(self):
		container = tk.Frame(self.master)
		canvas = tk.Canvas(container)
		scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
		scrollable_frame = ttk.Frame(canvas)
		
		scrollable_frame.bind( "<Configure>", lambda e: canvas.configure( scrollregion=canvas.bbox("all")))

		canvas.bind("<Configure>", lambda e: self.pageRefresh(), add="+")
		
		canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
		canvas.configure(yscrollcommand=scrollbar.set)

		pagerFrame = tk.Frame(container)
		backButton = ttk.Button(pagerFrame,text="Back",command=self.pageBack, width=12)
		nextButton = ttk.Button(pagerFrame,text = "Next", command=self.pageNext, width=12)
		scrollable_frame.pageLabel = ttk.Label(pagerFrame,text="page 1 of 1", width=12 )

		searchField = ttk.Entry(pagerFrame, width=15)
		filterOSCheckbox = tk.Checkbutton(pagerFrame, text="Filter to current OS", onvalue = True, offvalue = False, var = self.filterOS, command=self.refreshAllGamesList)


		pagerFrame.pack(side="top", fill="x")
		canvas.pack(side="left", fill="both", expand=True)
		scrollbar.pack(side="right", fill="y")

		backButton.pack(side="left")
		scrollable_frame.pageLabel.pack(side="left")
		nextButton.pack(side="left")
		searchField.pack(side="right")
		filterOSCheckbox.pack(side="right")
		#backButton.grid(row=0,column=0)
		#container.gameFrame.pageLabel.gric(row=0,column=1,
		#nextButton.grid(row=0,column=2)

		container.canvas = canvas
		container.gameFrame = scrollable_frame
		container.scrollbar = scrollbar
		container.gameFrame.page = 0
		container.gameFrame.gamesPerPage = 50
		self.master.bind_all("<MouseWheel>", self.__on_mousewheel)
		if self.platform == platforms.linux:
			self.master.bind_all("<Button-5>", self.__on_mousewheel, add="+")
			self.master.bind_all("<Button-4>", self.__on_mousewheel, add="+")
		elif self.platform == platforms.windows:
			self.master.bind_all("<MouseWheel>", self.__on_mousewheel)

		searchField.bind("<Return>", self.searchGames)
		#filterOSCheckbox.bind("<Button-1>", self.refreshAllGamesList)

		return container


	def searchGames(self, event):
		buttonframe = event.widget.master
		frame = buttonframe.master
		self.gamelist = []
		for  game in self.allgameslist:
			if event.widget.get().upper() in game[1].upper():
				self.gamelist.append(game)
		self.showGames()

	def getMatches(self, game):
		if self.r.match(game[1]):
			return game

	def pageNext(self):
		if self.gameFrame.page < self.gameFrame.maxpages:
			self.gameFrame.page += 1
			self.showGames()
	def pageBack(self):
		if self.gameFrame.page > 0:
			self.gameFrame.page -= 1
			self.showGames()

	def pageRefresh(self):
		if self.widgetSize != 0:
			if ((self.libCanvas.winfo_width() // self.widgetSize) != self.gameFrame.maxColumns):
				for widget in self.gameFrame.winfo_children(): widget.forget()
				self.drawWidgets(gameWidgets=self.gameWidgets,container=self.gameFrame)
			

	def __on_mousewheel(self,event):
		self.libCanvas.canvas.yview_scroll(int(-1*(event.delta/120)),"units")
		#self.libCanvas.canvas.yview_scroll(10 * event.delta,"units")

	def getDownloadOptions(self, game):
		c = self.launcher.sqlconn.cursor()
		c.execute("SELECT windows,linux,mac from allgames where name=?;", (game,))
		response = c.fetchone()
		out = []
		if response[0]:
			out.append(platforms.windows)
		if response[1]:
			out.append(platforms.linux)
		if response[2]:
			out.append(platforms.mac)

	def getDownloaded(self):
		c = self.launcher.sqlconn.cursor()
		c.execute("SELECT gameid, name from downloadedgames;")
		#self.downloadedGamesList = [*map(lambda x: x[0], c.fetchall())]
		self.downloadedGamesList = c.fetchall()
		

	def playGame(self, event):
		buttonframe = event.widget.master
		frame = buttonframe.master
		c = self.launcher.sqlconn.cursor()
		if self.platform == platforms.linux:			
			installname = "linuxinstall"
			execname = 'linuxexec'
		elif self.platform == platforms.windows:
			installname = "windowsinstall"
			execname = 'windowsexec'
			
		c.execute("SELECT %s,%s from downloadedgames where name=?;" % (execname,installname), (frame.name,))
		executable, installdir = c.fetchone()
		if not executable:
			executable = tk.filedialog.askopenfilename(initialdir = installdir, title="Choose which executable to run")
			with self.launcher.sqllock:
				c.execute('UPDATE downloadedgames set %s=? where name=?' % (execname), (executable,frame.name))
				self.launcher.sqlconn.commit()
			if not executable:
				return

		kwargs = {}
		if self.platform == platforms.linux:
			kwargs.update(start_new_session=True)
			os.chmod(executable, 0o700)
			oldwd = os.getcwd()
			os.chdir(os.path.dirname(executable))
			p = Popen([executable], stdin=PIPE, stdout=PIPE, stderr=PIPE, **kwargs)
			os.chdir(oldwd)
		if self.platform == platforms.windows:
			CREATE_NEW_PROCESS_GROUP = 0x00000200  # note: could get it from subprocess
			DETACHED_PROCESS = 0x00000008          # 0x8 | 0x200 == 0x208
			kwargs.update(creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP) 
			oldwd = os.getcwd()
			os.chdir(os.path.dirname(executable))
			os.startfile(executable) 
			os.chdir(oldwd)
		
			

	def downloadGame(self, event):
		buttonframe = event.widget.master
		frame = buttonframe.master
		frame.progress = ttk.Progressbar(frame.imageLabel, orient="horizontal",length=self.widgetSize, mode="determinate", maximum=100,value=0)
		frame.progress.lock = threading.RLock()
		frame.progress.place(relx=0, rely=1, anchor="sw")
		downloadLocation = os.path.join(self.defaultGameLocation, re.sub("[^0-9a-zA-Z]+","_",frame.name))
		#name, platform, location, overwrite, cookies, x64, homedir, progressor
		self.downloadQueue.put((frame.name, self.platform, downloadLocation, True, self.launcher.session.cookies, True, self.installpath, frame.progress, self.launcher.sqllock))

		

	def clearExec(self, event):
		print("wrong one")
		buttonframe = event.widget.master
		frame = buttonframe.master
		c = self.launcher.sqlconn.cursor()
		if self.platform == platforms.linux:			
			installname = "linuxinstall"
			execname = 'linuxexec'
			executable, installdir = c.fetchone()
		elif self.platform == platforms.windows:
			installname = "windowsinstall"
			execname = 'windowsexec'
		with self.launcher.sqllock:
			c.execute('UPDATE downloadedgames set %s="" where name=?;' % (execname), (frame.name,))
			self.launcher.sqlconn.commit()


#	def makeGameWidget(self, game=None, parentframe=None):
#		frame = tk.Frame(parentframe)
#		frame.name = game[1]
#		frame.title = ttk.Label(frame, text=frame.name,wraplength=315)
#		frame.imageLabel = ttk.Label(frame)
#		frame.imageLabel.image = tk.PhotoImage(width=315, height=250)
#		frame.imageLabel.configure(image=frame.imageLabel.image)
#		frame.buttonframe = tk.Frame(frame)
#		frame.downloadplay = ttk.Button(frame.buttonframe, style="OneGame.TButton")
#		frame.clearExec = ttk.Button(frame.buttonframe, style="OneGame.TButton")
#
#		frame.downloadplay.downloaded = (game[1] in map(lambda x: x[1],self.downloadedGamesList))
#		if frame.downloadplay.downloaded == False:
#			frame.downloadplay["text"] = "Download"
#			frame.downloadplay.bind("<Button-1>", self.downloadGame, add='')
#		else:
#			frame.downloadplay["text"] = "Play"
#			frame.downloadplay.bind("<Button-1>", self.playGame, add='')
#			frame.clearExec.bind("<Button-1>", self.clearExec, add='')
#			frame.clearExec["text"] = "Clear run executable"
#			
#	#	frame.popup_menu = tk.Menu(frame, tearoff=0)
#		
#		
#		frame.title.pack(side="top")
#		frame.imageLabel.pack(side="top")
#		frame.buttonframe.pack(side="bottom")
#		frame.downloadplay.pack(side="left")
#		frame.clearExec.pack(side="right")
#		c = self.launcher.sqlconn.cursor()
#		c.execute("SELECT localimage from allgames where name=?;", (game[1],))
#		imagepath = c.fetchone()
#		if imagepath:
#			try:
#				frame.imageLabel.image.configure(file=imagepath[0])
#				pass
#			except Exception as e:
#				pass
#		return frame
		

class GameWidget(tk.Frame):
	def __init__(self, parentframe=None, game=None, sqlconn=None, downloadedGamesList=None, sqllock=None, fullGui=None):
		super().__init__(parentframe)
		self.fullGui = fullGui
		self.name = game[1]
		self.title = ttk.Label(self, text=self.name,wraplength=315)
		self.imageLabel = ttk.Label(self)
		self.imageLabel.image = tk.PhotoImage(width=315, height=250)
		self.imageLabel.configure(image=self.imageLabel.image)
		self.buttonframe = tk.Frame(self)
		self.downloadplay = ttk.Button(self.buttonframe, style="OneGame.TButton")

		self.downloaded = (game[1] in map(lambda x: x[1],self.fullGui.downloadedGamesList))
		if self.downloaded == False:
			self.downloadplay["text"] = "Download"
			self.downloadplay["command"] = self.downloadGame
		else:
			self.downloadplay["text"] = "Play"
			self.downloadplay["command"] = self.playGame
			
		self.popup_menu = tk.Menu(self, tearoff=0)
		self.popup_menu.add_command(label="Clear Exec", command=self.clearExecs)
		self.imageLabel.bind("<Button-3>", self.popup)
		#self.bind("<Button-2>", self.popup)
		
		
		self.title.pack(side="top")
		self.imageLabel.pack(side="top")
		self.buttonframe.pack(side="bottom")
		self.downloadplay.pack(side="left")
		c = self.fullGui.launcher.sqlconn.cursor()
		c.execute("SELECT localimage from allgames where name=?;", (game[1],))
		imagepath = c.fetchone()
		if imagepath:
			try:
				self.imageLabel.image.configure(file=imagepath[0])
				pass
			except Exception as e:
				pass

	def popup(self, event):
		try:
			self.popup_menu.tk_popup(event.x_root, event.y_root, 0)
		finally:
			self.popup_menu.grab_release()

	def playGame(self):
		c = self.fullGui.launcher.sqlconn.cursor()
		if self.fullGui.platform == platforms.linux:			
			installname = "linuxinstall"
			execname = 'linuxexec'
		elif self.fullGui.platform == platforms.windows:
			installname = "windowsinstall"
			execname = 'windowsexec'
			
		c.execute("SELECT %s,%s from downloadedgames where name=?;" % (execname,installname), (self.name,))
		executable, installdir = c.fetchone()
		if not executable:
			executable = tk.filedialog.askopenfilename(initialdir = installdir, title="Choose which executable to run")
			with self.fullGui.launcher.sqllock:
				c.execute('UPDATE downloadedgames set %s=? where name=?' % (execname), (executable,self.name))
				self.fullGui.launcher.sqlconn.commit()
			if not executable:
				return

		kwargs = {}
		if self.fullGui.platform == platforms.linux:
			kwargs.update(start_new_session=True)
			os.chmod(executable, 0o700)
			oldwd = os.getcwd()
			os.chdir(os.path.dirname(executable))
			p = Popen([executable], stdin=PIPE, stdout=PIPE, stderr=PIPE, **kwargs)
			os.chdir(oldwd)
		if self.fullGui.platform == platforms.windows:
			CREATE_NEW_PROCESS_GROUP = 0x00000200  # note: could get it from subprocess
			DETACHED_PROCESS = 0x00000008          # 0x8 | 0x200 == 0x208
			kwargs.update(creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP) 
			oldwd = os.getcwd()
			os.chdir(os.path.dirname(executable))
			os.startfile(executable) 
			os.chdir(oldwd)


	def downloadGame(self):
		self.progress = ttk.Progressbar(self.imageLabel, orient="horizontal",length=self.fullGui.widgetSize, mode="determinate", maximum=100,value=0)
		self.progress.lock = threading.RLock()
		self.progress.place(relx=0, rely=1, anchor="sw")
		downloadLocation = os.path.join(self.fullGui.defaultGameLocation, re.sub("[^0-9a-zA-Z]+","_",self.name))
		#name, platform, location, overwrite, cookies, x64, homedir, progressor
		self.fullGui.downloadQueue.put((self.name, self.fullGui.platform, downloadLocation, True, self.fullGui.launcher.session.cookies, True, self.fullGui.installpath, self.progress, self.fullGui.launcher.sqllock))



	def clearExecs(self):
		c = self.fullGui.launcher.sqlconn.cursor()
		if self.fullGui.platform == platforms.linux:			
			execname = 'linuxexec'
		elif self.fullGui.platform == platforms.windows:
			execname = 'windowsexec'
		with self.fullGui.launcher.sqllock:
			c.execute('UPDATE downloadedgames set %s="" where name=?;' % (execname), (self.name,))
			self.fullGui.launcher.sqlconn.commit()


class ImageThread(threading.Thread):
	def __init__(self, sqlconn, lock):
		threading.Thread.__init__(self, daemon=True)
		self.sqlconn = sqlconn
		self.lock = lock
	def run(self):
		self.installdir = os.getcwd()
		while True:
			self.check_for_images()
			time.sleep(30)
	def check_for_images(self):
		sqlconn = self.sqlconn
		c = sqlconn.cursor()
		c.execute('SELECT imageurl,name from allgames where cachedimage=False;')
		hits = c.fetchall()
		if hits:
			throttle = 1000
			count=0
			for game in hits:
				if game[0]:
					resp = requests.get(game[0])

					if game[1] != "":
						filename = re.sub("[^0-9a-zA-Z]+", "_", game[1])
						localpath = os.path.join(self.installdir,'cache', 'images', '%s.png' % filename)
						with open(localpath,'wb') as f:
							for chunk in resp:
								f.write(chunk)
					try:
							with self.lock:
								sqlconn.execute('UPDATE allgames set cachedimage=True,  localimage=? where name=?;', (localpath,game[1],))
								sqlconn.commit()
							
					except sqlite3.OperationalError:
						print("Didn't work for %s. Skipping for now" % game[1])
					count +=1
					if count > throttle:
						time.sleep(3)
						count = 0


class LoginFrame(tk.Frame):
	def __init__(self, parentframe):
		super().__init__(parentframe.master)
		self.parentframe = parentframe
		self.label_username = ttk.Label(self, text="Username")
		self.label_password = ttk.Label(self, text="Password")

		self.entry_username = ttk.Entry(self)
		self.entry_password = ttk.Entry(self, show="*")

		self.label_username.grid(row=0, sticky=tk.E)
		self.label_password.grid(row=1, sticky=tk.E)
		self.entry_username.grid(row=0, column=1)
		self.entry_password.grid(row=1, column=1)

		self.savesession = tk.BooleanVar()
		self.checkbox = tk.Checkbutton(self, text="Keep me logged in. Your password is not saved", onvalue = True, offvalue = False, var = self.savesession, command=self.refreshAllGamesList)
		self.checkbox.grid(columnspan=2)

		self.logbtn = ttk.Button(self, text="Login", command=self._login_btn_clicked)
		self.logbtn.grid(columnspan=2)



	def _login_btn_clicked(self):
		# print("Clicked")
		username = self.entry_username.get()
		password = self.entry_password.get()
		self.parentframe.launcher.login(username, password, save=self.savesession)
		
		self.forget()
		self.parentframe.setup()
		self.destroy()


root = tk.Tk()
root.geometry("800x500")
app = gui(master=root)
app.mainloop()
