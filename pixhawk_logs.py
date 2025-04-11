from pymavlink import mavutil 

import datetime 

import subprocess 

import os 

  

log_dir = "/home/elvyn/hk-arial/pixhawk_logs" 

os.makedirs(log_dir, exist_ok=True) 

  

# Connect to the Pixhawk 

MAVLINK_CONNECTION = "serial:/dev/ttyAMA0" 

master = mavutil.mavlink_connection(MAVLINK_CONNECTION, baud=921600) 

  

print("Waiting for heartbeat...") 

master.wait_heartbeat() 

print("Heartbeat received!") 

  

log_process = None 

armed = False 

  

while True: 

    msg = master.recv_match(type='HEARTBEAT', blocking=True) 

    if not msg: 

        continue 

  

    # Check arm status 

    current_armed = (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) != 0 

  

    if current_armed and not armed: 

        print("Drone armed! Starting logging...") 

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S") 

        log_file = os.path.join(log_dir, f"flightlog_{timestamp}.tlog") 

        log_process = subprocess.Popen([ 

            "mavproxy.py", 

            "--master=/dev/ttyAMA0", 

            f"--logfile={log_file}" 

        ]) 

        armed = True 

  

    elif not current_armed and armed: 

        print("Drone disarmed. Stopping logging...") 

        if log_process: 

            log_process.terminate() 

            log_process = None 

        armed = False 
