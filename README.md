# Frigate Watcher

A quick and dirty script to handle `No frames have been received, check error logs` quick and dirty.

This script checks through the frigate stats if the ffmpeg process is still running. If the consecutive fails hit the treshold has been registered for your camera, this script will reboot frigate. The failure count is recorded at the MQTT topic frigate_watcher/[camrea_name]/failure_count. As soon as the ffmpeg pid of a camera is found in the stats, the counter is set to 0.

After a reboot, ffmpeg processes will spin up to restore the connection with your camera. If, for instance, the camera has been shut down, frigate_watcher will reboot frigate until the power is restored.

This script is not meant to run as a service, it could be a cron job for every x seconds.

## frigate_watcher.json

```json
{
    "mqtt": {
        "broker": "", //the address of the mqtt broker
        "port": 1883,
        "username": "", //the username to connect to the broker
        "password": ", //the password to connect to the broker
        "base_topic": "frigate_watcher", //the base topic to report to
        "frigate_base_topic": "frigate" //the base topic of frigate
    },
    "frigate_url": ", //the url of frigate
    "log_level": "debug",
    "failure_count_treshold": 5, //the number of consecutive failures before a reboot is initiated
    "restart": true //define of the reboot should be initiated
```

## Home Assistant

Place `frigate_watcher.py` and `frigate_watcher.json` in `/config/python_scripts/`

### Sensor

Create a command line sensor that runs every 60 seconds

```yaml
- platform: command_line
  name: Frigate Command Line
  scan_interval: 60
  command_timeout: 300
  command: python3 /config/python_scripts/frigate_watcher.py
```

### Automation

This automation will notify when a restart is initiated by frigate_watcher. Change the 5 if you have set a different value at `failure_count_treshold` in `frigate_watcher.json`

```yaml
- id: frigate_notifications
  alias: Frigate Notifications
  description: ""
  trigger:
    - platform: mqtt
      topic: frigate_watcher/+/failure_count
      id: frigatewatcher
  action:
    choose:
    - conditions:
      - condition: trigger
        id: frigatewatcher
      sequence:
      - condition: and
        conditions:
        - condition: template
          value_template: >-
            {% if (trigger.payload_json | int) == 5 %} {{ True }}
            {% else %} False
            {% endif %}
      - service: notify.mobile_app_iphone
        data:
          title: "Frigate watcher"
          message: "Frigate will be restared, got {{ trigger.payload_json | string }} failure counts on topic {{ trigger.topic | string }}"
```
