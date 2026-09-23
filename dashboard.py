"""
CFC Partner Logo Exposure Dashboard (Streamlit) — per-partner impact view.

Loads detections.csv (from detect_and_export.py) and shows the exposure impact
for ONE selected partner at a time.

Setup:  pip install streamlit pandas plotly
Run:    streamlit run dashboard.py
"""
import os
import glob
import pandas as pd
import plotly.express as px
import streamlit as st

# ---------------- Config ----------------
DATA_PATH = '/Users/pranav/Downloads/CFC'   # a detections.csv file, OR a folder with several
SECONDS_PER_FRAME = 1.0                       # 1 fps extraction -> 1 second per frame

st.set_page_config(page_title='CFC Logo Exposure', layout='wide')


@st.cache_data
def load_data(path):
    if os.path.isdir(path):
        files = glob.glob(os.path.join(path, '**', 'detections*.csv'), recursive=True)
    else:
        files = [path]
    if not files:
        return pd.DataFrame()
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df['frame_key'] = df['match'].astype(str) + '|' + df['quarter'].astype(str) + '|' + df['frame_index'].astype(str)
    return df


df = load_data(DATA_PATH)

st.title('Collingwood FC — Partner Exposure Impact')
st.caption('Broadcast footage · 1 frame/second · exposure analytics per partner')

if df.empty:
    st.error(f'No detections CSV found at: {DATA_PATH}')
    st.stop()

# ---------------- Selection ----------------
st.sidebar.header('Select')
partner = st.sidebar.selectbox('Partner', sorted(df['partner'].unique()))
matches = sorted(df['match'].unique())
quarters = sorted(df['quarter'].unique())
sel_match = st.sidebar.multiselect('Match', matches, default=matches)
sel_qtr = st.sidebar.multiselect('Quarter', quarters, default=quarters)
min_conf = st.sidebar.slider('Min confidence', 0.0, 1.0, 0.30, 0.05)

# full footage (all partners) after match/quarter/confidence filter -> for the % denominator
scope = df[df['match'].isin(sel_match) & df['quarter'].isin(sel_qtr) & (df['confidence'] >= min_conf)]
total_frames = scope.groupby(['match', 'quarter'])['frame_index'].max().add(1).sum() if not scope.empty else 0
total_seconds = total_frames * SECONDS_PER_FRAME

# this partner only
p = scope[scope['partner'] == partner].copy()

st.header(f'{partner}')

if p.empty:
    st.warning(f'No {partner} detections in the current selection.')
    st.stop()

# ---------------- Headline metrics for this partner ----------------
exp_frames = p['frame_key'].nunique()
exp_seconds = exp_frames * SECONDS_PER_FRAME
pct_footage = (exp_seconds / total_seconds * 100) if total_seconds else 0
avg_cov = p['coverage_pct'].mean()
peak_cov = p['coverage_pct'].max()
avg_instances = len(p) / exp_frames   # average simultaneous logos when on screen

mm, ss = divmod(int(exp_seconds), 60)
c1, c2, c3, c4 = st.columns(4)
c1.metric('Time on screen', f'{mm}m {ss}s')
c2.metric('% of footage', f'{pct_footage:.1f}%')
c3.metric('Peak screen coverage', f'{peak_cov:.2f}%')
c4.metric('Avg logos on screen at once', f'{avg_instances:.1f}')

st.divider()

# ---------------- Exposure by quarter (this partner) ----------------
st.subheader(f'{partner} — exposure by quarter')
per_q = (p.groupby('quarter')['frame_key'].nunique() * SECONDS_PER_FRAME).reset_index()
per_q.columns = ['quarter', 'exposure_seconds']
fig = px.bar(per_q, x='quarter', y='exposure_seconds', text='exposure_seconds',
             labels={'exposure_seconds': 'seconds on screen'})
fig.update_layout(height=340)
st.plotly_chart(fig, use_container_width=True)

# ---------------- Coverage over time across the WHOLE round ----------------
# Each quarter's timestamps restart at 0, so build a continuous round timeline by
# offsetting each quarter to start where the previous one ended (Q1 -> Q2 -> Q3 -> Q4).
st.subheader(f'{partner} — presence across the round')
st.caption('Each bar is a second the logo is on screen (bar height = % of screen). '
           'Gaps = the logo is NOT on screen. This shows whether it appears continuously or in bursts.')

qlen = ((scope.groupby(['match', 'quarter'])['frame_index'].max() + 1) * SECONDS_PER_FRAME)
qlen = qlen.reset_index(name='length_sec').sort_values(['match', 'quarter']).reset_index(drop=True)
qlen['offset'] = qlen['length_sec'].cumsum().shift(fill_value=0)
offset_map = {(r['match'], r['quarter']): r['offset'] for _, r in qlen.iterrows()}

p['global_time'] = [offset_map[(m, q)] + t for m, q, t in
                    zip(p['match'], p['quarter'], p['timestamp_sec'])]

# one value per second (max coverage that second); keep frame info for the hover tooltip
tl = p.groupby('global_time').agg(
    coverage_pct=('coverage_pct', 'max'),
    frame_index=('frame_index', 'first'),
    quarter=('quarter', 'first'),
    timestamp_sec=('timestamp_sec', 'first'),
).reset_index()

fig = px.bar(tl, x='global_time', y='coverage_pct',
             labels={'global_time': 'time across round (s)', 'coverage_pct': '% of screen'},
             custom_data=['frame_index', 'quarter', 'timestamp_sec'])
fig.update_traces(
    marker_line_width=0, width=2,   # thin discrete bars per second
    hovertemplate=('Frame %{customdata[0]}<br>'
                   'Quarter %{customdata[1]}<br>'
                   'Quarter time %{customdata[2]:.0f}s<br>'
                   'Screen %{y:.2f}%<extra></extra>'),
)

# quarter-boundary markers + labels
for _, r in qlen.iterrows():
    fig.add_vline(x=r['offset'], line_dash='dot', line_color='gray', opacity=0.5)
    fig.add_annotation(x=r['offset'], y=1.0, yref='paper', text=str(r['quarter']),
                       showarrow=False, xanchor='left', font=dict(size=11, color='gray'))
fig.update_layout(height=320, bargap=0)
st.plotly_chart(fig, use_container_width=True)

# ---------------- Position on screen (this partner) ----------------
st.subheader(f'{partner} — where it appears on screen')
fig = px.density_heatmap(p, x='center_x', y='center_y', nbinsx=40, nbinsy=24)
fig.update_yaxes(autorange='reversed')   # image coords: y grows downward
fig.update_layout(height=380)
st.plotly_chart(fig, use_container_width=True)

# ---------------- Top moments (biggest appearances) ----------------
st.subheader(f'{partner} — biggest on-screen moments')
top = (p.sort_values('coverage_pct', ascending=False)
        [['match', 'quarter', 'timestamp_sec', 'coverage_pct', 'confidence']]
        .head(10).reset_index(drop=True))
st.dataframe(top, use_container_width=True)

st.download_button(
    f'Download {partner} detections',
    p.to_csv(index=False),
    f'{partner}_detections.csv', 'text/csv'
)