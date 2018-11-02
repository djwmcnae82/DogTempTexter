from twilio.rest import Client
from twilio.twiml.messaging_response import Body, Message, Redirect, MessagingResponse
from datetime import datetime
import socket
from math import fsum
from time import sleep

import MyPyDHT
import os
import threading

from flask import Flask
from flask import send_file 
from flask import render_template
from flask import redirect, url_for
from flask import jsonify
from flask import request

class DogTempSensor(object):
	def __init__(self):
		self.dht22_bcm = 17

		# Set this to true in order to text every minute an alert!
		self.alert = False
		self.limit = None

		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		s.connect(('8.8.8.8', 1))  # connect() for UDP doesn't send packets
		local_ip_address = s.getsockname()[0]

		# Buffers and sensor data class variables
		self.temp_buff =  [0 for i in range(0,4)]
		self.humid_buff =  [0 for i in range(0,4)]
		self.clean_sensors = (0,0,0)
		current_time = datetime.strftime(datetime.now(),"%I:%M:%S %p")

		# Send send message on bootup with ip address, useful for sshing and pushing code
		self.SendTextMessage('Bootup @ IP '+ local_ip_address+  ' at:' + current_time )

		# Store resin environment variable as a class variable
		self.mins_per_text = os.environ["TEXT_FREQ"] 

		schedule.every(30).seconds.do(self.SendInfoMessage)

		t1 = threading.Thread(target=self.t_flask_server, name="flask_server")
		t1.setDaemon(True)
		t1.start()
		print("Started web server!")

		t2 = threading.Thread(target=self.t_read_th_sensor, name="temp and humidity sensor")
		t2.setDaemon(True)
		t2.start()
		print("Started Temp and Humidity Reader Thread")

		sleep(5)
		t3 = threading.Thread(target=self.t_text_message_router, name="text router")
		t3.setDaemon(True)
		t3.start()
		print("Started Text Message Router Thread")

	# THREAD: Run Web Server to receive text events webhooks
	def t_flask_server(self):
		while True:
			try:
				app = Flask(__name__)
				app.add_url_rule('/',view_func=self.ResponseTextServer)
				app.add_url_rule('/update',view_func=self.UpdateSensorLimit)
				app.add_url_rule('/in-bound',view_func=self.InBoundMessageResponse, methods=['GET', 'POST'])
				app.run(host='0.0.0.0', port=80)
				
			except Exception as e:
				sleep(30)

	# THREAD: Read temp and humidity sensor
	def t_read_th_sensor(self):
		while True:
			self.clean_sensors = self.ReadDHT22()
			if self.limit != None:
				if self.clean_sensors[1] >= self.limit:
					self.alert = True
				else:
					self.alert = False
			print("Clean Sensors Readings: %s,%s,%s" % self.clean_sensors)
			sleep(2)

	def SendInfoMessage(self):
		# while True:
		current_time = datetime.strftime(datetime.now(),"%I:%M:%S %p")
		print(current_time)

		if self.limit == None:
			msg_text = "Still Monitoring! " + current_time
		else:
			msg_text = "Alert Status: " + str(self.alert) + \
			"\nCurrent Limit " + str(self.limit)

		msg_text = msg_text + "\nTemp (H,Tf,Tc): " + str(self.clean_sensors) + \
		"\n" +  "Threads: " + str(threading.active_count() )
		
		print(msg_text)

		self.SendTextMessage(msg_text)

		# if self.alert == True:
		# 	sleep(60)
		# else:
		# 	sleep(60 * int(self.mins_per_text) )

		# return schedule.CancelJob

	def t_text_message_router(self):
		while True:
		    schedule.run_pending()
		    time.sleep(1)


	# DHT22: Return clean sensor data (humidity, tempf, tempc )
	def ReadDHT22(self):
		# humidity = -1
		# temp = -1
		retry = 0
		max_retry = 10
		while retry < max_retry:
			try:
				humidity, temp = MyPyDHT.sensor_read(MyPyDHT.Sensor.DHT22, self.dht22_bcm)
				# print("DHT22 Alive: Received:\t Temp: %f\tHumidity:%f" %(temp,humidity) )
				
				temp = (temp * 1.8) + 32
				self.temp_buff.pop(0)
				self.humid_buff.pop(0)
				self.temp_buff.append(round(temp, 2) ) 
				self.humid_buff.append(round(humidity, 2) )
				average_h = round(fsum(self.humid_buff) / len(self.humid_buff), 2)
				average_t = round(fsum(self.temp_buff) / len(self.temp_buff), 2)
				return (average_h, average_t, round((average_t-32)/1.8,2) ) 

			except Exception as e:
				print(e)
				retry = retry + 1
				sleep(0.5)

		return (-1,-1,-1)

	# TWILIO: Send a text message using twilio
	def SendTextMessage(self,mymessage):
		# Your Account Sid and Auth Token from twilio.com/console
		account_sid = os.environ['TWILIO_ACCT_SID']
		auth_token = os.environ['TWILIO_AUTH_TOKEN']
		client = Client(account_sid, auth_token)
		message = client.messages.create(
		                              from_=os.environ["TWILIO_NUMBER"],
		                              body=mymessage,
		                              to=os.environ["CONTACT_NUMBER"]
		                          )
		print(message.sid)

	# Flask Routine: Serve Index Page
	def ResponseTextServer(self):
		return render_template('index.html', env=os.environ, dogwalker=self)

	# Flask Post? From Twilio?
	def UpdateSensorLimit(self):
		return render_template('twilio_response.html')

	def InBoundMessageResponse(self):
		# Get text message body from POST request
		body = request.values.get('Body', None)
		print("Received Message: %s" % str(body) )

		# Craft Twilio Response
		response = MessagingResponse()
		message = Message()
		rstring = None


		if body.lower().startswith("limit="):
			self.limit = int(body[len("limit="):] )
			rstring = "Setting Alert Limit to {0} degrees".format(self.limit)
		else:
			rstring = "Respond with message starting with `limit=` to set an alert!"
		message.body(rstring)
		response.append(message)

		return str(response)


if __name__ == '__main__':
	hi = DogTempSensor()

	while True:
		print("Still Running")
		print("H,T,Tc: %s", hi.clean_sensors )
		print(hi.temp_buff)
		print(hi.humid_buff)
		sleep(5)


		