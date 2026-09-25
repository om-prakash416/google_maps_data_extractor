import os
import sys
import time
import uuid
import csv
import json
import queue
import threading
from flask import Flask, render_template, request, jsonify, send_file

try:
    import pandas as pd
except ImportError:
    pd = None

from scraper_engine import ScraperEngine

# Configure Playwright browser cache path
PLAYWRIGHT_BROWSERS_PATH = os.path.expanduser("~/.cache/ms-playwright")
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = PLAYWRIGHT_BROWSERS_PATH

try:
    from waitress import serve
    HAS_WAITRESS = True
except ImportError:
    HAS_WAITRESS = False

app = Flask(__name__)

# Ensure required directories exist
STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs')
JOBS_DIR = os.path.join(STORAGE_DIR, 'jobs')
os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(JOBS_DIR, exist_ok=True)

# Concurrency configuration: 2 workers for 3-core / 11GB RAM server
NUM_WORKERS = 2
job_queue = queue.Queue()
active_jobs = {}
jobs_lock = threading.Lock()


def get_job_file_path(job_id):
    return os.path.join(JOBS_DIR, f"{job_id}.json")


def save_job_to_disk(job_id):
    """Persist job state to disk so server restarts don't lose data."""
    with jobs_lock:
        job = active_jobs.get(job_id)
        if not job:
            return
        snapshot = {
            'job_id': job_id,
            'status': job['status'],
            'area': job.get('area', ''),
            'pincode': job.get('pincode', ''),
            'created_at': job.get('created_at', time.time()),
            'last_updated': time.time(),
            'data': job.get('data', []),
            'results_count': len(job.get('data', []))
        }
    
    try:
        fpath = get_job_file_path(job_id)
        tmp_fpath = f"{fpath}.tmp"
        with open(tmp_fpath, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False)
        os.replace(tmp_fpath, fpath)
    except Exception as e:
        print(f"[Storage Warning] Could not save job {job_id}: {e}")


def load_jobs_from_disk():
    """Load existing jobs from disk on server startup."""
    if not os.path.exists(JOBS_DIR):
        return
        
    now = time.time()
    for fname in os.listdir(JOBS_DIR):
        if not fname.endswith('.json'):
            continue
        job_id = fname[:-5]
        fpath = os.path.join(JOBS_DIR, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Skip if older than 4 hours
            if now - data.get('created_at', now) > 14400:
                continue

            status = data.get('status', 'completed')
            # If server restarted while job was running/queued, mark as interrupted
            if status in ['running', 'queued']:
                status = 'interrupted'
                saved_count = len(data.get('data', []))
                logs = [
                    f"⚠️ Server was restarted while this job was processing.",
                    f"💾 {saved_count} records collected before restart are preserved and available for download."
                ]
            else:
                logs = ["✅ Job loaded from disk cache."]

            active_jobs[job_id] = {
                'status': status,
                'logs': logs,
                'data': data.get('data', []),
                'stop_flag': True,
                'area': data.get('area', 'Extracted_Data'),
                'pincode': data.get('pincode', ''),
                'last_sent_index': 0,
                'created_at': data.get('created_at', now)
            }
        except Exception as e:
            print(f"[Load Error] Failed reading {fname}: {e}")


def worker_thread(worker_id):
    """Dedicated background worker thread. Runs scraper jobs from the queue."""
    engine = ScraperEngine(headless=True)
    print(f"[Worker-{worker_id}] Started and waiting for jobs...")
    
    while True:
        job = job_queue.get()
        job_id = job['job_id']
        
        with jobs_lock:
            if job_id not in active_jobs:
                job_queue.task_done()
                continue
            active_jobs[job_id]['status'] = 'running'
            active_jobs[job_id]['logs'].append(f"🚀 [Worker-{worker_id}] Started processing job...")
            
        def log_callback(msg):
            with jobs_lock:
                if job_id in active_jobs:
                    active_jobs[job_id]['logs'].append(msg)
                    
        def stop_check():
            with jobs_lock:
                if job_id in active_jobs:
                    return active_jobs[job_id].get('stop_flag', False)
                return True

        def data_callback(item):
            """Real-time data streaming: live table gets rows immediately."""
            with jobs_lock:
                if job_id in active_jobs:
                    active_jobs[job_id]['data'].append(item)
            # Periodic flush to disk every 5 items
            current_count = len(active_jobs[job_id]['data'])
            if current_count % 5 == 0:
                save_job_to_disk(job_id)
                
        try:
            data = engine.run(
                query=job['query'],
                area=job['area'],
                pincode=job.get('pincode', ''),
                radius=job.get('radius', ''),
                max_results=job['max_results'],
                max_threads=1,
                proxy=job.get('proxy', None),
                log_callback=log_callback,
                data_callback=data_callback,
                stop_check=stop_check
            )
            
            with jobs_lock:
                if job_id in active_jobs:
                    # Sync any final items
                    if data and len(data) > len(active_jobs[job_id]['data']):
                        active_jobs[job_id]['data'] = data
                        
                    if active_jobs[job_id].get('stop_flag', False):
                        active_jobs[job_id]['status'] = 'stopped'
                        active_jobs[job_id]['logs'].append(f"🛑 Job stopped. Total {len(active_jobs[job_id]['data'])} leads collected.")
                    else:
                        active_jobs[job_id]['status'] = 'completed'
                        active_jobs[job_id]['logs'].append(f"🎉 Job completed! Total {len(active_jobs[job_id]['data'])} leads collected.")
                        
        except Exception as e:
            with jobs_lock:
                if job_id in active_jobs:
                    active_jobs[job_id]['status'] = 'error'
                    active_jobs[job_id]['logs'].append(f"❌ Worker Error: {str(e)}")
        finally:
            save_job_to_disk(job_id)
            job_queue.task_done()


def cleanup_worker():
    """Background task to remove old jobs & output files to prevent RAM & disk leaks.
    NEVER deletes jobs that are currently running or queued!
    """
    while True:
        time.sleep(300)  # Check every 5 minutes
        now = time.time()
        
        # Cleanup jobs older than 4 hours ONLY if completed/error/interrupted/stopped
        with jobs_lock:
            expired_ids = [
                jid for jid, jinfo in list(active_jobs.items())
                if jinfo.get('status') not in ['running', 'queued'] and (now - jinfo.get('created_at', now) > 14400)
            ]
            for jid in expired_ids:
                active_jobs.pop(jid, None)
                # Remove disk backup
                try:
                    fpath = get_job_file_path(jid)
                    if os.path.exists(fpath):
                        os.remove(fpath)
                except Exception:
                    pass
            
        # Cleanup outputs folder files older than 4 hours
        try:
            for fname in os.listdir(STORAGE_DIR):
                fpath = os.path.join(STORAGE_DIR, fname)
                if os.path.isfile(fpath) and (now - os.path.getmtime(fpath) > 14400):
                    os.remove(fpath)
        except Exception:
            pass


# 1. Load any persisted jobs from disk
load_jobs_from_disk()

# 2. Start 2 background worker threads for concurrency
for worker_idx in range(1, NUM_WORKERS + 1):
    threading.Thread(target=worker_thread, args=(worker_idx,), daemon=True).start()

# 3. Start cleanup thread
threading.Thread(target=cleanup_worker, daemon=True).start()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/scrape', methods=['POST'])
def start_scrape():
    req = request.json or {}
    query = req.get('query')
    area = req.get('area')
    pincode = req.get('pincode', '')
    radius = req.get('radius', '')
    max_results = req.get('max_results', 20)
    max_threads = req.get('max_threads', 2)
    proxy = req.get('proxy', '').strip()
    
    if not query or not area:
        return jsonify({"error": "Query and Area are required"}), 400
        
    try:
        max_results = int(max_results)
    except ValueError:
        return jsonify({"error": "Max Results must be a number"}), 400

    job_id = str(uuid.uuid4())
    queue_pos = job_queue.qsize() + 1
    
    with jobs_lock:
        active_jobs[job_id] = {
            'status': 'queued',
            'logs': [f"📋 Job queued. Position in queue: {queue_pos}"],
            'data': [],
            'stop_flag': False,
            'area': area,
            'pincode': pincode,
            'last_sent_index': 0,
            'created_at': time.time()
        }
    
    save_job_to_disk(job_id)
    
    job_queue.put({
        'job_id': job_id,
        'query': query,
        'area': area,
        'pincode': pincode,
        'radius': radius,
        'max_results': max_results,
        'max_threads': 1,
        'proxy': proxy if proxy else None
    })
    
    return jsonify({
        "job_id": job_id, 
        "message": f"Job queued successfully! Position in queue: {queue_pos}"
    })


@app.route('/api/status/<job_id>', methods=['GET'])
def check_status(job_id):
    with jobs_lock:
        if job_id not in active_jobs:
            # Try to load from disk in case of cold restart
            disk_path = get_job_file_path(job_id)
            if os.path.exists(disk_path):
                try:
                    with open(disk_path, 'r', encoding='utf-8') as f:
                        disk_data = json.load(f)
                    active_jobs[job_id] = {
                        'status': disk_data.get('status', 'completed'),
                        'logs': ["💾 Job retrieved from disk storage."],
                        'data': disk_data.get('data', []),
                        'stop_flag': True,
                        'area': disk_data.get('area', 'Extracted_Data'),
                        'pincode': disk_data.get('pincode', ''),
                        'last_sent_index': 0,
                        'created_at': disk_data.get('created_at', time.time())
                    }
                except Exception:
                    pass
                    
        if job_id not in active_jobs:
            return jsonify({
                "status": "not_found",
                "logs": ["❌ Job not found in server memory or disk storage."],
                "new_data": [],
                "results_count": 0,
                "error": "Job not found"
            }), 404
            
        job = active_jobs[job_id]
        logs_to_send = list(job['logs'])
        job['logs'].clear()
        
        last_idx = job.get('last_sent_index', 0)
        current_data = job['data']
        new_data = current_data[last_idx:]
        job['last_sent_index'] = len(current_data)
        current_status = job['status']
        results_count = len(current_data)
    
    return jsonify({
        "status": current_status,
        "logs": logs_to_send,
        "new_data": new_data,
        "results_count": results_count
    })


@app.route('/api/stop/<job_id>', methods=['POST'])
def stop_scrape(job_id):
    with jobs_lock:
        if job_id in active_jobs:
            active_jobs[job_id]['stop_flag'] = True
            active_jobs[job_id]['logs'].append("🛑 Stopping job gracefully...")
            return jsonify({"message": "Stop signal sent"})
    return jsonify({"error": "Job not found"}), 404


@app.route('/api/download/<job_id>/<format_type>', methods=['GET'])
def download_data(job_id, format_type):
    with jobs_lock:
        job = active_jobs.get(job_id)
        if not job:
            return "Job not found", 404
        records = list(job['data'])
        area_name = job.get('area', 'Extracted_Data').replace(',', '_').replace(' ', '')
        pincode_val = job.get('pincode', '')

    if not records:
        return "No data to download", 400
        
    if len(area_name) > 30:
        area_name = area_name[:30]
        
    if format_type == 'hisgro':
        hisgro_data = []
        for item in records:
            hisgro_data.append({
                'name': item.get('Name', ''),
                'shop_name': item.get('Name', ''),
                'email': item.get('Emails', ''),
                'phone': item.get('Phone', ''),
                'address': item.get('Address', ''),
                'city': '', 
                'state': '',
                'pincode': pincode_val,
                'owner_name': '',
                'map_url': item.get('Maps URL', ''),
                'area_id': '',
                'lead_status': 'pending',
                'assign_id': '',
                'status': '1'
            })
        filepath = os.path.join(STORAGE_DIR, f"data_{job_id}_hisgro.csv")
        if hisgro_data:
            keys = list(hisgro_data[0].keys())
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(hisgro_data)
        return send_file(filepath, as_attachment=True, download_name=f"{area_name}_Hisgro.csv")
        
    elif format_type == 'csv':
        filepath = os.path.join(STORAGE_DIR, f"data_{job_id}.csv")
        all_keys = list(records[0].keys())
        fields_param = request.args.get('fields', '')
        if fields_param:
            selected_fields = [f.strip() for f in fields_param.split(',') if f.strip()]
            valid_fields = [f for f in selected_fields if f in all_keys]
            if valid_fields:
                all_keys = valid_fields
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(records)
        return send_file(filepath, as_attachment=True, download_name=f"{area_name}.csv")
        
    elif format_type in ['xlsx', 'xls']:
        if pd is None:
            return "Excel export requires pandas which is disabled to save RAM. Please download as CSV.", 400
        df = pd.DataFrame(records)
        fields_param = request.args.get('fields', '')
        if fields_param:
            selected_fields = [f.strip() for f in fields_param.split(',') if f.strip()]
            valid_fields = [f for f in selected_fields if f in df.columns]
            if valid_fields:
                df = df[valid_fields]
        filepath = os.path.join(STORAGE_DIR, f"data_{job_id}.{format_type}")
        df.to_excel(filepath, index=False)
        return send_file(filepath, as_attachment=True, download_name=f"{area_name}.{format_type}")
    else:
        return "Unsupported format", 400


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 7860))
    if HAS_WAITRESS:
        print(f"Starting Waitress production server on 0.0.0.0:{port} with 6 HTTP threads & 2 Scraper workers...")
        serve(app, host='0.0.0.0', port=port, threads=6)
    else:
        print(f"Waitress not available, falling back to app.run on port {port}...")
        app.run(host='0.0.0.0', port=port, debug=False)
