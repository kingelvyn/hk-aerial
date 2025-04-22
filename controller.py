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
import select
import csv
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
#MODEL_PATH = "/home/hkarial/hk-arial/result-v3-yolo11/best_openvino_2022.1_6shave.blob"
#CONFIG_PATH = "/home/hkarial/hk-arial/result-v3-yolo11/best.json"
MODEL_PATH = "/home/hkarial/hk-arial/test-model/best_openvino_2022.1_6shave.blob"
CONFIG_PATH = "/home/hkarial/hk-arial/test-model/best.json"
master = mavutil.mavlink_connection(MAVLINK_CONNECTION, baud=57600, source_system=255)

# Setup logging 
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s - %(message)s') 

# CSV Format for MAVLink messages
csv_log_file = os.path.join(LOG_DIR, f"flightlog_{timestamp}.csv")
csv_log = open(csv_log_file, mode="w", newline = '')
csv_writer = csv.writer(csv_log)
csv_writer.writerow(["timestamp","lat","lon","alt","roll","pitch","yaw","ground_speed","climb"])

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
        logging.info("Model Path: %s", MODEL_PATH)
        logging.info("Config Path: %s", CONFIG_PATH)

def stop_scripts(): 
    global detection_proc
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
        #msg = master.recv_match(type="HEARTBEAT", blocking=True, timeout=1) 
        msg = master.recv_match(blocking=True, timeout=1)
        # Logging mavlink data
        if msg and msg.get_type() == "HEARTBEAT":
            is_armed = msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED 
            if is_armed and not armed:
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") 
                log_file = os.path.join(LOG_DIR, f"flightlog_{timestamp}.tlog")
                mavlinkFile_handle = open(log_file, 'wb')
                master.logfile = mavlinkFile_handle
                logging.info("Drone armed - logging started...")
                start_scripts()
                armed = True
                time.sleep(0.5)
                
            elif not is_armed and armed: 
                master.logfile = None
                logging.info("Drone disarmed - logging stopped...")
                if mavlinkFile_handle and not mavlinkFile_handle.closed:
                    mavlinkFile_handle.flush()
                    os.fsync(mavlinkFile_handle.fileno())
                    mavlinkFile_handle.close()
                    mavlinkFile_handle = None
                stop_scripts()
                armed = False
                
        # Custom CSV logs
        if msg:
            if msg.get_type() == "GLOBAL_POSITION_INT":
                csv_writer.writerow([
                    datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    msg.lat / 1e7,  # Convert to degrees
                    msg.lon / 1e7,  # Convert to degrees
                    msg.alt / 1000,  # Convert to meters
                    "", "", "", "", ""
                ])
                csv_log.flush()
                #logging.info(f"Logged GLOBAL_POSITION_INT: lat={msg.lat/1e7}, lon={msg.lon/1e7}, alt={msg.alt/1000}")

            elif msg.get_type() == "ATTITUDE":
                csv_writer.writerow([
                    datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "", "", "", msg.roll, msg.pitch, msg.yaw, "", ""
                ])
                csv_log.flush()
                #logging.info(f"Logged ATTITUDE: roll={msg.roll}, pitch={msg.pitch}, yaw={msg.yaw}")

            elif msg.get_type() == "VFR_HUD":
                csv_writer.writerow([
                    datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "", "", "", "", "", "", msg.groundspeed, msg.climb
                ])
                csv_log.flush()
                #logging.info(f"Logged VFR_HUD: groundspeed={msg.groundspeed}, climb={msg.climb}")

            elif msg.get_type() == "SYS_STATUS":
                csv_writer.writerow([
                    datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "", "", "", "", "", "", "", msg.battery_remaining
                ])
                csv_log.flush()
                #logging.info(f"Logged SYS_STATUS: battery_remaining={msg.battery_remaining}%")
        
# Excepts for graceful shutdowns to prevent corruption
except KeyboardInterrupt: 
    logging.info("Shutting down due to KeyboardInterrupt.") 
    stop_scripts() 
    try:
        master.logfile = None
        if mavlinkFile_handle and not mavlinkFile_handle.closed:
            mavlinkFile_handle.flush()
            os.fsync(mavlinkFile_handle.fileno())
            mavlinkFile_handle.close()
    except Exception as e:
        logging.warning("Error while closing log on shutdown - (KeyboardInterrupt): %s", e)

except Exception as e: 
    logging.error("Unhandled exception occurred: %s", e) 
    stop_scripts()
    try:
        master.logfile = None
        if mavlinkFile_handle and not mavlinkFile_handle.closed:
            mavlinkFile_handle.flush()
            os.fsync(mavlinkFile_handle.fileno())
            mavlinkFile_handle.close()
    except Exception as e:
        logging.warning("Error while closing log on shutdown - (Exception): %s", e)
finally:
    csv_log.close()
