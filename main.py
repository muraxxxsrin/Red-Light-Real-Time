# from speed import SpeedModule

# if __name__ == "__main__":
#     speed = SpeedModule()
#     speed.process()


import threading
from speed import SpeedModule
from redLight import redWrongViolation
from helmetSeatbeltMobile import SafetyViolationModule


def run_speed():
    SpeedModule().process()


def run_traffic_rules():
    redWrongViolation().process()

def run_safety():
    SafetyViolationModule().process()


if __name__ == "__main__":

    print("🚀 Starting Traffic Violation System...")

    t1 = threading.Thread(target=run_speed)
    t2 = threading.Thread(target=run_traffic_rules)
    t3 = threading.Thread(target=run_safety)

    t1.start()
    t2.start()
    t3.start()

    t1.join()
    t2.join()
    t3.join()

    print("✅ All modules finished")
