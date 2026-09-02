"""
Day 8: Shiksha Call Analytics Dashboard

Run:
    python dashboard.py

Open:
    http://localhost:5000
"""

from flask import Flask, jsonify, render_template_string
import sqlite3
import os
from datetime import datetime


app = Flask(__name__)


# ============================================================
# DATABASE
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DB_PATH = os.path.join(
    BASE_DIR,
    "shiksha_memory.db"
)


# ============================================================
# DATABASE SETUP
# ============================================================

def init_db():

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS call_logs (
            call_id TEXT PRIMARY KEY,
            channel TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT,
            outcome TEXT NOT NULL,
            reason TEXT
        )
        """
    )

    conn.commit()
    conn.close()


init_db()


# ============================================================
# HTML
# ============================================================

PAGE = """
<!DOCTYPE html>

<html>

<head>

    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>Shiksha - Call Analytics</title>

    <meta
        http-equiv="refresh"
        content="5"
    >

    <style>

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            padding: 40px;
            font-family: Arial, sans-serif;
            background: #0f1117;
            color: #e8e8e8;
        }

        .container {
            max-width: 1100px;
            margin: auto;
        }

        h1 {
            margin-bottom: 5px;
        }

        .subtitle {
            color: #888;
            margin-bottom: 30px;
        }

        .cards {
            display: grid;
            grid-template-columns:
                repeat(auto-fit, minmax(200px, 1fr));

            gap: 20px;
        }

        .card {
            background: #1a1d27;
            border-radius: 14px;
            padding: 28px;
            text-align: center;
        }

        .num {
            font-size: 46px;
            font-weight: bold;
        }

        .label {
            color: #999;
            margin-top: 8px;
        }

        .total .num {
            color: #66b3ff;
        }

        .success .num {
            color: #4caf50;
        }

        .failed .num {
            color: #f44336;
        }

        .rate {
            margin-top: 20px;
            color: #aaa;
        }

        .section {
            margin-top: 45px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            background: #1a1d27;
            border-radius: 12px;
            overflow: hidden;
        }

        th,
        td {
            text-align: left;
            padding: 14px;
            border-bottom: 1px solid #2a2d3a;
        }

        th {
            color: #999;
            font-weight: normal;
        }

        .badge {
            padding: 5px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: bold;
        }

        .success {
            color: #4caf50;
        }

        .failed {
            color: #f44336;
        }

        .in_progress {
            color: #ffcc66;
        }

        .footer {
            color: #666;
            margin-top: 25px;
            font-size: 13px;
        }

        @media (max-width: 700px) {

            body {
                padding: 20px;
            }

            table {
                font-size: 13px;
            }

            th,
            td {
                padding: 9px;
            }

        }

    </style>

</head>


<body>

<div class="container">

    <h1>Shiksha — Call Analytics</h1>

    <div class="subtitle">
        Day 8 • Learning & Literacy
    </div>


    <!-- ================================================= -->
    <!-- MAIN METRICS -->
    <!-- ================================================= -->

    <div class="cards">

        <div class="card total">

            <div class="num">
                {{ total }}
            </div>

            <div class="label">
                Total Calls
            </div>

        </div>


        <div class="card success">

            <div class="num">
                {{ success }}
            </div>

            <div class="label">
                Successful Calls
            </div>

        </div>


        <div class="card failed">

            <div class="num">
                {{ failed }}
            </div>

            <div class="label">
                Failed Calls
            </div>

        </div>

    </div>


    <!-- ================================================= -->
    <!-- SUCCESS RATE -->
    <!-- ================================================= -->

    <div class="rate">

        Success Rate:
        <strong>{{ rate }}%</strong>

    </div>


    <!-- ================================================= -->
    <!-- RECENT CALLS -->
    <!-- ================================================= -->

    <div class="section">

        <h2>
            Recent Calls
        </h2>


        <table>

            <thead>

                <tr>

                    <th>Call ID</th>

                    <th>Channel</th>

                    <th>Start Time</th>

                    <th>Duration</th>

                    <th>Outcome</th>

                    <th>Reason</th>

                </tr>

            </thead>


            <tbody>

            {% for row in recent %}

                <tr>

                    <td>
                        {{ row.call_id }}
                    </td>

                    <td>
                        {{ row.channel }}
                    </td>

                    <td>
                        {{ row.start_time }}
                    </td>

                    <td>
                        {{ row.duration }}
                    </td>

                    <td>

                        <span
                            class="badge {{ row.outcome }}"
                        >

                            {{ row.outcome }}

                        </span>

                    </td>

                    <td>
                        {{ row.reason or '' }}
                    </td>

                </tr>

            {% else %}

                <tr>

                    <td
                        colspan="6"
                        style="text-align:center;color:#777;"
                    >

                        No calls recorded yet.

                    </td>

                </tr>

            {% endfor %}

            </tbody>

        </table>

    </div>


    <div class="footer">

        Auto-refreshes every 5 seconds.
        No transcripts or sensitive caller information
        are displayed.

    </div>

</div>

</body>

</html>
"""


# ============================================================
# GET STATISTICS
# ============================================================

def get_stats():

    conn = sqlite3.connect(
        DB_PATH
    )

    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()


    # Total
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM call_logs
        """
    )

    total = cursor.fetchone()[0]


    # Successful
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM call_logs
        WHERE outcome = 'success'
        """
    )

    success = cursor.fetchone()[0]


    # Failed
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM call_logs
        WHERE outcome = 'failed'
        """
    )

    failed = cursor.fetchone()[0]


    # Recent calls
    cursor.execute(
        """
        SELECT
            call_id,
            channel,
            start_time,
            end_time,
            outcome,
            reason
        FROM call_logs
        ORDER BY start_time DESC
        LIMIT 15
        """
    )

    rows = cursor.fetchall()

    conn.close()


    # --------------------------------------------------------
    # Calculate duration
    # --------------------------------------------------------

    recent = []

    for row in rows:

        duration = "-"

        if row["start_time"] and row["end_time"]:

            try:

                start = datetime.fromisoformat(
                    row["start_time"]
                )

                end = datetime.fromisoformat(
                    row["end_time"]
                )

                seconds = int(
                    (end - start).total_seconds()
                )

                minutes = seconds // 60
                remaining = seconds % 60

                duration = (
                    f"{minutes}m {remaining}s"
                )

            except Exception:

                duration = "-"


        recent.append(
            {
                "call_id": row["call_id"],
                "channel": row["channel"],
                "start_time": row["start_time"],
                "duration": duration,
                "outcome": row["outcome"],
                "reason": row["reason"],
            }
        )


    # --------------------------------------------------------
    # Success rate
    # --------------------------------------------------------

    rate = (
        round(
            (success / total) * 100,
            1
        )
        if total > 0
        else 0
    )


    return (
        total,
        success,
        failed,
        rate,
        recent,
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
def dashboard():

    (
        total,
        success,
        failed,
        rate,
        recent,
    ) = get_stats()


    return render_template_string(
        PAGE,
        total=total,
        success=success,
        failed=failed,
        rate=rate,
        recent=recent,
    )


# ============================================================
# JSON API
# ============================================================

@app.route("/api/stats")
def api_stats():

    (
        total,
        success,
        failed,
        rate,
        recent,
    ) = get_stats()


    return jsonify(
        {
            "total_calls": total,
            "successful_calls": success,
            "failed_calls": failed,
            "success_rate_percent": rate,
        }
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print(
        "=========================================="
    )

    print(
        "Shiksha Call Analytics Dashboard"
    )

    print(
        "Database:",
        DB_PATH
    )

    print(
        "Open: http://localhost:5000"
    )

    print(
        "=========================================="
    )

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
    )