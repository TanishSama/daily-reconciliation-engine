#!/usr/bin/env python3
"""
app.py — Interactive Web Workstation Launcher for Project 2.

Usage:
    python app.py
    python app.py --port 8081
"""

import argparse
import http.server
import os
import socketserver
import sys
import webbrowser

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(PROJECT_ROOT, "web")

def main():
    parser = argparse.ArgumentParser(description="Launch Project 2 Interactive Reconciliation Workstation")
    parser.add_argument("--port", type=int, default=8081, help="Port to bind (default: 8081)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open browser")
    args = parser.parse_args()

    # Ensure data bundle exists
    data_js_path = os.path.join(WEB_DIR, "data.js")
    if not os.path.exists(data_js_path):
        print("Data bundle missing. Generating web dataset bundle from CSVs...")
        sys.path.insert(0, PROJECT_ROOT)
        from web.bundle_data import export_bundle
        export_bundle()

    os.chdir(WEB_DIR)
    handler = http.server.SimpleHTTPRequestHandler

    port = args.port
    max_tries = 10
    httpd = None
    for attempt in range(max_tries):
        try:
            httpd = socketserver.TCPServer(("", port), handler)
            break
        except OSError:
            print(f"Port {port} in use, trying {port + 1}...")
            port += 1

    if httpd is None:
        print("Error: Could not bind to an open port.")
        sys.exit(1)

    url = f"http://localhost:{port}/index.html"
    print("=" * 64)
    print("  APEX RECONCILIATION WORKSTATION // FINANCIAL CONTROL")
    print(f"  Live local server: {url}")
    print("  Press Ctrl+C to stop the server.")
    print("=" * 64)

    if not args.no_browser:
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

if __name__ == "__main__":
    main()
