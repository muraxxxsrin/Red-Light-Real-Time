import math
import config  # Imports your settings

class SpeedTracker:
    def __init__(self, fps):
        self.car_positions = {}
        self.car_speeds = {}
        self.fps = fps 

    def update(self, car_id, centroid):
        cx, cy = centroid
        
        if car_id not in self.car_positions:
            self.car_positions[car_id] = []

        self.car_positions[car_id].append((cx, cy))
        
        # Keep memory short
        if len(self.car_positions[car_id]) > 20:
            self.car_positions[car_id].pop(0)

        # Calculate Speed
        if len(self.car_positions[car_id]) > config.FRAME_GAP:
            p2 = self.car_positions[car_id][-1]
            p1 = self.car_positions[car_id][-1 - config.FRAME_GAP]
            
            distance_pixels = math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
            distance_meters = distance_pixels / config.PIXELS_PER_METER
            time_seconds = config.FRAME_GAP / self.fps
            
            speed_kmh = (distance_meters / time_seconds) * 3.6
            self.car_speeds[car_id] = round(speed_kmh, 1)

        return self.car_speeds.get(car_id, 0.0)


