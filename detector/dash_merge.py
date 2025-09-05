import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go
from modules.mongodb_config import get_alerts_collection, get_mongo_db
from collections import defaultdict
import datetime
import os
import argparse

# Parse command line arguments for output directory
parser = argparse.ArgumentParser(description='Dashboard with configurable output directory')
parser.add_argument('--output-dir', type=str, default='logs', help='Output directory for plots')
args = parser.parse_args()


# --- MongoDB setup ---
alerts = get_alerts_collection()

# Check if MongoDB connection is available
if alerts is None:
    print("Warning: MongoDB connection failed. Dashboard may not work properly.")
    exit(1)

# Wipe any leftover alerts from previous runs
try:
    alerts.delete_many({})
    print("Cleared previous alerts from MongoDB")
except Exception as e:
    print(f"Warning: Could not clear previous alerts: {e}")

# --- Dash app setup ---
app = dash.Dash(__name__)
app.title = "Live Network + Physical Anomalies"

# Create a session timestamp that matches the monitor script pattern
session_timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
session_logs_dir = os.path.join("logs", f"logs_{session_timestamp}")

app.layout = html.Div([
    html.H2("Network + Physical Anomalies (Live)"),
    dcc.Graph(id="live-graph"),
    dcc.Interval(id="interval", interval=5000, n_intervals=0)
])

@app.callback(Output("live-graph", "figure"), Input("interval", "n_intervals"))
def update_graph(n):
    try:
        # Get fresh alerts collection reference
        alerts = get_alerts_collection()
        if alerts is None:
            # Return empty figure if MongoDB is not available
            fig = go.Figure()
            fig.update_layout(
                title="MongoDB Connection Error",
                annotations=[dict(
                    x=0.5, y=0.5, text="MongoDB connection failed",
                    showarrow=False, font=dict(size=20), xref="paper", yref="paper"
                )]
            )
            return fig
            
        # 1) Fetch & merge network anomalies (only integer iterations)
        raw_net = list(alerts.find({
            "tank":              {"$exists": False},
            "IP":                {"$exists": True},
            #"communicateswith":  {"$exists": True, "$ne": None, "$ne": "unknown"}
        }))
        
        for a in raw_net:
            a["dest"] = a.get("communicateswith") or "?"   # fallback for None / "unknown"

    except Exception as e:
        print(f"Error querying MongoDB: {e}")
        # Return error figure
        fig = go.Figure()
        fig.update_layout(
            title="Database Query Error",
            annotations=[dict(
                x=0.5, y=0.5, text=f"Error: {str(e)}",
                showarrow=False, font=dict(size=16), xref="paper", yref="paper"
            )]
        )
        return fig
    net_merged = {}
    current_iteration= None
    net_unique_origin=[]
    for a in raw_net:
        
        it = a["iteration"]
        # check if the alert origin already exist for the current iteration
        if it != current_iteration:
            net_unique_origin = []
            current_iteration = it
        
        elif a.get("alertorigin") not in net_unique_origin:
            key = (it,
                a["IP"],
                a.get("dest"),
                a.get("alertorigin"),
                a.get("direction"))
            entry = net_merged.setdefault(key, {**a, "types": []})
            entry["types"] = sorted(set(entry["types"] + a.get("types", [])))
            net_unique_origin.append(a.get("alertorigin"))
    net_by_iter = defaultdict(list)
    for a in net_merged.values():
        net_by_iter[a["iteration"]].append(a)

    # 2) Fetch & merge physical anomalies (only integer iterations)
    try:
        raw_phys = list(alerts.find({
            "tank":      {"$exists": True},
        }))
    except Exception as e:
        print(f"Error querying physical anomalies: {e}")
        raw_phys = []
    phys_merged = {}
    for p in raw_phys:
        it = p["iteration"]
        key = (it, p["tank"])
        entry = phys_merged.setdefault(key, {**p, "types": []})
        entry["types"] = sorted(set(entry["types"] + p.get("types", [])))
    phys_by_iter = defaultdict(list)
    for p in phys_merged.values():
        phys_by_iter[p["iteration"]].append(p)

    # 3) All iterations
    all_iters = sorted(set(net_by_iter) | set(phys_by_iter))

    # layout constants
    small_gap    = 3
    large_gap    = 12
    LINE_H       = 19    # per line of text
    PADDING      = 24     # vertical padding inside box

    BOX_WIDTH    = 60
    net_spacing  = 60
    phys_spacing = 60
    left_margin  = 10

    # compute number of lines per row
    def count_lines(types):
        return 2 + len(types)  # iteration + tank + each type

    row_lines = {}
    for it in all_iters:
        counts = []
        # network
        for a in net_by_iter.get(it, []):
            counts.append(count_lines(a["types"]))
        # matched physical
        if it in net_by_iter and net_by_iter[it]:
            for p in phys_by_iter.get(it, []):
                counts.append(count_lines(p["types"]))
        # unmatched physical
        # will handle later, but include them too so height fits
        for p in phys_by_iter.get(it, []):
            if it not in net_by_iter or not net_by_iter[it]:
                counts.append(count_lines(p["types"]))
        row_lines[it] = max(counts) if counts else 1

    # compute y positions dynamically
    y_positions = {}
    curr_y, prev_it, prev_h = 0, None, 0
    for it in all_iters:
        block_h = row_lines[it] * LINE_H + PADDING
        if prev_it is not None:
            gap = small_gap if it == prev_it + 1 else large_gap
            curr_y += gap + prev_h
        y_positions[it] = curr_y
        prev_it, prev_h = it, block_h

    shapes, annotations = [], []

    # draw network + matched physical
    for it in all_iters:
        y = y_positions[it]
        block_h = row_lines[it] * LINE_H + PADDING

        # network (red)
        for j, a in enumerate(net_by_iter.get(it, [])):
            x0, x1 = left_margin + j*net_spacing, left_margin + j*net_spacing + BOX_WIDTH

            # Choose arrow character
            direction = a.get("direction", "").upper()
            arrow = ">" if direction == "SEND" else "<" if direction == "RECV" else ">"

            # Enhanced label with clear PLC identifier and log type
            detector_id = a.get('alertorigin', '?')
            log_types = a.get('types', [])
            log_type_str = ', '.join(log_types) if log_types else 'Unknown'
            
            # Make PLC identifier prominent
            plc_label = f"{detector_id}" if detector_id != '?' else "Unknown PLC"
            
            label = (
                f"{it}<br>"
                f"{plc_label}<br>"
            )

            shapes.append(go.layout.Shape(
                type="rect", x0=x0, x1=x1, y0=y, y1=y+block_h,
                line=dict(color="red"), fillcolor="lightcoral", opacity=0.6
            ))
            annotations.append(dict(
                x=(x0+x1)/2, y=y+block_h/2,
                text=label, showarrow=False, font=dict(size=10), align="center"
            ))

        # matched physical (blue) only if network exists
        if it in net_by_iter and net_by_iter[it]:
            for j, p in enumerate(phys_by_iter.get(it, [])):
                x0 = left_margin + len(net_by_iter[it])*net_spacing + j*phys_spacing
                x1 = x0 + BOX_WIDTH
                label = f"{it}<br>{p['tank']}<br>{'<br>'.join(p['types'])}"
                shapes.append(go.layout.Shape(
                    type="rect", x0=x0, x1=x1, y0=y, y1=y+block_h,
                    line=dict(color="blue"), fillcolor="lightblue", opacity=0.6
                ))
                annotations.append(dict(
                    x=(x0+x1)/2, y=y+block_h/2,
                    text=label, showarrow=False, font=dict(size=10), align="center"
                ))

    # unmatched physical only (orange)
    phys_only = sorted(set(phys_by_iter) - set(net_by_iter))
    extra_x = left_margin \
            + max((len(net_by_iter[it]) for it in all_iters), default=0)*net_spacing \
            + max((len(phys_by_iter[it]) for it in all_iters), default=0)*phys_spacing + 50

    for it in phys_only:
        y = y_positions[it]
        block_h = row_lines[it] * LINE_H + PADDING
        for j, p in enumerate(phys_by_iter[it]):
            x0 = extra_x + j*phys_spacing
            x1 = x0 + BOX_WIDTH
            label = f"{it}<br>{p['tank']}<br>{'<br>'.join(p['types'])}"
            shapes.append(go.layout.Shape(
                type="rect", x0=x0, x1=x1, y0=y, y1=y+block_h,
                line=dict(color="orange"), fillcolor="orange", opacity=0.6
            ))
            annotations.append(dict(
                x=(x0+x1)/2, y=y+block_h/2,
                text=label, showarrow=False, font=dict(size=10), align="center"
            ))

    # build figure
    fig = go.Figure()
    fig.update_layout(
        title="Network + Physical Anomalies (Live View)",
        shapes=shapes,
        annotations=annotations,
        xaxis=dict(showticklabels=False),
        yaxis=dict(showticklabels=False),
        margin=dict(l=20, r=20, t=40, b=20),
        height=max(500, curr_y + prev_h + large_gap)
    )

    # autoscale
    max_x = extra_x + max((len(phys_by_iter[it]) for it in phys_only), default=0)*phys_spacing + 100
    max_y = curr_y + prev_h
    fig.add_trace(go.Scatter(
        x=[0, max_x], y=[0, max_y],
        mode="markers", marker=dict(opacity=0),
        showlegend=False, hoverinfo="none"
    ))

     # Save plot to HTML file with timestamp
    try:
        
        filename = f"plot-{session_timestamp}.html"
        filepath = os.path.join(args.output_dir, filename)
        
        # Create output directory if it doesn't exist
        os.makedirs(args.output_dir, exist_ok=True)
        
        # Save the figure as HTML
        fig.write_html(filepath)
        print(f"Plot saved to: {filepath}")
    except Exception as e:
        print(f"Error saving plot: {e}")

    return fig


if __name__ == "__main__":
    try:
        print("Starting Dash application on http://0.0.0.0:8050")
        app.run(host="0.0.0.0", port=8050, debug=False)
    except Exception as e:
        print(f"Error starting Dash application: {e}")
        print("Make sure MongoDB is running and port 8050 is available.")