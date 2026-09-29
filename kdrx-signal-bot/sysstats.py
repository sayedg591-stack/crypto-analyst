# -*- coding: utf-8 -*-
"""جمع إحصائيات الخادم: CPU, RAM, Disk, Load."""
import os


def get_stats():
    """إرجاع قاموس بإحصائيات الخادم."""
    stats = {
        "cpu_pct": 0.0,
        "ram_pct": 0.0,
        "ram_used_gb": 0.0,
        "ram_total_gb": 0.0,
        "disk_pct": 0.0,
        "load_1m": 0.0,
        "cores": 1,
    }
    try:
        # CPU cores
        stats["cores"] = os.cpu_count() or 1

        # Load average (1 min)
        try:
            stats["load_1m"] = round(os.getloadavg()[0], 2)
        except Exception:
            pass

        # RAM from /proc/meminfo
        try:
            with open("/proc/meminfo") as f:
                mem = {}
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        mem[parts[0].rstrip(":")] = int(parts[1])
            total = mem.get("MemTotal", 1)
            avail = mem.get("MemAvailable", mem.get("MemFree", 0))
            used = total - avail
            stats["ram_pct"] = round(used / total * 100, 1)
            stats["ram_used_gb"] = round(used / 1024 / 1024, 1)
            stats["ram_total_gb"] = round(total / 1024 / 1024, 1)
        except Exception:
            pass

        # Disk from / (root)
        try:
            st = os.statvfs("/")
            total = st.f_blocks * st.f_frsize
            free = st.f_bavail * st.f_frsize
            used = total - free
            stats["disk_pct"] = round(used / total * 100, 1) if total else 0
        except Exception:
            pass

        # CPU % from /proc/stat (two samples)
        try:
            def cpu_times():
                with open("/proc/stat") as f:
                    parts = f.readline().split()[1:]
                vals = list(map(int, parts))
                idle = vals[3] + vals[4]
                total = sum(vals)
                return idle, total
            i1, t1 = cpu_times()
            import time as _t
            _t.sleep(0.5)
            i2, t2 = cpu_times()
            idle_d = i2 - i1
            total_d = t2 - t1
            if total_d > 0:
                stats["cpu_pct"] = round((1 - idle_d / total_d) * 100, 1)
        except Exception:
            pass
    except Exception:
        pass
    return stats
