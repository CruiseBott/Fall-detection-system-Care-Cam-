import cv2
import time
from threading import Thread
from ultralytics import YOLO

# Add this import at the top of the file
import requests
from datetime import datetime

class VideoProcessor:
    def __init__(self, model_path, frame_queue, confidence_threshold=0.5):
        self.model = YOLO(model_path)
        self.frame_queue = frame_queue
        self.confidence_threshold = confidence_threshold
        self.should_stop = False
        self.processing_thread = None
        self.total_fall_time = 0
        self.fall_detected_duration = 2  # seconds
        self.monitoring_duration = 10  # seconds
        self.start_time = time.time()
        self.last_detection_time = None

    def process_frame(self, frame):
        results = self.model(frame)
        falling_detected = False

        for result in results:
            for box in result.boxes:
                if box.conf < self.confidence_threshold:
                    continue  # Skip detections with low confidence

                class_id = box.cls
                class_name = self.model.names[int(class_id)]
                x1, y1, x2, y2 = map(int, box.xyxy[0])  # Get bounding box coordinates

                # Draw bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                # Put class label text
                cv2.putText(frame, class_name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

                if class_name == 'fall':
                    falling_detected = True
                    if self.last_detection_time is None:
                        self.last_detection_time = time.time()
                    else:
                        self.total_fall_time += time.time() - self.last_detection_time
                        self.last_detection_time = time.time()
                    break

        if not falling_detected:
            self.last_detection_time = None

        # Check if total fall time exceeds the threshold within the monitoring duration
        if self.total_fall_time >= self.fall_detected_duration:
            cv2.putText(frame, "FALL DETECTED", (50, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        # Reset total fall time and start time if monitoring duration has passed
        if time.time() - self.start_time >= self.monitoring_duration:
            self.total_fall_time = 0
            self.start_time = time.time()

        return frame

    def process_video(self, video_path, camera_id):
        self.should_stop = False
        cap = cv2.VideoCapture(video_path)
        
        while cap.isOpened() and not self.should_stop:
            success, frame = cap.read()
            if not success:
                break

            processed_frame = self.process_frame(frame)

            if self.frame_queue.full():
                self.frame_queue.get()
            self.frame_queue.put(processed_frame)
            time.sleep(0.01)

        cap.release()

    def start_processing(self, video_path, camera_id):
        if self.processing_thread and self.processing_thread.is_alive():
            self.stop_processing()
        self.processing_thread = Thread(target=self.process_video, args=(video_path, camera_id))
        self.processing_thread.start()

    def stop_processing(self):
        self.should_stop = True
        if self.processing_thread:
            self.processing_thread.join()

    def process_frame(self, frame, camera_id):
        # Process the frame with YOLO
        results = self.model(frame)
        
        # Draw bounding boxes on the frame
        annotated_frame = results[0].plot()
        
        # Check if fall is detected
        fall_detected = False
        for r in results:
            for c in r.boxes.cls:
                class_name = r.names[int(c)]
                if class_name == 'fall':
                    fall_detected = True
                    break
        
        # Send alert if fall is detected and cooldown period has passed
        current_time = datetime.now()
        if fall_detected and (not self.fall_detected or 
                             (self.last_alert_time and 
                              (current_time - self.last_alert_time).total_seconds() > self.alert_cooldown)):
            self.fall_detected = True
            self.last_alert_time = current_time
            self.send_fall_alert(camera_id)
        elif not fall_detected:
            self.fall_detected = False
        
        return annotated_frame

    def send_fall_alert(self, camera_id):
        """Send an alert to the server when a fall is detected"""
        try:
            # Get the first user ID (in a real app, you'd determine which user to alert)
            # For testing, we'll use user ID 1
            user_id = 1
            
            # Send alert to the server
            response = requests.post(
                f'http://127.0.0.1:5000/send_alert/{user_id}',
                data={
                    'location': f'Camera {camera_id}',
                    'severity': 'High'
                }
            )
            
            if response.status_code == 200:
                print(f"Alert sent successfully for camera {camera_id}")
            else:
                print(f"Failed to send alert: {response.status_code}")
                
        except Exception as e:
            print(f"Error sending fall alert: {e}")

class VideoStreamer:
    def __init__(self, esp32_cam, video_processor):
        self.esp32_cam = esp32_cam
        self.video_processor = video_processor

    def start(self):
        self.esp32_cam.start()

    def stop(self):
        self.esp32_cam.stop()

    def generate_frames(self):
        self.start()
        try:
            while True:
                frame = self.esp32_cam.get_frame()
                if frame is not None:
                    processed_frame = self.video_processor.process_frame(frame)
                    _, buffer = cv2.imencode('.jpg', processed_frame)
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                else:
                    time.sleep(0.01)
        finally:
            self.stop()
            
class FileVideoStreamer:
    def __init__(self, frame_queue):
        self.frame_queue = frame_queue

    def get_frame(self):
        while True:
            if not self.frame_queue.empty():
                frame = self.frame_queue.get()
                _, buffer = cv2.imencode('.jpg', frame)
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            else:
                time.sleep(0.01)
