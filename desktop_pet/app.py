import datetime
import logging
import os
import queue
import socket
import sys
import threading

from flask import Flask, request, jsonify

from desktop_pet.config import load_app_config
from desktop_pet.state import StateMachine
from desktop_pet.gui import DesktopPet
from desktop_pet.alarm import AlarmManager
from desktop_pet.shared import events, event_queue, app_state, app_state_lock, PET_PORT
from desktop_pet.shared import stats_tracker, balance_fetcher, git_info

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)
logger = logging.getLogger()

app = Flask(__name__)

MAX_CONTENT_LENGTH = 1 * 1024 * 1024
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/event", methods=["POST", "OPTIONS"])
def handle_event():
    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "No data provided or invalid JSON"}), 400

    event_type = data.get("event", "unknown")
    message = data.get("message", "")
    transcript_path = data.get("transcript_path")
    cwd = data.get("cwd")

    event_record = {
        "event": event_type,
        "message": message,
        "timestamp": datetime.datetime.now().isoformat()
    }
    with app_state_lock:
        events.append(event_record)
        app_state["last_event_time"] = datetime.datetime.now()

    # 用量统计 + git 状态（后台解析，非阻塞）
    if transcript_path:
        stats_tracker.on_activity(transcript_path, cwd)
    if cwd:
        git_info.set_cwd(cwd)

    try:
        event_queue.put_nowait((event_type, message))
    except queue.Full:
        logger.warning("[EVENT] Queue full, dropping event")

    logger.info("=" * 50)
    logger.info(f"[EVENT] Received: {event_type}")
    if message:
        logger.info(f"[MESSAGE] {message}")
    logger.info(f"[TIME] {event_record['timestamp']}")
    logger.info("=" * 50)

    return jsonify({"status": "ok", "event": event_type})


@app.route("/events", methods=["GET"])
def list_events():
    with app_state_lock:
        current = {
            "current_state": app_state["current_state"],
            "current_message": app_state["current_message"],
        }
        events_snapshot = list(events)
    return jsonify({"events": events_snapshot, **current})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/stats", methods=["GET"])
def get_stats():
    snap = stats_tracker.snapshot()
    return jsonify({
        "cost": snap["cost"],
        "peak_cost": snap["peak_cost"],
        "off_peak_cost": snap["off_peak_cost"],
        "legacy_cost": snap["legacy_cost"],
        "efficiency": snap["efficiency"],
        "satiety": snap["satiety"],
        "food": snap["food"],
        "stats": snap["stats"],
        "balance": balance_fetcher.get(),
        "git": git_info.get(),
    })


@app.route("/balance", methods=["GET"])
def get_balance():
    return jsonify({"balance": balance_fetcher.get()})


@app.errorhandler(413)
def request_entity_too_large(error):
    logger.warning(f"Request too large, max: {MAX_CONTENT_LENGTH} bytes")
    return jsonify({"error": "Request too large"}), 413


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return False
        except OSError:
            return True


def start_flask(port):
    import werkzeug.serving
    werkzeug.serving._log_add_style = False
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def run_pet():
    """启动桌面宠物应用"""
    PORT = PET_PORT

    if is_port_in_use(PORT):
        logger.error(f"Port {PORT} is already in use! Another pet instance may be running.")
        logger.error(f"Run: netstat -ano | findstr \":{PORT}\" to find the process.")
        sys.exit(1)

    logger.info("Desktop Pet App Starting...")
    logger.info(f"Flask listening on: http://localhost:{PORT}")
    logger.info("Endpoint: POST /event")
    logger.info("\nPress Ctrl+C to stop")

    flask_thread = threading.Thread(target=start_flask, args=(PORT,), daemon=True)
    flask_thread.start()

    state_machine = StateMachine()
    pet = DesktopPet(state_machine)
    state_machine.set_callback(pet._on_state_change)

    # 启动闹钟管理器
    alarm_manager = AlarmManager(
        get_config=lambda: pet.config,
        save_config=lambda: None,  # 闹钟不主动保存，由GUI操作时保存
        root=pet.root,
    )
    alarm_manager.start()

    pet.run()


if __name__ == "__main__":
    run_pet()
