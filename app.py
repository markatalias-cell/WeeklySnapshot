import dash
from dash import dcc, html, dash_table, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import base64
import io

# ── App init ──────────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    title="S3D ISO Case Closure Report",
    suppress_callback_exceptions=True
)
server = app.server

# ── Colours ───────────────────────────────────────────────────────────────────
BLUE   = '#1F4E79'
BLUE2  = '#2E75B6'
TEAL   = '#1F6B75'
RED    = '#C00000'
AMBER  = '#C55A11'
GREEN  = '#375623'
GREY   = '#595959'
STRIPE = '#EBF3FB'

# ── Helpers ───────────────────────────────────────────────────────────────────
def parse_file(contents):
    _, data = contents.split(',')
    return pd.read_excel(io.BytesIO(base64.b64decode(data)))

def clean(df, date_cols=None):
    df = df[df.iloc[:,0].notna() & ~df.iloc[:,0].astype(str)
            .str.contains('Copyright|Confidential', na=False)].copy()
    for col in (date_cols or []):
        if col in df.columns:
            df[col] = pd.to_datetime(
                df[col].astype(str).str.replace(',','').str.strip(),
                format='%d/%m/%Y %H:%M', errors='coerce')
    return df

def safe_float(x):
    """Convert any numeric to plain Python float, return 0.0 if NaN."""
    try:
        v = float(x)
        return 0.0 if np.isnan(v) else round(v, 1)
    except Exception:
        return 0.0

def ucl(s):
    q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
    return round(q3 + 1.5 * (q3 - q1), 1)

def fmt(x, suffix='d'):
    v = safe_float(x)
    return f"{v:.1f}{suffix}" if v != 0.0 else '—'

def safe_str(x):
    if pd.isna(x): return '—'
    try:
        v = float(x)
        if np.isnan(v): return '—'
        if v == int(v): return str(int(v))
        return str(v)
    except Exception:
        return str(x)

# ── Layout ────────────────────────────────────────────────────────────────────
app.layout = html.Div([
    dcc.Store(id='store-ready'),

    # Header
    html.Div([
        html.H1('S3D ISO Case Closure Report',
                style={'color':'white','margin':0,'fontSize':'1.5rem','fontWeight':700}),
        html.P('Upload the three Salesforce exports to generate the interactive weekly dashboard.',
               style={'color':'#BDD7EE','margin':'4px 0 0 0','fontSize':'0.85rem'}),
    ], style={'background':BLUE,'padding':'18px 28px'}),

    # Upload section
    html.Div([
        dbc.Row([
            dbc.Col([
                html.Label('File 1 — All Parent Cases (12m)',
                           style={'fontWeight':600,'color':BLUE,'fontSize':'0.85rem'}),
                dcc.Upload(id='u1',
                    children=html.Div(['📁 Drag or click to upload']),
                    style={'width':'100%','height':'55px','lineHeight':'55px','borderWidth':'2px',
                           'borderStyle':'dashed','borderRadius':'6px','textAlign':'center',
                           'borderColor':BLUE2,'background':'#F0F7FF','cursor':'pointer'},
                    multiple=False),
                html.Div(id='s1', style={'fontSize':'0.75rem','marginTop':'3px','color':GREEN}),
            ], md=4),
            dbc.Col([
                html.Label('File 2 — Helper Cases (12m)',
                           style={'fontWeight':600,'color':BLUE,'fontSize':'0.85rem'}),
                dcc.Upload(id='u2',
                    children=html.Div(['📁 Drag or click to upload']),
                    style={'width':'100%','height':'55px','lineHeight':'55px','borderWidth':'2px',
                           'borderStyle':'dashed','borderRadius':'6px','textAlign':'center',
                           'borderColor':BLUE2,'background':'#F0F7FF','cursor':'pointer'},
                    multiple=False),
                html.Div(id='s2', style={'fontSize':'0.75rem','marginTop':'3px','color':GREEN}),
            ], md=4),
            dbc.Col([
                html.Label("File 3 — This Week's Cases",
                           style={'fontWeight':600,'color':BLUE,'fontSize':'0.85rem'}),
                dcc.Upload(id='u3',
                    children=html.Div(['📁 Drag or click to upload']),
                    style={'width':'100%','height':'55px','lineHeight':'55px','borderWidth':'2px',
                           'borderStyle':'dashed','borderRadius':'6px','textAlign':'center',
                           'borderColor':BLUE2,'background':'#F0F7FF','cursor':'pointer'},
                    multiple=False),
                html.Div(id='s3', style={'fontSize':'0.75rem','marginTop':'3px','color':GREEN}),
            ], md=4),
        ], className='g-3'),
        dbc.Row([
            dbc.Col(width=3),
            dbc.Col([
                dbc.Button('Generate Report', id='btn-gen', color='primary', size='lg',
                           disabled=True, className='w-100 mt-3',
                           style={'background':BLUE,'border':'none','fontWeight':600}),
                html.Div(id='gen-status',
                         style={'marginTop':'8px','fontSize':'0.85rem','textAlign':'center'}),
            ], md=6),
            dbc.Col(width=3),
        ]),
    ], style={'padding':'20px 28px','background':'#F8FBFF',
              'borderBottom':'1px solid #D6E8F7'}),

    # Dashboard area
    html.Div(id='dashboard', style={'display':'none','padding':'20px 28px'}),

], style={'fontFamily':'Arial, sans-serif','minHeight':'100vh','background':'#F4F8FB'})


# ── Upload status ─────────────────────────────────────────────────────────────
@app.callback(Output('s1','children'), Input('u1','filename'))
def _s1(fn): return f'✅ {fn}' if fn else ''

@app.callback(Output('s2','children'), Input('u2','filename'))
def _s2(fn): return f'✅ {fn}' if fn else ''

@app.callback(Output('s3','children'), Input('u3','filename'))
def _s3(fn): return f'✅ {fn}' if fn else ''

@app.callback(Output('btn-gen','disabled'),
              Input('u1','contents'), Input('u2','contents'), Input('u3','contents'))
def _enable(f1, f2, f3): return not (f1 and f2 and f3)


# ── Main generate callback ────────────────────────────────────────────────────
@app.callback(
    Output('dashboard','children'),
    Output('dashboard','style'),
    Output('gen-status','children'),
    Input('btn-gen','n_clicks'),
    State('u1','contents'), State('u2','contents'), State('u3','contents'),
    prevent_initial_call=True)
def generate(_, f1, f2, f3):
    SHOW  = {'display':'block','padding':'20px 28px'}
    HIDE  = {'display':'none','padding':'20px 28px'}
    DC    = ['Date/Time Opened','Date/Time Closed',
             'Case : Parent Case : Date/Time Opened',
             'Case : Parent Case : Date/Time Closed']

    # ── Process data ──────────────────────────────────────────────────────────
    try:
        df1 = clean(parse_file(f1), ['Date/Time Opened','Date/Time Closed'])
        df2 = clean(parse_file(f2), DC)
        df3 = clean(parse_file(f3), DC)
    except Exception as e:
        return html.Pre(f'File error: {e}'), SHOW, '❌ File error'

    try:
        METRICS = ['Parent_TTR_Days','Helper_TTR_Days','Time_to_File','HP_Gap']
        ML      = {'Parent_TTR_Days':'Parent Age','Helper_TTR_Days':'Helper Age',
                   'Time_to_File':'Time to File Helper','HP_Gap':'Helper→Parent Gap'}

        df1['Has_Helper']      = df1['Has Helper Case'].fillna(0).astype(int)
        df1['Parent_TTR_Days'] = df1['Time to Resolve'] / 24
        df1['Month']           = df1['Date/Time Closed'].dt.to_period('M').astype(str)

        df2['Helper_TTR_Days'] = df2['Time to Resolve'] / 24
        df2['Parent_TTR_Days'] = df2['Parent Case: Time to Resolve'] / 24
        df2['Time_to_File']    = (df2['Date/Time Opened'] -
                                   df2['Case : Parent Case : Date/Time Opened']).dt.total_seconds()/86400
        df2['HP_Gap']          = (df2['Case : Parent Case : Date/Time Closed'] -
                                   df2['Date/Time Closed']).dt.total_seconds()/86400
        df2['Month']           = df2['Date/Time Closed'].dt.to_period('M').astype(str)

        df3['Helper_TTR_Days'] = df3['Time to Resolve'] / 24
        df3['Parent_TTR_Days'] = df3['Parent Case: Time to Resolve'] / 24
        df3['Time_to_File']    = (df3['Date/Time Opened'] -
                                   df3['Case : Parent Case : Date/Time Opened']).dt.total_seconds()/86400
        df3['HP_Gap']          = (df3['Case : Parent Case : Date/Time Closed'] -
                                   df3['Date/Time Closed']).dt.total_seconds()/86400

        # UCLs — plain Python floats
        U = {m: ucl(df1['Parent_TTR_Days']) if m == 'Parent_TTR_Days' else ucl(df2[m])
             for m in METRICS}
        M = {m: safe_float(df2[m].median()) for m in METRICS}
        A = {m: safe_float(df2[m].mean())   for m in METRICS}

        # Outlier flags
        df3['Outlier Flags'] = ''
        for m in METRICS:
            src = df1['Parent_TTR_Days'] if m == 'Parent_TTR_Days' else df2[m]
            q1h, q3h = float(src.quantile(0.25)), float(src.quantile(0.75))
            lo, hi   = q1h - 1.5*(q3h-q1h), q3h + 1.5*(q3h-q1h)
            mask = (df3[m] < lo) | (df3[m] > hi)
            df3.loc[mask, 'Outlier Flags'] = df3.loc[mask, 'Outlier Flags'].apply(
                lambda x: (x + ', ' if x else '') + ML[m])
        df3['Is Outlier'] = df3['Outlier Flags'] != ''

        # Parent cases this week
        wk_lo = df3['Date/Time Closed'].min().replace(hour=0,  minute=0)
        wk_hi = df3['Date/Time Closed'].max().replace(hour=23, minute=59)
        df1['_k'] = df1['Case Number'].astype(str).str.replace(r'\.0','',regex=True).str.zfill(8)
        df2['_k'] = df2['Parent Case'].apply(
            lambda x: str(int(float(x))).zfill(8) if pd.notna(x) else '')
        hagg = df2.groupby('_k').agg(
            HC=('Case Number', lambda x: ', '.join(
                x.astype(str).str.replace(r'\.0','',regex=True).str.zfill(8))),
            HO=('Case Owner',  lambda x: ', '.join(x.dropna().unique())),
            HT=('Helper_TTR_Days', 'mean'),
            TF=('Time_to_File',    'mean'),
            HG=('HP_Gap',          'mean'),
        ).reset_index()
        pw = df1[(df1['Date/Time Closed'] >= wk_lo) &
                 (df1['Date/Time Closed'] <= wk_hi)].copy()
        pw['_k']       = pw['Case Number'].astype(str).str.replace(r'\.0','',regex=True).str.zfill(8)
        pw             = pw.merge(hagg, on='_k', how='left')
        pw['Is_Out']   = pw['Parent_TTR_Days'] > U['Parent_TTR_Days']
        pw_h  = pw[pw['Has_Helper']==1].sort_values('Parent_TTR_Days', ascending=False)
        pw_no = pw[pw['Has_Helper']==0].sort_values('Parent_TTR_Days', ascending=False)

        BL = (f"{df2['Date/Time Closed'].min().strftime('%b %Y')}–"
              f"{df2['Date/Time Closed'].max().strftime('%b %Y')}")
        wk_min = df3['Date/Time Closed'].min().strftime('%d %b')
        wk_max = df3['Date/Time Closed'].max().strftime('%d %b %Y')
        n_out  = int(df3['Is Outlier'].sum())

    except Exception as e:
        import traceback
        return html.Div([
            html.H4('❌ Data processing error', style={'color':RED}),
            html.Pre(str(e), style={'background':'#fff0f0','padding':'12px','fontSize':'0.8rem',
                                    'borderRadius':'4px','whiteSpace':'pre-wrap'}),
            html.Pre(traceback.format_exc(), style={'fontSize':'0.7rem','color':GREY}),
        ]), SHOW, '❌ Error'

    # ── Build dashboard ───────────────────────────────────────────────────────
    try:
        # KPI strip
        def kpi(label, val, color):
            return dbc.Col(html.Div([
                html.P(label, style={'fontSize':'0.7rem','color':GREY,'margin':0,
                                     'fontWeight':600,'textTransform':'uppercase'}),
                html.H4(val,  style={'color':color,'margin':'2px 0 0 0','fontWeight':700}),
            ], style={'background':'white','borderLeft':f'4px solid {color}',
                      'borderRadius':'6px','padding':'10px 14px',
                      'boxShadow':'0 1px 4px rgba(0,0,0,0.07)'}))

        kpis = dbc.Row([
            kpi('Cases Closed',     str(len(df3)),                            BLUE),
            kpi('Med Parent Age',   fmt(df3['Parent_TTR_Days'].median()),      TEAL),
            kpi('Med Helper Age',   fmt(df3['Helper_TTR_Days'].median()),      TEAL),
            kpi('Med Time to File', fmt(df3['Time_to_File'].median()),         AMBER),
            kpi('Parent UCL',       f"{U['Parent_TTR_Days']}d",               RED),
            kpi('Outliers',         str(n_out),                               RED if n_out > 0 else GREEN),
            kpi('Parent Cases',     str(len(pw)),                             BLUE2),
        ], className='g-2 mb-3')

        # Benchmark comparison table
        bench_data = []
        for m in METRICS:
            wa = safe_float(df3[m].mean()); wm = safe_float(df3[m].median())
            da = round(wa - A[m], 1);       dm = round(wm - M[m], 1)
            breach = wm > U[m]; above = dm > 0 and not breach
            status = '🔴 Above UCL' if breach else ('🟠 Above median' if above else '🟢 At or below')
            bench_data.append({
                'Metric': ML[m],
                'This Week Avg': f"{wa:.1f}d",
                'This Week Med': f"{wm:.1f}d",
                '12m Avg': f"{A[m]:.1f}d",
                '12m Med': f"{M[m]:.1f}d",
                'UCL':     f"{U[m]:.1f}d",
                'vs Med':  f"+{dm:.1f}d" if dm > 0 else f"{dm:.1f}d",
                'Status':  status,
            })

        bench_tbl = dash_table.DataTable(
            data=bench_data,
            columns=[{'name':c,'id':c} for c in bench_data[0].keys()],
            style_table={'overflowX':'auto'},
            style_header={'backgroundColor':BLUE,'color':'white','fontWeight':'bold',
                          'textAlign':'center','fontSize':'12px','padding':'8px'},
            style_cell={'textAlign':'center','fontSize':'12px','padding':'7px 10px',
                        'border':'1px solid #D6E8F7'},
            style_cell_conditional=[{'if':{'column_id':'Metric'},'textAlign':'left','fontWeight':'bold'}],
            style_data_conditional=[
                {'if':{'filter_query':'{Status} contains "🔴"'},'backgroundColor':'#FFCCCC'},
                {'if':{'filter_query':'{Status} contains "🟠"'},'backgroundColor':'#FFF2CC'},
                {'if':{'filter_query':'{Status} contains "🟢"'},'backgroundColor':'#E2EFDA'},
            ])

        # Metric bar chart
        bar_fig = go.Figure()
        labels = [ML[m] for m in METRICS]
        bar_fig.add_trace(go.Bar(name='This Week Median', x=labels,
            y=[safe_float(df3[m].median()) for m in METRICS],
            marker_color=TEAL, text=[fmt(df3[m].median()) for m in METRICS],
            textposition='outside'))
        bar_fig.add_trace(go.Bar(name='12m Median', x=labels,
            y=[M[m] for m in METRICS], marker_color='#888780',
            text=[f"{M[m]:.1f}d" for m in METRICS], textposition='outside'))
        bar_fig.add_trace(go.Bar(name='UCL', x=labels,
            y=[U[m] for m in METRICS], marker_color=RED,
            text=[f"{U[m]:.1f}d" for m in METRICS], textposition='outside'))
        bar_fig.update_layout(
            barmode='group', title='This Week vs 12m Median & UCL',
            plot_bgcolor='white', paper_bgcolor='white', height=300,
            legend=dict(orientation='h', y=-0.25),
            margin=dict(t=40,b=70,l=40,r=20), font=dict(family='Arial',size=11))
        bar_fig.update_yaxes(title='Days', gridcolor='#EEE')

        # Case detail table
        def prep_row(row):
            return {
                'Helper Case':   safe_str(row['Case Number']),
                'Parent Case':   safe_str(row['Parent Case']),
                'Case Owner':    str(row.get('Case Owner', '—')),
                'Parent Owner':  str(row.get('Case : Parent Case : Owner FullName', '—')),
                'Closed':        row['Date/Time Closed'].strftime('%d/%m/%Y %H:%M')
                                 if pd.notna(row['Date/Time Closed']) else '—',
                'Parent Age':    fmt(row['Parent_TTR_Days']),
                'Helper Age':    fmt(row['Helper_TTR_Days']),
                'Time to File':  fmt(row['Time_to_File']),
                'H→P Gap':       fmt(row['HP_Gap']),
                'Status':        str(row.get('Parent Case: Status', '—')),
                'Dev Item':      safe_str(row.get('Parent Case: Dev Item Number', None))
                                 if pd.notna(row.get('Parent Case: Dev Item Number', None)) else '—',
                'Outlier':       str(row['Outlier Flags']) if row['Outlier Flags'] else '—',
            }

        case_data = [prep_row(row) for _, row in
                     df3.sort_values('Date/Time Closed').iterrows()]
        case_cols = list(case_data[0].keys()) if case_data else []

        case_tbl = dash_table.DataTable(
            data=case_data,
            columns=[{'name':c,'id':c} for c in case_cols],
            style_table={'overflowX':'auto'},
            style_header={'backgroundColor':BLUE,'color':'white','fontWeight':'bold',
                          'textAlign':'center','fontSize':'11px','padding':'7px'},
            style_cell={'textAlign':'center','fontSize':'11px','padding':'6px 8px',
                        'border':'1px solid #D6E8F7'},
            style_cell_conditional=[
                {'if':{'column_id':c},'textAlign':'left'}
                for c in ['Case Owner','Parent Owner','Outlier']],
            style_data_conditional=[
                {'if':{'filter_query':'{Outlier} != "—"'},
                 'backgroundColor':'#FFCCCC','fontWeight':'bold'},
                {'if':{'row_index':'odd'},'backgroundColor':STRIPE},
            ],
            filter_action='native', sort_action='native', page_size=20)

        # Monthly trend chart
        try:
            mo = df1.groupby('Month').agg(
                No_H=('Has_Helper', lambda x:(x==0).sum()),
                Wi_H=('Has_Helper', lambda x:(x==1).sum()),
                Avg_No=('Parent_TTR_Days','mean'),
                Avg_Wi=('Parent_TTR_Days',lambda x: x[df1.loc[x.index,'Has_Helper']==1].mean()),
            ).reset_index().sort_values('Month')

            trend_fig = go.Figure()
            trend_fig.add_trace(go.Bar(name='No Helper', x=mo['Month'].tolist(),
                y=mo['No_H'].tolist(), marker_color='#B8CCE4'))
            trend_fig.add_trace(go.Bar(name='With Helper', x=mo['Month'].tolist(),
                y=mo['Wi_H'].tolist(), marker_color=BLUE2))
            trend_fig.add_trace(go.Scatter(name='Avg TTR No Helper', x=mo['Month'].tolist(),
                y=[safe_float(v) for v in mo['Avg_No'].tolist()],
                yaxis='y2', mode='lines+markers', line=dict(color=BLUE, width=2)))
            trend_fig.update_layout(
                barmode='stack', title='Monthly Volume & Avg Resolution Time',
                plot_bgcolor='white', paper_bgcolor='white', height=360,
                yaxis=dict(title='Case Count', gridcolor='#EEE'),
                yaxis2=dict(title='Avg TTR (Days)', overlaying='y', side='right'),
                legend=dict(orientation='h', y=-0.3),
                margin=dict(t=40,b=90,l=50,r=50), font=dict(family='Arial',size=11))
        except Exception:
            trend_fig = go.Figure()
            trend_fig.add_annotation(text='Chart unavailable', showarrow=False)

        # Ownership chart
        try:
            d2o = df2[df2['Month'] >= '2026-01'].copy()
            own = d2o.groupby(['Month','Case Owner']).size().reset_index(name='N')
            pvt = own.pivot(index='Month', columns='Case Owner', values='N').fillna(0)
            OWN_COLORS = ['#1F4E79','#ED7D31','#70AD47','#FFC000',
                          '#4472C4','#FF0000','#A9D18E','#BF9000','#833C00']
            own_fig = go.Figure()
            for i, owner in enumerate(pvt.columns):
                own_fig.add_trace(go.Scatter(
                    name=str(owner), x=pvt.index.tolist(),
                    y=[safe_float(v) for v in pvt[owner].tolist()],
                    mode='lines+markers',
                    line=dict(color=OWN_COLORS[i % len(OWN_COLORS)], width=2),
                    marker=dict(size=6)))
            own_fig.add_vline(x='2026-05', line_dash='dash', line_color=AMBER,
                              line_width=2, annotation_text='★ Initiative',
                              annotation_position='top right',
                              annotation_font_color=AMBER)
            own_fig.update_layout(
                title='Helper Case Ownership (★ = Initiative 18 May 2026)',
                plot_bgcolor='white', paper_bgcolor='white', height=360,
                yaxis=dict(title='Cases Closed', gridcolor='#EEE'),
                legend=dict(orientation='h', y=-0.35, font=dict(size=10)),
                margin=dict(t=40,b=100,l=50,r=20), font=dict(family='Arial',size=11))
        except Exception:
            own_fig = go.Figure()
            own_fig.add_annotation(text='Chart unavailable', showarrow=False)

        # Parent cases tables
        def make_parent_tbl(df_in, has_helper):
            if len(df_in) == 0:
                return html.P('No cases.', style={'color':GREY,'fontStyle':'italic'})
            rows = []
            for _, r in df_in.iterrows():
                row = {
                    'Parent Case': safe_str(r['Case Number']),
                    'Owner':       str(r.get('Case Owner','—')),
                    'Account':     str(r.get('Account Name','—'))
                                   if pd.notna(r.get('Account Name')) else '—',
                    'Closed':      r['Date/Time Closed'].strftime('%d/%m/%Y')
                                   if pd.notna(r['Date/Time Closed']) else '—',
                    'Parent TTR':  fmt(r['Parent_TTR_Days']),
                    'Outlier':     '🔴' if r['Is_Out'] else '—',
                }
                if has_helper:
                    row['Helper Case(s)'] = str(r['HC']) if pd.notna(r.get('HC')) else '—'
                    row['Helper Owner']   = str(r['HO']) if pd.notna(r.get('HO')) else '—'
                    row['Avg Helper TTR'] = fmt(r.get('HT'))
                    row['Time to File']   = fmt(r.get('TF'))
                rows.append(row)
            cols = list(rows[0].keys())
            hc   = BLUE2 if has_helper else '#889DB5'
            return dash_table.DataTable(
                data=rows, columns=[{'name':c,'id':c} for c in cols],
                style_table={'overflowX':'auto'},
                style_header={'backgroundColor':hc,'color':'white','fontWeight':'bold',
                              'fontSize':'11px','textAlign':'center','padding':'7px'},
                style_cell={'textAlign':'center','fontSize':'11px',
                            'padding':'6px 8px','border':'1px solid #D6E8F7'},
                style_cell_conditional=[
                    {'if':{'column_id':c},'textAlign':'left'}
                    for c in ['Owner','Account']],
                style_data_conditional=[
                    {'if':{'filter_query':'{Outlier} = "🔴"'},
                     'backgroundColor':'#FFCCCC','fontWeight':'bold'},
                    {'if':{'row_index':'odd'},
                     'backgroundColor':'#EAF4FF' if has_helper else STRIPE},
                ],
                sort_action='native', page_size=25)

        # ── Assemble dashboard ────────────────────────────────────────────────
        title = html.Div([
            html.H3(f'7-Day Case Closure Report — {wk_min} to {wk_max}',
                    style={'color':BLUE,'margin':0,'fontWeight':700}),
            html.P(f'{len(df3)} helper cases · {len(pw)} parent cases · '
                   f'Benchmarks: {len(df2)} cases from {BL} · '
                   f'Parent UCL = {U["Parent_TTR_Days"]}d',
                   style={'color':GREY,'margin':'4px 0 0 0','fontSize':'0.85rem'}),
        ], style={'marginBottom':'16px'})

        dashboard = html.Div([
            title, kpis,
            dbc.Tabs([
                dbc.Tab(label='📊 Weekly Snapshot', children=html.Div([
                    html.H5('Metric Comparison',
                            style={'color':BLUE,'fontWeight':700,'margin':'16px 0 10px'}),
                    bench_tbl,
                    html.Br(),
                    dcc.Graph(figure=bar_fig, config={'displayModeBar':False}),
                    html.H5('Case Detail — This Week',
                            style={'color':BLUE,'fontWeight':700,'margin':'16px 0 8px'}),
                    html.P('Use column headers to sort · Use filter row (▽) to filter',
                           style={'color':GREY,'fontSize':'0.8rem','fontStyle':'italic','marginBottom':'8px'}),
                    case_tbl,
                    html.P(f"Parent UCL={U['Parent_TTR_Days']}d · "
                           f"Helper UCL={U['Helper_TTR_Days']}d · "
                           f"Time to File UCL={U['Time_to_File']}d",
                           style={'fontSize':'0.75rem','color':GREY,'fontStyle':'italic','marginTop':'8px'}),
                ], style={'padding':'4px 0'})),

                dbc.Tab(label='👨‍👩‍👧 Parent Cases', children=html.Div([
                    dbc.Row([
                        dbc.Col(html.Div([
                            html.P('With Helper', style={'color':GREY,'margin':0,'fontWeight':600,'fontSize':'0.75rem'}),
                            html.H4(str(len(pw_h)), style={'color':BLUE2,'margin':0,'fontWeight':700}),
                            html.P(f"Avg {safe_float(pw_h['Parent_TTR_Days'].mean()):.1f}d · Med {safe_float(pw_h['Parent_TTR_Days'].median()):.1f}d"
                                   if len(pw_h) > 0 else 'No cases',
                                   style={'color':GREY,'margin':0,'fontSize':'0.8rem'}),
                        ], style={'background':'white','borderLeft':f'4px solid {BLUE2}',
                                  'borderRadius':'6px','padding':'10px 14px',
                                  'boxShadow':'0 1px 4px rgba(0,0,0,0.07)'})),
                        dbc.Col(html.Div([
                            html.P('Without Helper', style={'color':GREY,'margin':0,'fontWeight':600,'fontSize':'0.75rem'}),
                            html.H4(str(len(pw_no)), style={'color':'#889DB5','margin':0,'fontWeight':700}),
                            html.P(f"Avg {safe_float(pw_no['Parent_TTR_Days'].mean()):.1f}d · Med {safe_float(pw_no['Parent_TTR_Days'].median()):.1f}d"
                                   if len(pw_no) > 0 else 'No cases',
                                   style={'color':GREY,'margin':0,'fontSize':'0.8rem'}),
                        ], style={'background':'white','borderLeft':'4px solid #889DB5',
                                  'borderRadius':'6px','padding':'10px 14px',
                                  'boxShadow':'0 1px 4px rgba(0,0,0,0.07)'})),
                        dbc.Col(html.Div([
                            html.P('Outliers (>UCL)', style={'color':GREY,'margin':0,'fontWeight':600,'fontSize':'0.75rem'}),
                            html.H4(str(int(pw['Is_Out'].sum())),
                                    style={'color':RED if int(pw['Is_Out'].sum()) > 0 else GREEN,
                                           'margin':0,'fontWeight':700}),
                            html.P(f"UCL = {U['Parent_TTR_Days']}d",
                                   style={'color':GREY,'margin':0,'fontSize':'0.8rem'}),
                        ], style={'background':'white','borderLeft':f'4px solid {RED}',
                                  'borderRadius':'6px','padding':'10px 14px',
                                  'boxShadow':'0 1px 4px rgba(0,0,0,0.07)'})),
                    ], className='g-3 mb-3 mt-2'),
                    html.Div(f'Parent Cases WITH Helper ({len(pw_h)})',
                             style={'background':BLUE2,'color':'white','padding':'8px 14px',
                                    'borderRadius':'5px','fontWeight':600,'marginBottom':'8px'}),
                    make_parent_tbl(pw_h,  True),
                    html.Div(f'Parent Cases WITHOUT Helper ({len(pw_no)})',
                             style={'background':'#889DB5','color':'white','padding':'8px 14px',
                                    'borderRadius':'5px','fontWeight':600,
                                    'marginTop':'16px','marginBottom':'8px'}),
                    make_parent_tbl(pw_no, False),
                ], style={'padding':'4px 0'})),

                dbc.Tab(label='📈 12 Month Trend', children=html.Div([
                    dcc.Graph(figure=trend_fig, config={'displayModeBar':True}),
                ], style={'padding':'4px 0'})),

                dbc.Tab(label='👥 Ownership', children=html.Div([
                    dcc.Graph(figure=own_fig, config={'displayModeBar':True}),
                    html.P('Click legend entries to show/hide engineers. '
                           'Double-click to isolate one.',
                           style={'color':GREY,'fontSize':'0.8rem',
                                  'fontStyle':'italic','textAlign':'center'}),
                ], style={'padding':'4px 0'})),

                dbc.Tab(label='📋 Benchmarks', children=html.Div([
                    html.H5('IQR Benchmark Reference',
                            style={'color':BLUE,'fontWeight':700,'marginTop':'16px'}),
                    html.P(f"Parent UCL from all {len(df1):,} parent cases · "
                           f"Other UCLs from {len(df2)} helper cases · UCL = Q3 + 1.5×IQR",
                           style={'color':GREY,'fontSize':'0.85rem'}),
                    dash_table.DataTable(
                        data=[{'Metric':ML[m],'UCL':f"{U[m]:.1f}d",
                               '12m Median':f"{M[m]:.1f}d",'12m Avg':f"{A[m]:.1f}d"}
                              for m in METRICS],
                        columns=[{'name':c,'id':c}
                                 for c in ['Metric','UCL','12m Median','12m Avg']],
                        style_header={'backgroundColor':BLUE,'color':'white',
                                      'fontWeight':'bold','textAlign':'center'},
                        style_cell={'textAlign':'center','fontSize':'13px',
                                    'padding':'9px 14px','border':'1px solid #D6E8F7'},
                        style_cell_conditional=[
                            {'if':{'column_id':'Metric'},'textAlign':'left','fontWeight':'bold'}],
                        style_data_conditional=[
                            {'if':{'column_id':'UCL'},'backgroundColor':'#FFF2CC',
                             'fontWeight':'bold','color':RED},
                            {'if':{'row_index':'odd'},'backgroundColor':STRIPE},
                        ]),
                ], style={'padding':'4px 0'})),
            ], style={'marginTop':'4px'}),
        ])

    except Exception as e:
        import traceback
        return html.Div([
            html.H4('❌ Dashboard build error', style={'color':RED}),
            html.Pre(str(e), style={'background':'#fff0f0','padding':'12px',
                                    'fontSize':'0.8rem','borderRadius':'4px',
                                    'whiteSpace':'pre-wrap'}),
            html.Pre(traceback.format_exc(), style={'fontSize':'0.7rem','color':GREY}),
        ]), SHOW, '❌ Error'

    return dashboard, SHOW, html.Span('✅ Report generated', style={'color':GREEN})


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=8050)
