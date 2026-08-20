#!/usr/bin/env python3
"""
Poll build task progress every 5 minutes and push to Snorlax Desktop Pet bubble.
Usage:
  python scripts/build_progress_pusher.py --task-id <uuid>
"""
import argparse, json, time, sys, io, os
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PET_URL = "http://localhost:3456/event"
BUILD_STATUS_URL = "http://localhost:8000/knowledge/build/status"
INTERVAL_SEC = 300  # 5 minutes

_last_done = -1


def get_build_status(task_id):
    """Fetch build status from bilibili-rag backend."""
    try:
        req = urllib.request.Request(f"{BUILD_STATUS_URL}/{task_id}")
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return {"error": str(e)}


def push_bubble(message, persist=False):
    """Send show_bubble event to pet."""
    event_type = "show_bubble_persist" if persist else "show_bubble_persist"
    data = json.dumps({"event": event_type, "message": message}).encode('utf-8')
    try:
        req = urllib.request.Request(PET_URL, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception as e:
        print(f"  Push error: {e}")
        return False


def format_progress(status):
    """Format build progress as a pet-friendly message."""
    if "error" in status:
        return f"🐾 进度查询失败: {status['error']}"

    done = status.get("processed_videos", 0)
    total = status.get("total_videos", 1)
    pct = status.get("progress", 0)
    build_status = status.get("status", "unknown")
    cur = status.get("current_video_title", "")[:50]

    if build_status == "completed":
        return f"🎉 全部完成！{done}个视频已入库，即将开始AI总结～"

    if build_status == "failed":
        return f"😿 出错了... 已处理{done}/{total}，message: {status.get('message','')[:80]}"

    # Running — make a compact progress message
    # Calculate rough ETA
    global _last_done
    if _last_done > 0:
        speed = done - _last_done
        remaining = total - done
        eta_min = remaining / speed * 5 if speed > 0 else 999
        if eta_min < 60:
            eta_str = f"约{eta_min:.0f}分钟"
        else:
            eta_str = f"约{eta_min/60:.1f}小时"
    else:
        eta_str = "计算中..."

    _last_done_val = done  # will update global at end

    return (
        f"📚 设计仿真入库中\n"
        f"进度 {pct}% ({done}/{total})\n"
        f"剩余 {eta_str}\n"
        f"当前: {cur}"
    )


def main():
    global _last_done

    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True, help="Build task UUID")
    parser.add_argument("--interval", type=int, default=INTERVAL_SEC, help="Poll interval in seconds")
    parser.add_argument("--once", action="store_true", help="Send one update and exit")
    args = parser.parse_args()

    print(f"Build Progress Pusher started")
    print(f"  Task: {args.task_id}")
    print(f"  Interval: {args.interval}s")
    print(f"  Pet: {PET_URL}")

    # Initial bubble
    push_bubble("🔍 开始监控设计仿真入库进度...\n每5分钟更新一次哦~")

    while True:
        time.sleep(args.interval)

        status = get_build_status(args.task_id)
        done = status.get("processed_videos", 0)

        if done != _last_done:
            msg = format_progress(status)
            push_bubble(msg)
            print(f"[{time.strftime('%H:%M:%S')}] {status.get('progress',0)}% ({done}/{status.get('total_videos','?')}) | {status.get('current_video_title','')[:50]}")
            _last_done = done

        build_status = status.get("status", "")
        if build_status == "completed":
            push_bubble(f"🎉 入库完成！{done}个视频\n开始AI总结+分类保存...")
            print("Build complete! Exiting pusher.")
            break
        elif build_status == "failed":
            push_bubble(f"😿 入库失败: {status.get('message','')[:100]}")
            print("Build failed! Exiting pusher.")
            break

        if args.once:
            break


if __name__ == "__main__":
    main()
