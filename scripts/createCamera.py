import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from cameraRegistry import CameraRegistry

registry = CameraRegistry()

camera_id = registry.create_camera(
    "OMR Signal, Chennai",
    12.8432,
    80.1544
)

print(camera_id)