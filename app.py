from flask import Flask, render_template, request, jsonify, send_file
import threading
import queue
import uuid
import time
import os
import pandas as pd
from scraper_engine import ScraperEngine

app = Flask(__name__)

# Global state to manage jobs and queue
# For a free server with 512MB RAM, we should strictly limit to 1 concurrent job.
job_queue = queue.Queue()
active_jobs = {} # { job_id: { 'status': 'queued|running|completed|error', 'logs': [], 'data': [], 'stop_flag': False } }
current_running_job_id = None

def worker_thread():
    global current_running_job_id
    engine = ScraperEngine(headless=True)
    
    while True:
        job = job_queue.get()
        job_id = job['job_id']
        current_running_job_id = job_id
        
        active_jobs[job_id]['status'] = 'running'
        active_jobs[job_id]['logs'].append("🚀 Job started processing from the queue...")
        
        def log_callback(msg):
            if job_id in active_jobs:
                active_jobs[job_id]['logs'].append(msg)
                
        def stop_check():
            if job_id in active_jobs:
                return active_jobs[job_id].get('stop_flag', False)
            return True
            
        try:
            data = engine.run(
                query=job['query'],
                area=job['area'],
                pincode=job.get('pincode', ''),
                radius=job['radius'],
                max_results=job['max_results'],
                max_threads=job.get('max_threads', 2),
                proxy=job.get('proxy', None),
                log_callback=log_callback,
                stop_check=stop_check
            )
            
            if job_id in active_jobs:
                active_jobs[job_id]['data'] = data
                active_jobs[job_id]['status'] = 'completed'
                active_jobs[job_id]['logs'].append("🎉 Job completed successfully.")
        except Exception as e:
            if job_id in active_jobs:
                active_jobs[job_id]['status'] = 'error'
                active_jobs[job_id]['logs'].append(f"❌ Server Error: {str(e)}")
                
        current_running_job_id = None
        job_queue.task_done()

# Start the background worker
threading.Thread(target=worker_thread, daemon=True).start()


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/scrape', methods=['POST'])
def start_scrape():
    req = request.json
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
        max_threads = int(max_threads)
    except ValueError:
        return jsonify({"error": "Max Results and Max Threads must be numbers"}), 400

    job_id = str(uuid.uuid4())
    active_jobs[job_id] = {
        'status': 'queued',
        'logs': [f"📋 Job created. Position in queue: {job_queue.qsize() + 1}"],
        'data': [],
        'stop_flag': False,
        'area': area,
        'last_sent_index': 0
    }
    
    job_queue.put({
        'job_id': job_id,
        'query': query,
        'area': area,
        'pincode': pincode,
        'radius': radius,
        'max_results': max_results,
        'max_threads': max_threads,
        'proxy': proxy if proxy else None
    })
    
    return jsonify({"job_id": job_id, "message": "Job queued successfully"})

@app.route('/api/status/<job_id>', methods=['GET'])
def check_status(job_id):
    if job_id not in active_jobs:
        return jsonify({
            "status": "error",
            "logs": ["❌ Polling Error: Job not found in server memory. The server likely restarted due to memory or time limits."],
            "new_data": [],
            "results_count": 0,
            "error": "Job not found (Server restarted)"
        }), 200
        
    job = active_jobs[job_id]
    
    # Send logs and clear them to prevent massive payload over time
    logs_to_send = list(job['logs'])
    job['logs'].clear()
    
    # Send incremental new data for the live table
    last_idx = job.get('last_sent_index', 0)
    current_data = job['data']
    new_data = current_data[last_idx:]
    job['last_sent_index'] = len(current_data)
    
    return jsonify({
        "status": job['status'],
        "logs": logs_to_send,
        "new_data": new_data,
        "results_count": len(current_data)
    })

@app.route('/api/stop/<job_id>', methods=['POST'])
def stop_scrape(job_id):
    if job_id in active_jobs:
        active_jobs[job_id]['stop_flag'] = True
        return jsonify({"message": "Stop signal sent"})
    return jsonify({"error": "Job not found"}), 404

@app.route('/api/download/<job_id>/<format_type>', methods=['GET'])
def download_data(job_id, format_type):
    if job_id not in active_jobs:
        return "Job not found", 404
        
    job = active_jobs[job_id]
    if not job['data']:
        return "No data to download", 400
        
    os.makedirs('outputs', exist_ok=True)
    df = pd.DataFrame(job['data'])
    
    # Filter columns based on selected fields
    fields_param = request.args.get('fields', '')
    if fields_param:
        selected_fields = [f.strip() for f in fields_param.split(',') if f.strip()]
        # Only keep columns that exist in the data and were selected
        valid_fields = [f for f in selected_fields if f in df.columns]
        if valid_fields:
            df = df[valid_fields]
    
    area_name = job.get('area', 'Extracted_Data').replace(',', '_').replace(' ', '')
    if len(area_name) > 30:
        area_name = area_name[:30] # Keep filename length reasonable
        
    if format_type == 'hisgro':
        hisgro_data = []
        for item in job['data']:
            hisgro_data.append({
                'shop_name': item.get('Name', ''),
                'email': '',
                'phone': item.get('Phone', ''),
                'address': item.get('Address', ''),
                'owner_name': '',
                'map_url': item.get('Maps URL', ''),
                'area_id': '',
                'lead_status': 'pending',
                'assign_id': '',
                'status': '1'
            })
        df_hisgro = pd.DataFrame(hisgro_data)
        filepath = f"outputs/data_{job_id}_hisgro.csv"
        df_hisgro.to_csv(filepath, index=False)
        return send_file(filepath, as_attachment=True, download_name=f"{area_name}_Hisgro.csv")
    elif format_type == 'csv':
        filepath = f"outputs/data_{job_id}.csv"
        df.to_csv(filepath, index=False)
        return send_file(filepath, as_attachment=True, download_name=f"{area_name}.csv")
    elif format_type in ['xlsx', 'xls']:
        filepath = f"outputs/data_{job_id}.{format_type}"
        df.to_excel(filepath, index=False)
        return send_file(filepath, as_attachment=True, download_name=f"{area_name}.{format_type}")
    else:
        return "Unsupported format", 400

if __name__ == '__main__':
    # Use port 7860 for Hugging Face Spaces compatibility
    port = int(os.environ.get('PORT', 7860))
    app.run(host='0.0.0.0', port=port, debug=False)
