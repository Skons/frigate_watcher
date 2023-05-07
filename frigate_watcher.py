import requests
import logging, logging.handlers
import paho.mqtt.client as mqttClient
import time, datetime
import json
import os, sys

def on_connect(client, userdata, flags, rc):
  """
  Handle connection to MQTT server
  """
  if rc == 0:
      global Connected,logger,broker_address
      logger.info(f"MQTT client Connected to '{broker_address}'")
      Connected = True

  else:
      logger.error(f"Failed to connect to '{broker_address}' with result code '{rc}")
      quit()

def on_message(client, userdata, message):
  """
  Parse the results of the retained values
  """
  global logger,current_fc_count,last_registered_reboot
  message_topic = str(message.topic).lower()
  logger.info(f"Received payload on topic '{message_topic}'")
  if message_topic.endswith("failure_count"):
    current_fc_count = int(message.payload.decode())
  elif message_topic.endswith("last_reboot"):
    last_registered_reboot = message.payload.decode()
  else:
    logger.warning(f"Unknown topic '{message_topic}'")

def copy_log(type,timestamp_for_log):
  '''
  Get the log file from the frigate api and store it to disk
  '''
  global frigate_base_url,current_folder
  logs_url = frigate_base_url + '/api/logs/' + type
  try:
    log_resp = requests.get(logs_url)
    logger.info(f"Status Code of '{logs_url}' is '{log_resp.status_code}'")
    log_file = os.path.join(current_folder, timestamp_for_log + "_" + type + ".log")
    with open(log_file, 'wb') as f:
      f.write(log_resp.content)
    logger.info(f"'{type}' logs have been written to '{log_file}'")
  except requests.exceptions.RequestException as e:
    logger.error('%s', e)

# get config file
current_folder = os.path.dirname(os.path.realpath(__file__))
config_file = os.path.join(current_folder,"frigate_watcher.json")
if os.path.isfile(config_file) == False:
  raise Exception(f"Unable to find config file '{config_file}'")

with open(config_file) as file:
  config_file_contents = file.read()

try:
  configuration = json.loads(config_file_contents)
except ValueError:  # includes simplejson.decoder.JSONDecodeError
  raise Exception(f"Decoding configuration file '{config_file}' has failed")

# define logger
loglevel = 'info'
if 'log' in configuration:
  if 'level' in configuration['log']:
    loglevel = configuration['log']['level'].upper()

log_file = os.path.join(current_folder,"frigate_watcher.log")
formatter = logging.Formatter('%(asctime)s.%(msecs)03d %(name)s %(levelname)s	%(message)s','%Y-%m-%d %H:%M:%S')
log_handler = logging.handlers.RotatingFileHandler(log_file,maxBytes=20000000,backupCount=2)
log_handler.setFormatter(formatter)
#log_handler = logging.StreamHandler(sys.stdout)
logger = logging.getLogger()
logger.addHandler(log_handler)
logger.setLevel(loglevel)

# define variables from configuration
broker_address = configuration['mqtt']['broker']
port = int(configuration['mqtt']['port'])
user = configuration['mqtt']['username']
password = configuration['mqtt']['password']
Connected = False
base_topic = (configuration['mqtt']['base_topic']).strip('/')
max_failures = int(configuration['failure_count_treshold'])
if max_failures < 3:
  raise Exception(f"Please provide 'failure_count_treshold' with a value larger then 2")

frigate_base_url = (configuration['frigate_url']).strip('/')
frigate_stats_url = frigate_base_url + '/api/stats'
frigate_base_topic = (configuration['mqtt']['frigate_base_topic']).strip('/')
frigate_restart_topic = frigate_base_topic + "/restart"
restart_frigate = bool(configuration['restart'])

# report configuration information
logger.debug(f"MQTT Broker address:     {broker_address}")
logger.debug(f"MQTT Broker port:        {port}")
logger.debug(f"MQTT Username:           {user}")
logger.debug(f"MQTT Password:           {password}")
logger.debug(f"MQTT Base topic:         {base_topic}")
logger.debug(f"MQTT Frigate base topic: {frigate_base_topic}")
logger.debug(f"Frigate url:             {frigate_base_url}")
logger.debug(f"Failure count treshold:  {max_failures}")
logger.debug(f"Restart Frigate:         {restart_frigate}")

# get stats from frigate
try:
  resp = requests.get(frigate_stats_url)
  logger.info(f"Status Code of '{frigate_stats_url}' is '{resp.status_code}'")
except requests.exceptions.RequestException as e:
  logger.error('%s', e)
  exit()

# connect to mqtt
client = mqttClient.Client("frigate_watcher")
client.username_pw_set(user, password=password)
client.connect(broker_address, port=port)
client.on_connect = on_connect
client.on_message = on_message
client.loop_start()
while Connected != True:
    time.sleep(0.1)

# frigate_watcher stats
stats_topic = base_topic + "/stats"
last_run_topic = stats_topic + "/last_run"
last_reboot_topic = stats_topic + "/last_reboot_initiated"
last_run = str(datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat())
client.publish(last_run_topic, last_run, 0, False)

# parse the frigate stats
frigate_stats = resp.json()
sent_restart = False
for (k, v) in frigate_stats.items():
  if isinstance(frigate_stats[k], dict): # only when the JSON value is of type dict
    if "camera_fps" in v: # test if the dictionary is of a camera
      # define the camera variables
      camera_name = str(k)
      camera_fc_topic = f"{base_topic}/{camera_name}/failure_count"
      # get the current failure count
      logger.info(f"Subscribing to '{camera_fc_topic}'")
      client.subscribe(camera_fc_topic)
      current_fc_count = -1
      for i in range(5): # give paho some slack to receive an retained value
        if current_fc_count > -1:
          break
        time.sleep(1)
      logger.info(f"Camera '{camera_name}' has got a failure count of '{current_fc_count}'")
      client.unsubscribe(camera_fc_topic)

      new_state = 0 # default value for the failure count
      if str(v['ffmpeg_pid']) in frigate_stats['cpu_usages']:
        logger.info(f"Camera '{camera_name}' has got ffmpeg_id '{str(v['ffmpeg_pid'])}'")
      else: # ffmpeg_pid is not known as a process with cpu_usages
        logger.warning(f"Camera '{camera_name}' does not have an ffmpeg id")
        new_state = current_fc_count + 1

      # restart frigate if the treshold has been hit, this run has not restarted frigate and restart has been enabled
      if new_state == max_failures and sent_restart == False and restart_frigate == True: # Publish restart of frigate
        # get the last registered reboot
        last_registered_reboot = None
        client.subscribe(last_reboot_topic)
        for i in range(5): # give paho some slack to receive an retained value
          if last_registered_reboot is not None:
            break
          time.sleep(1)
        client.unsubscribe(last_reboot_topic)

        # get the total minutes since last reboot
        # for now is this only for logging purposes. could be used against boot loops
        try:
          last_registered_reboot_time = datetime.datetime.strptime(last_registered_reboot, "%Y-%m-%dT%H:%M:%S.%f%z")
          delta = datetime.datetime.utcnow() - last_registered_reboot_time.replace(tzinfo=None) #define the time since the last reboot
          logger.info(f"Frigate last reboot time is '{last_registered_reboot}' which was '{(delta.total_seconds()/60)}' minutes ago")
        except Exception as e:
          logger.info(f"Frigate last reboot time '{last_registered_reboot}' is unknown with error '{e}'")

        # initiate frigate restart
        logger.warning(f"Camera '{camera_name}' has got '{new_state}' of the maximum '{max_failures}' failures, restarting frigate with topic '{frigate_restart_topic}' after copying logs")

        timestamp_for_log = time.strftime("%Y%m%d-%H%M%S")
        if 'log' in configuration:
          if 'copy' in configuration['log']:
            if 'frigate' in configuration['log']['copy'] and configuration['log']['copy']['frigate']:
              copy_log('frigate',timestamp_for_log)

            if 'go2rtc' in configuration['log']['copy'] and configuration['log']['copy']['go2rtc']:
              copy_log('go2rtc',timestamp_for_log)

            if 'nginx' in configuration['log']['copy'] and configuration['log']['copy']['nginx']:
              copy_log('nginx',timestamp_for_log)

        sent_restart = True
        last_reboot = str(datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat())
        client.publish(frigate_restart_topic, "", 0, True)
        client.publish(last_reboot_topic, last_reboot, 0, True)
      elif new_state == max_failures and sent_restart == True: # restart has already ben sent this run
        logger.warning(f"Camera '{camera_name}' has got '{new_state}' of the maximum '{max_failures}' failures, restart is already in progress")
        sent_restart = True
      elif new_state == max_failures and restart_frigate == False: # a restart could happen, but restart is False
        logger.warning(f"Camera '{camera_name}' has got '{new_state}' of the maximum '{max_failures}' failures, but frigate restart is set to '{restart_frigate}'")

      # report a new state if there is a change
      if current_fc_count is not new_state:
        logger.info(f"Updating '{camera_name}' with failure count '{new_state}' on topic '{camera_fc_topic}'")
        client.publish(camera_fc_topic, new_state, 0, True)

client.disconnect()
client.loop_stop()