#!/usr/bin/env python3

'''
Elvyn Cachapero
The code is edited from docs (https://docs.luxonis.com/projects/api/en/latest/samples/Yolo/tiny_yolo/)
We add parsing from JSON files that contain configuration
'''

from datetime import datetime
from pathlib import Path
import sys
import cv2
import depthai as dai
import numpy as np
import time
import argparse
import json
import blobconverter
import csv
import signal

# Handling closing signals
def handle_sigterm(signum, frame):
    print("[INFO] SIGTERM Received, cleaning up...")
    video_writer.release()
    sys.exit(0)
signal.signal(signal.SIGTERM, handle_sigterm)

# setting up for logging
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
LOG_PATH = f"/home/hkarial/hk-arial/logs/detection_logs/detections_{timestamp}.csv"
LOG_FILE = open(LOG_PATH, mode='w', newline='')
csv_writer = csv.writer(LOG_FILE)
csv_writer.writerow(['timestamp', 'label', 'confidence', 'xmin', 'ymin', 'xmax', 'ymax'])

# parse arguments
parser = argparse.ArgumentParser()
parser.add_argument("-m", "--model", help="Provide model name or model path for inference",
                    default='yolov4_tiny_coco_416x416', type=str)
parser.add_argument("-c", "--config", help="Provide config path for inference",
                    default='json/yolov4-tiny.json', type=str)
args = parser.parse_args()

# parse config
configPath = Path(args.config)
if not configPath.exists():
    raise ValueError("Path {} does not exist!".format(configPath))

with configPath.open() as f:
    config = json.load(f)
nnConfig = config.get("nn_config", {})

# parse input shape
if "input_size" in nnConfig:
    W, H = tuple(map(int, nnConfig.get("input_size").split('x')))

# extract metadata
metadata = nnConfig.get("NN_specific_metadata", {})
classes = metadata.get("classes", {})
coordinates = metadata.get("coordinates", {})
anchors = metadata.get("anchors", {})
anchorMasks = metadata.get("anchor_masks", {})
iouThreshold = metadata.get("iou_threshold", {})

confidenceThreshold = metadata.get("confidence_threshold", {})

print(metadata)

# parse labels
nnMappings = config.get("mappings", {})
labels = nnMappings.get("labels", {})

# get model path
nnPath = args.model
if not Path(nnPath).exists():
    print("No blob found at {}. Looking into DepthAI model zoo.".format(nnPath))
    nnPath = str(blobconverter.from_zoo(args.model, shaves = 6, zoo_type = "depthai", use_cache=True))
# sync outputs
syncNN = True

# Create pipeline
pipeline = dai.Pipeline()

# Define sources and outputs
camRgb = pipeline.create(dai.node.ColorCamera)
detectionNetwork = pipeline.create(dai.node.YoloDetectionNetwork)
xoutRgb = pipeline.create(dai.node.XLinkOut)
nnOut = pipeline.create(dai.node.XLinkOut)

xoutRgb.setStreamName("rgb")
nnOut.setStreamName("nn")

# Properties

camRgb.setPreviewSize(W, H)

camRgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
camRgb.setInterleaved(False)
camRgb.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
camRgb.setFps(40)

# Network specific settings
detectionNetwork.setConfidenceThreshold(confidenceThreshold)
detectionNetwork.setNumClasses(classes)
detectionNetwork.setCoordinateSize(coordinates)
detectionNetwork.setAnchors(anchors)
detectionNetwork.setAnchorMasks(anchorMasks)
detectionNetwork.setIouThreshold(iouThreshold)
detectionNetwork.setBlobPath(nnPath)
detectionNetwork.setNumInferenceThreads(2)
detectionNetwork.input.setBlocking(False)

# Linking
camRgb.preview.link(detectionNetwork.input)
detectionNetwork.passthrough.link(xoutRgb.input)
detectionNetwork.out.link(nnOut.input)

# Connect to device and start pipeline
with dai.Device(pipeline) as device:

    # Output queues will be used to get the rgb frames and nn data from the outputs defined above
    qRgb = device.getOutputQueue(name="rgb", maxSize=4, blocking=False)
    qDet = device.getOutputQueue(name="nn", maxSize=4, blocking=False)

    frame = None
    detections = []
    startTime = time.monotonic()
    counter = 0
    color2 = (255, 255, 255)

    # Video Writer Setup
    first_frame = qRgb.get().getCvFrame()  # Get first frame to determine size
    frame_height, frame_width, _ = first_frame.shape
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video_writer = cv2.VideoWriter(
        f"/home/hkarial/hk-arial/logs/flight_videos/detection_recording_{timestamp}.mp4",
        fourcc, 30, (frame_width, frame_height)
    )

    print("Recording started... Press 'q' to stop.")

    # nn data, being the bounding box locations, are in <0..1> range - they need to be normalized with frame width/height
    def frameNorm(frame, bbox):
        normVals = np.full(len(bbox), frame.shape[0])
        normVals[::2] = frame.shape[1]
        return (np.clip(np.array(bbox), 0, 1) * normVals).astype(int)

    # Uncomment for a live view of detection (requires monitor output)
    #def displayFrame(name, frame, detections):
    #    color = (255, 0, 0)
    #    for detection in detections:
    #        bbox = frameNorm(frame, (detection.xmin, detection.ymin, detection.xmax, detection.ymax))
    #        cv2.putText(frame, labels[detection.label], (bbox[0] + 10, bbox[1] + 20), cv2.FONT_HERSHEY_TRIPLEX, 0.5, 255)
    #        cv2.putText(frame, f"{int(detection.confidence * 100)}%", (bbox[0] + 10, bbox[1] + 40), cv2.FONT_HERSHEY_TRIPLEX, 0.5, 255)
    #        cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2)
        # Show the frame
        cv2.imshow(name, frame)

    try:
        while True:
            inRgb = qRgb.get()
            inDet = qDet.get()

            if inRgb is not None:
                frame = inRgb.getCvFrame()
                # Rotate image 180 degrees for upside mounting plan
                frame = cv2.rotate(frame, cv2.ROTATE_180)
                cv2.putText(frame, "NN fps: {:.2f}".format(counter / (time.monotonic() - startTime)),
                            (2, frame.shape[0] - 4), cv2.FONT_HERSHEY_TRIPLEX, 0.4, color2)

            if inDet is not None:
                detections = inDet.detections
                counter += 1

                for detection in detections:
                    # Fixing orientation for bounding boxes
                    ymin_flipped = 1 - detection.ymin
                    ymax_flipped = 1 - detection.ymax
                    xmin_flipped = 1 - detection.xmin
                    xmax_flipped = 1 - detection.xmax
                    
                    csv_writer.writerow([
                        timestamp,
                        labels[detection.label] if detection.label < len(labels) else f"id_{detection.label}",
                        round(detection.confidence, 4),
                        ymin_flipped,
                        ymax_flipped,
                        xmin_flipped,
                        xmax_flipped
                    ])

            if frame is not None:
                #displayFrame("rgb", frame, detections) # Uncomment only if you have monitor plugged in
                # Draw all detections on the frame
                for detection in detections:
                    # Rotating bounding boxes 180 degrees to match camera orientation
                    flipped_bbox = (
                        1 - detection.xmax,
                        1 - detection.ymax,
                        1 - detection.xmin,
                        1 - detection.ymin
                    )
                    
                    bbox = frameNorm(frame, (detection.xmin, detection.ymin, detection.xmax, detection.ymax))
                    label = labels[detection.label] if detection.label < len(labels) else f"id_{detection.label}"
                    confidence = int(detection.confidence * 100)

                    cv2.putText(frame, label, (bbox[0] + 10, bbox[1] + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                    cv2.putText(frame, f"{confidence}%", (bbox[0] + 10, bbox[1] + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                    cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)

                video_writer.write(frame)



            if cv2.waitKey(1) == ord('q'):
                break

    except KeyboardInterrupt:
        print ("\n[INFO] Interrupted. Stopping live_inference.py")

    finally:
        video_writer.release()
        cv2.destroyAllWindows()
        print("[INFO] Video saved and resources released.")
