# Frigate Watcher

A quick and dirty script to handle `No frames have been received, check error logs` quick and dirty.

This script checks through the frigate stats if the ffmpeg process is still running. If a consecutive failes have been registered, this script will reboot frigate. The failure count is recorded at the MQTT topic frigate_watcher/[camrea_name]/failure_count. As soon as the ffmpeg pid of a camera is found in the stats, the counter is set to 0.

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
