import telnetlib
import sys
import ConfigParser
import threading
import Queue
import json
import logging
from time import sleep
import paho.mqtt.client as mqtt

host = 'lutron-01f576a.local'
sceneConfigFilename = '/etc/scenecontroller/scenes.ini'
picoConfigFilename = '/etc/scenecontroller/picos.ini'
mqttBroker = 'localhost'

DEBUG_MODE = True

user = 'lutron'
password = 'integration'

class LutronConnection:
	def __init__(self, host, user, password, outgoingSceneQueue):
		self.outgoingSceneQueue = outgoingSceneQueue
		self.host = host
		self.user = user
		self.password = password
		self.tn = telnetlib.Telnet()
		self.tn.set_debuglevel(0)
		self.start()
	
	def start(self):
		self.tn.open(self.host, 23, 60)
		self.tn.read_until('login: ')
		self.tn.write(self.user + '\n')
		self.tn.read_until('password: ')
		self.tn.write(self.password + '\n')
		self.tn.read_until("GNET> ")
		
	def restart(self):
		logger.debug('Restarting connection.')
		self.tn.close()
		self.start()
		logger.debug('Restarted connection.')
	
	def setLevel(self, deviceID, level, fadeTime=1.00):
		self.tn.write('#OUTPUT,%s,1,%s,%s\n' % (deviceID, level, fadeTime))

	def pollForInput(self):
		lutronFeedbackRaw = self.tn.expect(['\n'], 10)[2]
		if lutronFeedbackRaw != '':
			logger.debug('Got telnet input: %s' % lutronFeedbackRaw.strip())
			lutronFeedbackRaw = lutronFeedbackRaw.replace(' ','\n')
			try:
					lutronFeedbackPieces = lutronFeedbackRaw.split('\n')
			except ValueError:
					lutronFeedbackPieces = [lutronFeedbackRaw]
			for piece in lutronFeedbackPieces:
					piece = piece.strip()
					if piece and piece != 'GNET>':
							if piece.startswith('~DEVICE'):
									attributes = piece.split(',')[1:]
									# I only care about button events, not scenes or whatever
									if len(attributes) == 3:
											# I only care about button presses, not releases
											if attributes[2] == '3':
													logger.debug('device %s button %s was pressed' % (attributes[0], attributes[1]))
													logger.debug('Trying to acquire the registries lock in PollForInput.')
													registriesLock.acquire()
													global picoRegistry
													global sceneRegistry
													targetScene = None
													try:
														targetScene = sceneRegistry[picoRegistry[attributes[0]].buttons[attributes[1]]]
													except KeyError:
														logger.debug('No scene for button %s on device %s.' % (attributes[1], attributes[0]))
													registriesLock.release()
													logger.debug('Released the registries lock in PollForInput.')
													if targetScene:
														targetScene.go(self)
														logger.debug('Going to scene %s' % targetScene)
							if piece.startswith('shutting down the integration terminal'):
								self.restart()

class Command:
	def __init__(self, deviceID, level, fadeTime=None):
		self.deviceID = deviceID
		self.level = level
		self.fadeTime = fadeTime
	
	def execute(self, connection):
		connection.setLevel(self.deviceID, self.level, self.fadeTime)
		
class Scene:
	def __init__(self, number, name=None, defaultFadeTime=1.00, commands=[]):
		self.number = number
		self.name = name
		self.commands = commands
		self.defaultFadeTime = defaultFadeTime
		registriesLock.acquire()
		global sceneRegistry
		sceneRegistry[self.number] = self
		registriesLock.release()
	
	def go(self, connection):
		outgoingSceneCondition.acquire()
		connection.outgoingSceneQueue.put(self.number)
		outgoingSceneCondition.notifyAll()
		outgoingSceneCondition.release()
		if self.number == '99':
			global sceneRegistry
			global picoRegistry
			loadSceneConfig(sceneConfigFilename)
			loadPicoConfig(picoConfigFilename)
		else:
			for command in self.commands:
				if not command.fadeTime:
					command.fadeTime = self.defaultFadeTime
				command.execute(connection)
		
	
class Pico:
	def __init__(self, deviceID, buttons={}):
		self.deviceID = deviceID
		# Buttons is a dict mapping button number to scene
		self.buttons = buttons
		registriesLock.acquire()
		global picoRegistry
		picoRegistry[self.deviceID] = self
		registriesLock.release()

def loadSceneConfig(filename):
	logger.info('Loading scene configuration from %s.' % filename)
	registriesLock.acquire()
	global sceneRegistry
	sceneRegistry = {}
	registriesLock.release()
	config = ConfigParser.RawConfigParser()
	config.read(filename)
	scenes = {}
	# Hardcode the "reload configs" scene
	scenes['99'] = Scene('99', 'Reload', None)
	for section in config.sections():
		scenes[section] = Scene(section, config.get(section, 'name'), config.get(section, 'fadetime'))
		commandValues = []
		for item in config.items(section):
			if item[0].isdigit():
				commandValues += [Command(item[0], item[1])]
		scenes[section].commands = commandValues

def loadPicoConfig(filename):
	logger.info('Loading Pico configuration from %s.' % filename)
	registriesLock.acquire()
	global picoRegistry
	picoRegistry = {}
	registriesLock.release()
	config = ConfigParser.RawConfigParser()
        config.read(filename)
	for section in config.sections():
		buttons = {}
		for item in config.items(section):
			if item[0].isdigit():
				buttons[item[0]] = item[1]
		p = Pico(section, buttons)

class LutronIOThread(threading.Thread):
	def __init__(self, host, user, password, incomingSceneQueue, outgoingSceneQueue):
		threading.Thread.__init__(self)
		self.host = host
		self.user = user
		self.password = password
		self.incomingSceneQueue = incomingSceneQueue
		self.outgoingSceneQueue = outgoingSceneQueue
	def run(self):
		lc = LutronConnection(self.host, self.user, self.password, outgoingSceneQueue)
		sender = LutronSenderThread(lc, incomingSceneQueue)
		sender.daemon = True
		sender.start()
		while True:
			lc.pollForInput()

class LutronSenderThread(threading.Thread):
	def __init__(self, lc, incomingSceneQueue):
		threading.Thread.__init__(self)
		self.lc = lc
		self.incomingSceneQueue = incomingSceneQueue
	def run(self):
		while True:
			incomingSceneCondition.acquire()
			while self.incomingSceneQueue.empty():
				incomingSceneCondition.wait()
			self.incomingSceneQueue.get().go(self.lc)
			incomingSceneCondition.release()

def on_connect(client, userdata, flags, rc):
	client.subscribe('/homebridge/#')
	sceneControllerJSON = json.dumps({"name": "scenesetter", "service_name": "Scenesetter", "service": "Lightbulb", "Brightness": "default"})
	client.publish('homebridge/to/add', sceneControllerJSON)
			
def on_message(client, userdata, msg):
	incomingSceneQueue = userdata['incomingSceneQueue']
	if msg.topic == 'homebridge/from/set':
		setPayload = json.loads(msg.payload)
		if setPayload['name'] == 'scenesetter' and setPayload['characteristic'] == 'Brightness':
			sceneToQueue = str(setPayload['value'])
			logger.debug('Trying to acquire the registries lock in MQTT message callback.')
			registriesLock.acquire()
			global sceneRegistry
			try:
				toScene = sceneRegistry[sceneToQueue]
				incomingSceneCondition.acquire()
				incomingSceneQueue.put(toScene)
				incomingSceneCondition.notifyAll()
			except KeyError:
				logger.debug('No such scene as %s' % sceneToQueue)
			finally:
				incomingSceneCondition.release()
				registriesLock.release()	
			logger.debug('Released the registries lock in MQTT message callback.')			

				
def publishScenesFromQueue(mqttClient, q):
	outgoingSceneCondition.acquire()
	while q.empty():
		outgoingSceneCondition.wait()
	sceneUpdateJSON = json.dumps({"name":"scenesetter","service_name":"Scenesetter","characteristic":"Brightness","value":q.get()})
	mqttClient.publish('homebridge/to/set', sceneUpdateJSON)
	outgoingSceneCondition.release()
		
if __name__ == '__main__':
	global sceneRegistry
	global picoRegistry
	global registriesLock
	registriesLock = threading.Lock()
	logger = logging.getLogger('scenesetter')
	logger.setLevel(logging.DEBUG)
	ch = logging.StreamHandler()
	fh = logging.FileHandler('/var/log/scenecontroller.log')
	fh.setLevel(logging.DEBUG)
	ch.setLevel(logging.DEBUG)
	formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
	ch.setFormatter(formatter)
	fh.setFormatter(formatter)
	# logger.addHandler(ch)
	logger.addHandler(fh)
	loadSceneConfig(sceneConfigFilename)
	loadPicoConfig(picoConfigFilename)
	incomingSceneQueue = Queue.Queue()
	outgoingSceneQueue = Queue.Queue()
	incomingSceneCondition = threading.Condition()
	outgoingSceneCondition = threading.Condition()
	lutronThread = LutronIOThread(host, user, password, incomingSceneQueue, outgoingSceneQueue)
	lutronThread.daemon = True
	mqttUserdata = {'incomingSceneQueue': incomingSceneQueue, 'sceneRegistry': sceneRegistry}
	mqttClient = mqtt.Client(userdata=mqttUserdata)
	mqttClient.on_connect = on_connect
	mqttClient.on_message = on_message
	mqttClient.connect(mqttBroker)
	lutronThread.start()
	mqttClient.loop_start()
	while True:
		publishScenesFromQueue(mqttClient, outgoingSceneQueue)
