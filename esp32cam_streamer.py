import cv2

class ESP32CamStreamer:
    def __init__(self, esp32_cam_url):
        self.esp32_cam_url = esp32_cam_url.rstrip('/')  # Ensure no trailing slash
        self.cap = None

    def start(self):
        if self.cap is None or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(self.esp32_cam_url)

    def stop(self):
        if self.cap and self.cap.isOpened():
            self.cap.release()
            self.cap = None

    def get_frame(self):
        if self.cap is None or not self.cap.isOpened():
            self.start()

        if self.cap:
            success, frame = self.cap.read()
            if success:
                return frame
        return None
