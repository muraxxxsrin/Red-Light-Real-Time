import json
import os
import time
import threading
from api.cloudinaryUploader import upload_violation_image
from DB.violationLogger import ViolationLogger

OFFLINE_FILE = "offline_uploads.json"
logger = ViolationLogger()

def save_to_offline(challan_id, image_path):
    """
    Appends a failed upload to the offline JSON queue.
    """
    tasks = []
    if os.path.exists(OFFLINE_FILE):
        try:
            with open(OFFLINE_FILE, "r") as f:
                tasks = json.load(f)
        except:
            tasks = []
            
    tasks.append({
        "challan_id": challan_id,
        "image_path": image_path,
        "timestamp": time.time()
    })
    
    with open(OFFLINE_FILE, "w") as f:
        json.dump(tasks, f, indent=4)
        
    print(f"💾 Saved {challan_id} to offline queue. Total offline tasks: {len(tasks)}")


def _offline_sync_worker():
    """
    Runs continuously in a background thread, checking the offline queue every 30 seconds.
    If the network is up (Cloudinary succeeds), it clears out the backlog.
    """
    print("🔄 Offline Sync Daemon started. Monitoring for network recovery...")
    while True:
        time.sleep(30) # Check every 30 seconds
        
        if not os.path.exists(OFFLINE_FILE):
            continue
            
        try:
            with open(OFFLINE_FILE, "r") as f:
                tasks = json.load(f)
        except:
            continue
            
        if not tasks:
            continue
            
        print(f"📡 Network Check: Attempting to flush {len(tasks)} offline uploads...")
        
        remaining_tasks = []
        network_down = False
        
        for task in tasks:
            if network_down:
                # If one fails, assume network is still down, keep the rest for next cycle
                remaining_tasks.append(task)
                continue
                
            challan_id = task["challan_id"]
            image_path = task["image_path"]
            
            # Attempt upload
            image_url = upload_violation_image(image_path)
            
            if image_url:
                print(f"✅ Offline Sync Success: {challan_id}")
                logger.update_image_url(challan_id, image_url)
            else:
                print(f"❌ Network still unreachable for {challan_id}. Pausing sync.")
                network_down = True
                remaining_tasks.append(task)
                
        # Write back ONLY the tasks that still haven't been uploaded
        with open(OFFLINE_FILE, "w") as f:
            json.dump(remaining_tasks, f, indent=4)
            
        if len(tasks) != len(remaining_tasks):
            print(f"✅ Offline Sync Complete. Remaining tasks: {len(remaining_tasks)}")

def start_offline_sync():
    """
    Spawns the daemon thread that monitors the offline queue.
    """
    t = threading.Thread(target=_offline_sync_worker, daemon=True)
    t.start()
