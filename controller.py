'''
Elvyn Cachapero
Code was created to create an infinite control loop that will create logs from Pixhawk 
and centralize them into the /hk-arial/logs folder. Added handling to initiate object detection
based on ARM & DISARM status.
'''

import os
import time 
import subprocess 
import logging 
from datetime import datetime 
from pymavlink import mavutil 

# Configurations 
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
MAVLINK_CONNECTION = "/dev/ttyAMA0"  
LOG_DIR = "/home/hkarial/hk-arial/logs/pixhawk_logs" 
CONTROLLER_LOG_DIR = "/home/hkarial/hk-arial/logs/controller_logs"
LOG_FILE = f"{CONTROLLER_LOG_DIR}/controller_{timestamp}.log" 
OBJECT_DETECTION_SCRIPT = "/home/hkarial/hk-arial/live_inference.py" 
#LOGGING_SCRIPT = "/home/hkarial/hk-arial/pixhawk_logs.py" # Deprecated
MODEL_PATH = "/home/hkarial/hk-arial/result-v3-yolo11/best_openvino_2022.1_6shave.blob"
CONFIG_PATH = "/home/hkarial/hk-arial/result-v3-yolo11/best.json"
master = mavutil.mavlink_connection(MAVLINK_CONNECTION, baud=921600)

# Setup logging 
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s - %(message)s') 

# Logging network connection
#with open("/home/hkarial/hk-arial/logs/network_log.txt", "a") as log:
#	log.write(f"[{timestamp}] Startup:n")
#	log.write(os.popen("date").read())
#	log.write(os.popen("ip addr").read())
#	log.write("\n\n")

# Connect to MAVLink for ARM check
logging.info("Connecting to MAVLink...") 
logging.info("Waiting for heartbeat...")
master.wait_heartbeat() 
logging.info("Heartbeat received from system ID %s", master.target_system) 

# Script process handles 
detection_proc = None 
def start_scripts(): 
    global detection_proc
     
    if detection_proc is None: 
        detection_proc = subprocess.Popen([
            "python", OBJECT_DETECTION_SCRIPT,
            "-m", MODEL_PATH,
            "-c", CONFIG_PATH])
        logging.info("Object detection script started.") 

def stop_scripts(): 
    global detection_proc, log_proc 
    if detection_proc: 
        detection_proc.terminate() 
        detection_proc.wait() 
        logging.info("Object detection script stopped.") 
        detection_proc = None 

# Main loop
armed = False
mavlinkFile_handle = None
try: 
    logging.info("Starting controller loop...") 
    while True: 
        msg = master.recv_match(type="HEARTBEAT", blocking=True, timeout=1) 
        # Logging raw mavlink data
        if msg: 
            is_armed = msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED 
            if is_armed and not armed: 
                log_file = os.path.join(LOG_DIR, f"flightlog_{timestamp}.tlog")
                mavlinkFile_handle = open(log_file, 'wb')
                master.logfile_raw = mavlinkFile_handle
                logging.info("Drone armed - logging started.")
                start_scripts()
                armed = True
            elif not is_armed and armed: 
                if master.logfile_raw:
                    master.logfile_raw.flush()
                    master.logfile_raw.close()
                    master.logfile_raw = None
                mavlinkFile_handle = None
                logging.info("Drone disarmed - logging stopping.")
                stop_scripts()
                armed = False
        time.sleep(0.3)
        
# Excepts for graceful shutdowns to prevent corruption
except KeyboardInterrupt: 
    logging.info("Shutting down due to KeyboardInterrupt.") 
    stop_scripts() 
    if master.logfile_raw:
        master.logfile_raw.close()

except Exception as e: 
    logging.error("Exception occurred: %s", e) 
    stop_scripts()
    if master.logfile_raw:
        master.logfile_raw.close()
