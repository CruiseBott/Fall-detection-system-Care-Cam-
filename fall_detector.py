import numpy as np
import time

class FallDetector:
    def __init__(self, fall_threshold=45, fall_duration=2.0, sit_threshold=50, chair_height_ratio=0.6):
        self.fall_threshold = fall_threshold
        self.fall_duration = fall_duration
        self.sit_threshold = sit_threshold
        self.chair_height_ratio = chair_height_ratio
        self.person_trackers = {}

    def determine_pose(self, keypoints):
    # Extract keypoints
        left_shoulder = np.array(keypoints[5])
        right_shoulder = np.array(keypoints[6])
        left_hip = np.array(keypoints[11])
        right_hip = np.array(keypoints[12])
        left_knee = np.array(keypoints[13])
        right_knee = np.array(keypoints[14])
        left_ankle = np.array(keypoints[15])
        right_ankle = np.array(keypoints[16])
    
    # Validate keypoints: if any critical keypoints are missing (i.e., all zero)
        for point in [left_shoulder, right_shoulder, left_hip, right_hip, left_ankle, right_ankle]:
            if np.all(point == 0):
                return "UNKNOWN"

        # Calculate midpoints
        shoulder_mid = (left_shoulder + right_shoulder) / 2
        hip_mid = (left_hip + right_hip) / 2
        knee_mid = (left_knee + right_knee) / 2
        ankle_mid = (left_ankle + right_ankle) / 2

        # Calculate vectors
        torso_vector = shoulder_mid - hip_mid
        thigh_vector = knee_mid - hip_mid
        lower_leg_vector = ankle_mid - knee_mid
        vertical_vector = np.array([0, -1])  # pointing up in image coordinates

        # Calculate angles
        torso_angle = self.calculate_angle(torso_vector, vertical_vector)
        knee_angle = self.calculate_angle(thigh_vector, lower_leg_vector)

        # Calculate ratios
        total_height = np.linalg.norm(shoulder_mid - ankle_mid)
        hip_height = np.linalg.norm(hip_mid - ankle_mid)
        hip_height_ratio = hip_height / total_height if total_height != 0 else 0

        # Additional horizontal check
        shoulder_to_ankle_vec = shoulder_mid - ankle_mid
        horizontal_ratio = abs(shoulder_to_ankle_vec[0]) / np.linalg.norm(shoulder_to_ankle_vec)

        # Additional ankle-hip distance for confirming lying
        ankle_hip_dist = np.linalg.norm(ankle_mid - hip_mid)

        # Determine pose
        if torso_angle >= self.fall_threshold and horizontal_ratio > 0.5:
            if ankle_hip_dist < 0.2 * total_height:
                return "LYING"
    
        elif torso_angle >= self.sit_threshold:
            if hip_height_ratio <= self.chair_height_ratio:
                return "SITTING_CHAIR"
            else:
                return "SITTING_FLOOR"
    
        elif knee_angle < 100:
            return "SQUATTING"  # Optional category

        return "STANDING"


    def calculate_angle(self, vector1, vector2):
        angle = np.arccos(np.dot(vector1, vector2) / 
                          (np.linalg.norm(vector1) * np.linalg.norm(vector2)))
        return np.degrees(angle)

    def detect_fall(self, person_id, pose):
        if person_id not in self.person_trackers:
            self.person_trackers[person_id] = {'lying_start_time': None}

        if pose == "LYING":
            if self.person_trackers[person_id]['lying_start_time'] is None:
                self.person_trackers[person_id]['lying_start_time'] = time.time()
            elif time.time() - self.person_trackers[person_id]['lying_start_time'] >= self.fall_duration:
                return True
        else:
            self.person_trackers[person_id]['lying_start_time'] = None

        return False