#!/bin/bash 

source /home/elvyn/hk-arial/venv_hkarial/bin/activate #activate virtual environment 

python /home/elvyn/hk-arial/live_inference.py -m "/home/elvyn/hk-arial/result-v3-yolo11/best_openvino_2022.1_6shave.blob" -c "/home/elvyn/hk-arial/result-v3-yolo11/best.json" # running program with appropriate parameters   
