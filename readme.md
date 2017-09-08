# Scenesetter for Lutron Caseta

## What's this for?

The Lutron Caseta Wireless home lighting control system is awesome in lots of ways: it's rock-solid reliable, quite affordable, and works great with Apple HomeKit. But it has some drawbacks:

* You can't configure the fade time between scenes. With the Lutron app, it's always about 2 seconds, and with HomeKit it's always about 1 second. Wouldn't it be nice to have a smooth, 10-second transition between the "Cooking" scene and the "Dinner" scene?
* You can't program a button on a Pico remote to trigger either a Lutron App scene or a HomeKit scene. Buttons on a Pico can only control (all of) the lights to which that Pico is paired. This also means you basically can't have a "whole house off" button, unless you pair a Pico with every light in the house.

This script solves those problems, providing the following functionality:

* You program it with scenes -- that is, a set of Lutron Caseta devices and their levels, and the fade time to transition into that scene.
* You can configure any button on any Pico to trigger any scenesetter scene.
* The current scene is exposed to HomeKit as a fake lightbulb whose brightness is the current scene number (1% = Scene 1, 2% = Scene 2, etc.). 
  * This means you can set up a HomeKit scene that sets the scene controller device to 1%, and now that scenesetter scene can be triggered by going to that HomeKit scene. You can, of course, include other HomeKit devices in the same HomeKit scene -- so, for example, your "Good Morning" scene can include turning on your HomeKit coffeemaker as well as setting the appropriate scenesetter scene. 
  * This also means you can set up HomeKit automations to be triggered by changes to the scenesetter scene number -- which, in turn, means that, using HomeKit automations, you can trigger any automatable HomeKit action from any button on any Pico.

## Requirements

You will need:

1. A Lutron Caseta Smart Bridge *Pro*. Yes, sorry, you need the Pro ($150ish), not the regular Smart Bridge ($80ish). Why? The main difference between the two is that the Smart Bridge Pro has a telnet interface, while the regular Smart Bridge doesn't. The telnet interface is the only known way of getting notified of Pico button-press events. (*Note*: This means someone could in theory write a version of this that does the slick slow-fade-to-scene part without the Pico-button-press part using the SSH interface on the regular Smart Bridge.)
2. A working installation of [homebridge](https://github.com/nfarina/homebridge), the truly awesome NodeJS-based HomeKit interface.
3. The [homebridge-mqtt](https://github.com/cflurin/homebridge-mqtt) plugin for homebridge
4. A mqtt broker that the homebridge-mqtt plugin is pointed at. I use [Mosquitto](https://mosquitto.org/).
5. The paho-mqtt Python mqtt client module.

Why use the MQTT layer, rather than writing this whole thing in NodeJS as a homebridge accessory? Honestly, it's because I don't know jack about NodeJS, and I think MQTT is nifty and elegant and I already had everything set up. Someone could totally implement this as a pure NodeJS program.

## Getting Started

1. Install all of the required software.
1. Turn on the Telnet interface of your Smart Bridge Pro in the Lutron app by going to Settings > Advanced > Integration and turning "Telnet Support" to On.
1. Edit scenesetter.py to put in:
    * host: the IP or hostname of your Lutron Caseta Smart Bridge Pro. You can find this in the Lutron app by going to Settings > Advanced > Integration > Network Settings.
    * sceneConfigFilename: the path to your scenes.ini (described below; a sample scenes.ini.sample is included)
    * picoConfigFilename: the path to your picos.ini (described below; a sample picos.ini.sample is included)
    * mqttBroker: the IP or hostname of your MQTT broker. If you're running Mosquitto on the same host as Scenesetter, this will be "localhost."
1. Run scenesetter.py. If everything worked properly, a HomeKit device called Scenesetter will appear in your Default Room in the Home app.

## Configuration Files
Scenesetter uses two configuration files, which is where you will do your customization.
### scenes.ini
scenes.ini is where you configure each of your scenes -- "Dinner" or "Gaming" or "Welcome Home" or "Bedtime" or whatever.  Each scene has a number between 1 and 98. (I don't recommend making a Scene 0 or Scene 100, because then they will be triggered if you accidentially flip the fake Scenesetter bulb to "On" or "Off." Scene 99 is hardcoded to make Scenesetter reload the config files.)

Each scene consists of one or more Lutron devices (each with a target brightness) and a fade time. They are expressed like this:
```
[1]
name: Cooking
fadetime: 5
2: 50
3: 50
4: 100
5: 55
6: 100
7: 80
```
That's scene number 1 (triggered when the fake Scenesetter bulb is at 1%), which fades device 2 to 50%, device 3 to 50%, device 4 to 100%, and so on, all in 5 seconds.

How do you know which device number corresponds to which Lutron device in your home? That information is contained in the Integration Report, which you can email to yourself by going in the Lutron app to Settings > Advanced > Integration > Send Integration Report. I find it useful to include the device names in comments in the scene definition, like this:
```
[3]
name: Evening
fadetime: 10
2: 15	; Hallway Ceiling
3: 65	; Great Room Bubble Lamp
4: 25	; Kitchen Ceiling
5: 15	; Dining Table
6: 100	; Mystery Hallway
7: 50	; Great Room Floor Lamp
```
So, for example, if you want an "all off" scene, you'd put in all your devices at zero.

### picos.ini
picos.ini is where you define what button on what Pico triggers what scene. They look like this:
```
[18] ; Dining Room Wall Pico
8=1
9=2
10=3
11=51
```
So that says that on the Pico that is device 18 (which number you will have gotten from the Integration Report), button 8 goes to scene 1, button 9 goes to scene 2, and so on.

How do you know what the button numbers are? You can look it up in the [Lutron Integration Protocol Guide](http://www.lutron.com/TechnicalDocumentLibrary/040249.pdf). For the 5-button Picos that come with Caseta Wireless devices, the button numbers are, in order from top to bottom, 2, 5, 3, 6, 4. For 4-button "scene" Picos (that are especially great to use with Scenesetter), the button numbers are, in order from top to bottom, 8, 9, 10, 11.

# Best Practices
Here's the way I have it set up.

For each Scenesetter scene, there's a corresponding HomeKit scene that just has the Scenesetter fake lightbulb set to the appropriate scene number. That way I can trigger a Scenesetter scene either from HomeKit (including by telling Siri "Go to the Dinner scene") or by hitting a button on a Pico. That also means you can use HomeKit automations to trigger Scenesetter scenes -- for example, I have a motion sensor near the front door that triggers the "Welcome Home" scene under certain conditions.

I have a bedside Pico that's paired to my bedside lamp, but I've set up the Off button on that Pico to also trigger the "Whole House Off" Scenesetter scene, so I can turn everything off from bed without getting out my iPad or talking to Siri in the bedroom, because that's creepy.

# Thank-yous

This would not have been possible without implementation facts gleaned from other software that talks to Lutron Caseta Wireless devices:
* [Casetify](https://github.com/jhanssen/casetify)
* [MiCasaVerde Caseta Connect](http://forum.micasaverde.com/index.php?topic=35577.0)

And, of course, big thanks to Lutron for publishing its [Lutron Integration Protocol Guide](http://www.lutron.com/TechnicalDocumentLibrary/040249.pdf) to allow third-party integration via an open protocol.