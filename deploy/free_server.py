"""Lightweight standard library web server to trigger the pipeline via webhooks on Render Free Tier."""

import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

class WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "healthy", "service": "ai-news-agent"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/run':
            # Run the pipeline in a background thread
            def run_pipeline():
                print("Webhook triggered: Starting pipeline run...")
                subprocess.run([sys.executable, "main.py"])
                print("Webhook pipeline run completed.")
            
            threading.Thread(target=run_pipeline).start()
            
            self.send_response(202)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "triggered", "message": "Pipeline started in background"}')
        else:
            self.send_response(404)
            self.end_headers()

def run_server():
    port = int(os.environ.get("PORT", "8080"))
    server_address = ('', port)
    httpd = HTTPServer(server_address, WebhookHandler)
    print(f"Starting server on port {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server...")
        httpd.server_close()

if __name__ == '__main__':
    run_server()
