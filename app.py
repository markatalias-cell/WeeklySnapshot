import dash
from dash import dcc, html, dash_table, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
import base64
import io
from datetime import datetime

# ─────────────────────────────────────────────────────────────────
# APP INIT
# ─────────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    title="S3D ISO Case Closure Report",
    suppress_callback_exceptions=True
)
server = app.server  # for Render/Gunicorn

# ─────────────────────────────────────────────────────────────────
# COLOURS
# ─────────────────────────────────────────────────────────────────
C = {
    'blue':    '#1F4E79',
    'blue2':   '#2E75B6',
    'teal':    '#1F6B75',
    'red':     '#C00000',
    'amber':   '#C55A11',
    'green':   '#375623',
    'grey':    '#595959',
    'stripe':  '#EBF3FB',
    'outlier': '#FFCCCC',
    'good':    '#E2EFDA',
    'warn':    '#FFF2CC',
    'white':   '#FFFFFF',
}

# ─────────────────────────────────────────────────────────────────
# DATA PROCESSING
# ─────────────────────────────────────────────────────────────────
def parse_upload(contents):
    _, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    return pd.read_excel(io.BytesIO(decoded))

def clean_df(df, date_cols=None):
    df = df[df.iloc[:,0].notna() & ~df.iloc[:,0].astype(str).str.contains('Copyright|Confidential', na=False)].copy()
    for col in (date_cols or []):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).str.replace(',','').str.strip(), format='%d/%m/%Y %H:%M', errors='coerce')
    return df

def calc_ucl(s):
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    return round(q3 + 1.5*(q3-q1), 1)

def process_data(df1_raw, df2_raw, df3_raw):
    DC = ['Date/Time Opened','Date/Time Closed',
          'Case : Parent Case : Date/Time Opened','Case : Parent Case : Date/Time Closed']
    df1 = clean_df(df1_raw, ['Date/Time Opened','Date/Time Closed'])
    df2 = clean_df(df2_raw, DC)
    df3 = clean_df(df3_raw, DC)

    df1['Has_Helper']      = df1['Has Helper Case'].fillna(0).astype(int)
    df1['Parent_TTR_Days'] = df1['Time to Resolve'] / 24
    df1['Month']           = df1['Date/Time Closed'].dt.to_period('M').astype(str)
    df1['Week_str']        = df1['Date/Time Closed'].dt.to_period('W').apply(lambda w: str(w.start_time.date()))

    df2['Helper_TTR_Days'] = df2['Time to Resolve'] / 24
    df2['Parent_TTR_Days'] = df2['Parent Case: Time to Resolve'] / 24
    df2['Time_to_File']    = (df2['Date/Time Opened'] - df2['Case : Parent Case : Date/Time Opened']).dt.total_seconds()/86400
    df2['HP_Gap']          = (df2['Case : Parent Case : Date/Time Closed'] - df2['Date/Time Closed']).dt.total_seconds()/86400
    df2['Month']           = df2['Date/Time Closed'].dt.to_period('M').astype(str)
    df2['Week_str']        = df2['Date/Time Closed'].dt.to_period('W').apply(lambda w: str(w.start_time.date()))

    df3['Helper_TTR_Days'] = df3['Time to Resolve'] / 24
    df3['Parent_TTR_Days'] = df3['Parent Case: Time to Resolve'] / 24
    df3['Time_to_File']    = (df3['Date/Time Opened'] - df3['Case : Parent Case : Date/Time Opened']).dt.total_seconds()/86400
    df3['HP_Gap']          = (df3['Case : Parent Case : Date/Time Closed'] - df3['Date/Time Closed']).dt.total_seconds()/86400

    METRICS = ['Parent_TTR_Days','Helper_TTR_Days','Time_to_File','HP_Gap']
    ML = {'Parent_TTR_Days':'Parent Age','Helper_TTR_Days':'Helper Age',
          'Time_to_File':'Time to File Helper','HP_Gap':'Helper→Parent Gap'}

    UCL = {
        'Parent_TTR_Days': calc_ucl(df1['Parent_TTR_Days']),
        'Helper_TTR_Days': calc_ucl(df2['Helper_TTR_Days']),
        'Time_to_File':    calc_ucl(df2['Time_to_File']),
        'HP_Gap':          calc_ucl(df2['HP_Gap']),
    }
    MED = {m: round(df2[m].median(),1) for m in METRICS}
    AVG = {m: round(df2[m].mean(),1)   for m in METRICS}

    # Outlier flags
    df3['Outlier Flags'] = ''
    for m in METRICS:
        src = df1['Parent_TTR_Days'] if m == 'Parent_TTR_Days' else df2[m]
        q1h,q3h = src.quantile(0.25), src.quantile(0.75)
        lo, hi  = q1h-1.5*(q3h-q1h), q3h+1.5*(q3h-q1h)
        mask    = (df3[m]<lo)|(df3[m]>hi)
        df3.loc[mask,'Outlier Flags'] = df3.loc[mask,'Outlier Flags'].apply(
            lambda x: (x+', ' if x else '') + ML[m])
    df3['Is Outlier'] = df3['Outlier Flags'] != ''

    # Parent cases this week
    wk_lo = df3['Date/Time Closed'].min().replace(hour=0, minute=0)
    wk_hi = df3['Date/Time Closed'].max().replace(hour=23, minute=59)
    pw = df1[(df1['Date/Time Closed']>=wk_lo)&(df1['Date/Time Closed']<=wk_hi)].copy()
    df1['_k'] = df1['Case Number'].astype(str).str.replace(r'\.0','',regex=True).str.zfill(8)
    pw['_k']  = pw['Case Number'].astype(str).str.replace(r'\.0','',regex=True).str.zfill(8)
    df2['_k'] = df2['Parent Case'].apply(lambda x: str(int(float(x))).zfill(8) if pd.notna(x) else '')
    hagg = df2.groupby('_k').agg(
        Helper_Cases=('Case Number', lambda x: ', '.join(x.astype(str).str.replace(r'\.0','',regex=True).str.zfill(8))),
        Helper_Owner=('Case Owner',  lambda x: ', '.join(x.dropna().unique())),
        Avg_Helper_TTR=('Helper_TTR_Days','mean'),
        Avg_Time_to_File=('Time_to_File','mean'),
        Avg_HP_Gap=('HP_Gap','mean')).reset_index()
    pw = pw.merge(hagg, on='_k', how='left')
    pw['Is_Outlier'] = pw['Parent_TTR_Days'] > UCL['Parent_TTR_Days']

    # Monthly trend
    def build_monthly(d1, d2):
        vol = d1.groupby('Month').agg(
            No_Helper=('Has_Helper',lambda x:(x==0).sum()),
            With_Helper=('Has_Helper',lambda x:(x==1).sum())).reset_index()
        tno = d1[d1['Has_Helper']==0].groupby('Month').agg(
            Avg_NoHelper_TTR=('Parent_TTR_Days','mean'),
            Med_NoHelper_TTR=('Parent_TTR_Days','median')).reset_index()
        twp = d1[d1['Has_Helper']==1].groupby('Month').agg(
            Avg_Helper_Parent_TTR=('Parent_TTR_Days','mean')).reset_index()
        th  = d2.groupby('Month').agg(
            Avg_Helper_TTR=('Helper_TTR_Days','mean'),
            Helper_Outliers=('Helper_TTR_Days',lambda x:(x>UCL['Helper_TTR_Days']).sum())).reset_index()
        df  = vol.merge(tno,on='Month',how='left').merge(twp,on='Month',how='left').merge(th,on='Month',how='left').sort_values('Month').reset_index(drop=True)
        df['Total'] = df['No_Helper'] + df['With_Helper']
        return df

    monthly = build_monthly(df1, df2)

    # Ownership
    d2o = df2[df2['Month']>='2026-01'].copy()
    ownership_mo = d2o.groupby(['Month','Case Owner']).size().reset_index(name='Count')

    bench_label = f"{df2['Date/Time Closed'].min().strftime('%b %Y')}–{df2['Date/Time Closed'].max().strftime('%b %Y')}"

    return {
        'df3': df3, 'pw': pw, 'monthly': monthly,
        'ownership_mo': ownership_mo,
        'UCL': UCL, 'MED': MED, 'AVG': AVG, 'ML': ML,
        'bench_label': bench_label, 'bench_n': len(df2),
        'wk_min': df3['Date/Time Closed'].min().strftime('%d %b'),
        'wk_max': df3['Date/Time Closed'].max().strftime('%d %b %Y'),
        'df1_count': len(df1),
    }

# ─────────────────────────────────────────────────────────────────
# LAYOUT
# ─────────────────────────────────────────────────────────────────
HEADER_STYLE = {
    'background': C['blue'],
    'padding': '20px 30px',
    'marginBottom': '0',
}
CARD_STYLE = {
    'borderRadius': '8px',
    'boxShadow': '0 2px 8px rgba(0,0,0,0.08)',
    'marginBottom': '20px',
    'border': 'none',
}

app.layout = html.Div([
    dcc.Store(id='store-data'),

    # Header
    html.Div([
        html.Div([
            html.H1('S3D ISO Case Closure Report', style={'color':'white','margin':0,'fontSize':'1.6rem','fontWeight':700}),
            html.P('Upload the three Salesforce exports to generate the interactive weekly dashboard.',
                   style={'color':'#BDD7EE','margin':'4px 0 0 0','fontSize':'0.9rem'}),
        ]),
    ], style=HEADER_STYLE),

    # Upload section
    html.Div([
        dbc.Row([
            dbc.Col([
                html.Label('File 1 — All Parent Cases (12m)', style={'fontWeight':600,'color':C['blue'],'fontSize':'0.85rem'}),
                dcc.Upload(id='upload-f1', children=html.Div(['📁 Drag or ', html.A('click to upload')]),
                    style={'width':'100%','height':'60px','lineHeight':'60px','borderWidth':'2px',
                           'borderStyle':'dashed','borderRadius':'8px','textAlign':'center',
                           'borderColor':C['blue2'],'background':'#F0F7FF','cursor':'pointer','fontSize':'0.85rem'},
                    multiple=False),
                html.Div(id='f1-status', style={'fontSize':'0.75rem','marginTop':'4px','color':C['green']}),
            ], md=4),
            dbc.Col([
                html.Label('File 2 — Helper Cases (12m)', style={'fontWeight':600,'color':C['blue'],'fontSize':'0.85rem'}),
                dcc.Upload(id='upload-f2', children=html.Div(['📁 Drag or ', html.A('click to upload')]),
                    style={'width':'100%','height':'60px','lineHeight':'60px','borderWidth':'2px',
                           'borderStyle':'dashed','borderRadius':'8px','textAlign':'center',
                           'borderColor':C['blue2'],'background':'#F0F7FF','cursor':'pointer','fontSize':'0.85rem'},
                    multiple=False),
                html.Div(id='f2-status', style={'fontSize':'0.75rem','marginTop':'4px','color':C['green']}),
            ], md=4),
            dbc.Col([
                html.Label('File 3 — This Week\'s Cases', style={'fontWeight':600,'color':C['blue'],'fontSize':'0.85rem'}),
                dcc.Upload(id='upload-f3', children=html.Div(['📁 Drag or ', html.A('click to upload')]),
                    style={'width':'100%','height':'60px','lineHeight':'60px','borderWidth':'2px',
                           'borderStyle':'dashed','borderRadius':'8px','textAlign':'center',
                           'borderColor':C['blue2'],'background':'#F0F7FF','cursor':'pointer','fontSize':'0.85rem'},
                    multiple=False),
                html.Div(id='f3-status', style={'fontSize':'0.75rem','marginTop':'4px','color':C['green']}),
            ], md=4),
        ], className='g-3'),
        dbc.Row([
            dbc.Col(width=4),
            dbc.Col([
                dbc.Button('Generate Report', id='btn-generate', color='primary', size='lg',
                           className='w-100 mt-3', disabled=True,
                           style={'background':C['blue'],'border':'none','fontWeight':600}),
                html.Div(id='generate-status', style={'marginTop':'8px','fontSize':'0.85rem','textAlign':'center'}),
            ], md=4),
            dbc.Col(width=4),
        ]),
    ], style={'padding':'24px 30px','background':'#F8FBFF','borderBottom':'1px solid #D6E8F7'}),

    # Main dashboard (hidden until data loaded)
    html.Div(id='dashboard', style={'display':'none','padding':'24px 30px'}),

], style={'fontFamily':'Arial, sans-serif','minHeight':'100vh','background':'#F4F8FB'})


# ─────────────────────────────────────────────────────────────────
# UPLOAD STATUS CALLBACKS
# ─────────────────────────────────────────────────────────────────
def file_status(contents, filename):
    if contents:
        return f'✅ {filename}'
    return ''

@app.callback(Output('f1-status','children'), Input('upload-f1','filename'))
def s1(fn): return f'✅ {fn}' if fn else ''

@app.callback(Output('f2-status','children'), Input('upload-f2','filename'))
def s2(fn): return f'✅ {fn}' if fn else ''

@app.callback(Output('f3-status','children'), Input('upload-f3','filename'))
def s3(fn): return f'✅ {fn}' if fn else ''

@app.callback(
    Output('btn-generate','disabled'),
    Input('upload-f1','contents'), Input('upload-f2','contents'), Input('upload-f3','contents'))
def enable_btn(f1,f2,f3):
    return not (f1 and f2 and f3)


# ─────────────────────────────────────────────────────────────────
# MAIN GENERATE CALLBACK
# ─────────────────────────────────────────────────────────────────
@app.callback(
    Output('store-data','data'),
    Output('dashboard','children'),
    Output('dashboard','style'),
    Output('generate-status','children'),
    Input('btn-generate','n_clicks'),
    State('upload-f1','contents'), State('upload-f2','contents'), State('upload-f3','contents'),
    prevent_initial_call=True)
def generate(n_clicks, f1, f2, f3):
    try:
        d = process_data(parse_upload(f1), parse_upload(f2), parse_upload(f3))
    except Exception as e:
        import traceback
        err_detail = traceback.format_exc()
        err_div = html.Div([
            html.H4('❌ Error generating report', style={'color':C['red'],'marginBottom':'8px'}),
            html.Pre(str(e), style={'background':'#fff0f0','padding':'12px','borderRadius':'6px',
                                    'fontSize':'0.85rem','border':'1px solid #ffcccc','whiteSpace':'pre-wrap'}),
            html.Details([
                html.Summary('Full traceback', style={'cursor':'pointer','color':C['grey'],'fontSize':'0.8rem'}),
                html.Pre(err_detail, style={'fontSize':'0.75rem','marginTop':'8px'}),
            ]),
        ], style={'padding':'24px'})
        return None, err_div, {'display':'block'}, html.Span(f'❌ Error — see details below', style={'color':C['red']})

    df3      = d['df3']
    pw       = d['pw']
    monthly  = d['monthly']
    own_mo   = d['ownership_mo']
    UCL      = d['UCL']
    MED      = d['MED']
    AVG      = d['AVG']
    ML       = d['ML']
    n_out    = int(df3['Is Outlier'].sum())
    pw_with  = pw[pw['Has_Helper']==1]
    pw_wo    = pw[pw['Has_Helper']==0]
    METRICS  = ['Parent_TTR_Days','Helper_TTR_Days','Time_to_File','HP_Gap']

    # ── KPI CARDS ────────────────────────────────────────────────
    def kpi_card(label, value, color=C['blue'], bg='white'):
        return dbc.Col(dbc.Card([
            dbc.CardBody([
                html.P(label, style={'fontSize':'0.72rem','color':C['grey'],'margin':0,'fontWeight':600,'textTransform':'uppercase','letterSpacing':'0.5px'}),
                html.H3(value, style={'color':color,'margin':'4px 0 0 0','fontWeight':700,'fontSize':'1.5rem'}),
            ])
        ], style={**CARD_STYLE,'background':bg,'borderLeft':f'4px solid {color}'}))

    outlier_color = C['red'] if n_out > 0 else C['green']
    outlier_bg    = '#FFF0F0' if n_out > 0 else '#F0FFF4'

    kpi_row = dbc.Row([
        kpi_card('Cases Closed',   str(len(df3)),                                       C['blue']),
        kpi_card('Med Parent Age', f"{df3['Parent_TTR_Days'].median():.1f}d",           C['teal']),
        kpi_card('Med Helper Age', f"{df3['Helper_TTR_Days'].median():.1f}d",           C['teal']),
        kpi_card('Med Time to File',f"{df3['Time_to_File'].median():.1f}d",             C['amber']),
        kpi_card('Parent UCL',     f"{UCL['Parent_TTR_Days']}d",                        C['red']),
        kpi_card('Outlier Cases',  str(n_out),                                          outlier_color, outlier_bg),
        kpi_card('Parent Cases',   str(len(pw)),                                        C['blue2']),
    ], className='g-2 mb-3')

    # ── METRIC COMPARISON TABLE ───────────────────────────────────
    bench_rows = []
    for m in METRICS:
        wk_avg = round(df3[m].mean(),1); wk_med = round(df3[m].median(),1)
        da = round(wk_avg-AVG[m],1);    dm = round(wk_med-MED[m],1)
        breach = wk_med > UCL[m]; above = dm > 0 and not breach
        if breach:  status='🔴 Above UCL';     bg=C['outlier']
        elif above: status='🟠 Above median';  bg=C['warn']
        else:       status='🟢 At or below';   bg=C['good']
        bench_rows.append({
            'Metric': ML[m], 'This Week Avg': f"{wk_avg}d", 'This Week Median': f"{wk_med}d",
            '12m Avg': f"{AVG[m]}d", '12m Median': f"{MED[m]}d", 'UCL': f"{UCL[m]}d",
            'vs Median': f"+{dm}d" if dm>0 else f"{dm}d", 'Status': status, '_bg': bg,
        })

    bench_table = dash_table.DataTable(
        data=bench_rows,
        columns=[{'name':c,'id':c} for c in ['Metric','This Week Avg','This Week Median','12m Avg','12m Median','UCL','vs Median','Status']],
        style_table={'overflowX':'auto'},
        style_header={'backgroundColor':C['blue'],'color':'white','fontWeight':'bold','textAlign':'center','fontSize':'12px'},
        style_cell={'textAlign':'center','fontSize':'13px','padding':'8px 12px','border':'1px solid #D6E8F7'},
        style_cell_conditional=[{'if':{'column_id':'Metric'},'textAlign':'left','fontWeight':'bold'}],
        style_data_conditional=[
            {'if':{'filter_query':'{Status} contains "🔴"'},'backgroundColor':'#FFCCCC'},
            {'if':{'filter_query':'{Status} contains "🟠"'},'backgroundColor':'#FFF2CC'},
            {'if':{'filter_query':'{Status} contains "🟢"'},'backgroundColor':'#E2EFDA'},
        ])

    # ── CASE DETAIL TABLE ─────────────────────────────────────────
    df3_disp = df3.sort_values('Date/Time Closed').copy()
    df3_disp['Parent Case'] = df3_disp['Parent Case'].apply(lambda x: str(int(x)) if pd.notna(x) else '')
    df3_disp['Closed']      = df3_disp['Date/Time Closed'].dt.strftime('%d/%m/%Y %H:%M')
    df3_disp['Parent Age']  = df3_disp['Parent_TTR_Days'].apply(lambda x: f"{x:.1f}d" if pd.notna(x) else '—')
    df3_disp['Helper Age']  = df3_disp['Helper_TTR_Days'].apply(lambda x: f"{x:.1f}d" if pd.notna(x) else '—')
    df3_disp['Time to File']= df3_disp['Time_to_File'].apply(lambda x: f"{x:.1f}d" if pd.notna(x) else '—')
    df3_disp['H→P Gap']     = df3_disp['HP_Gap'].apply(lambda x: f"{x:.1f}d" if pd.notna(x) else '—')
    df3_disp['Outlier']     = df3_disp['Outlier Flags'].apply(lambda x: x if x else '—')
    df3_disp['Dev Item']    = df3_disp['Parent Case: Dev Item Number'].apply(lambda x: str(int(x)) if pd.notna(x) else '—')

    case_cols = ['Case Number','Parent Case','Case Owner','Case : Parent Case : Owner FullName',
                 'Closed','Parent Age','Helper Age','Time to File','H→P Gap','Parent Case: Status','Dev Item','Outlier']
    col_labels = {'Case Number':'Helper Case','Case : Parent Case : Owner FullName':'Parent Owner','Parent Case: Status':'Status'}

    detail_table = dash_table.DataTable(
        id='case-detail-table',
        data=df3_disp[case_cols].to_dict('records'),
        columns=[{'name':col_labels.get(c,c),'id':c} for c in case_cols],
        style_table={'overflowX':'auto'},
        style_header={'backgroundColor':C['blue'],'color':'white','fontWeight':'bold','textAlign':'center','fontSize':'11px'},
        style_cell={'textAlign':'center','fontSize':'12px','padding':'7px 10px','border':'1px solid #D6E8F7','whiteSpace':'normal'},
        style_cell_conditional=[
            {'if':{'column_id':'Case Owner'},'textAlign':'left'},
            {'if':{'column_id':'Case : Parent Case : Owner FullName'},'textAlign':'left'},
            {'if':{'column_id':'Outlier'},'textAlign':'left'},
        ],
        style_data_conditional=[
            {'if':{'filter_query':'{Outlier} != "—"'},'backgroundColor':'#FFCCCC','fontWeight':'bold'},
            {'if':{'row_index':'odd'},'backgroundColor':C['stripe']},
        ],
        filter_action='native',
        sort_action='native',
        page_size=20,
        tooltip_data=[{c: {'value': str(row[c]), 'type':'markdown'} for c in case_cols} for row in df3_disp[case_cols].to_dict('records')],
        tooltip_duration=None,
    )

    # ── PARENT CASES TABLE ────────────────────────────────────────
    def make_parent_table(df, has_helper):
        if len(df) == 0:
            return html.P('No cases this week.', style={'color':C['grey'],'fontStyle':'italic'})
        d = df.copy()
        d['Case Number'] = d['Case Number'].apply(lambda x: str(int(x)) if pd.notna(x) else '')
        d['Closed']      = d['Date/Time Closed'].dt.strftime('%d/%m/%Y')
        d['Parent TTR']  = d['Parent_TTR_Days'].apply(lambda x: f"{x:.1f}d" if pd.notna(x) else '—')
        d['Outlier']     = d['Is_Outlier'].apply(lambda x: '🔴 Yes' if x else '—')
        if has_helper:
            d['Helper Cases']    = d['Helper_Cases'].fillna('—')
            d['Helper Owner']    = d['Helper_Owner'].fillna('—')
            d['Avg Helper TTR']  = d['Avg_Helper_TTR'].apply(lambda x: f"{x:.1f}d" if pd.notna(x) else '—')
            d['Time to File']    = d['Avg_Time_to_File'].apply(lambda x: f"{x:.1f}d" if pd.notna(x) else '—')
            cols = ['Case Number','Case Owner','Account Name','Closed','Parent TTR','Helper Cases','Helper Owner','Avg Helper TTR','Time to File','Status','Outlier']
        else:
            cols = ['Case Number','Case Owner','Account Name','Closed','Parent TTR','Status','Outlier']
        d = d.rename(columns={'Account Name':'Account'})
        cols = [c.replace('Account Name','Account') for c in cols]
        return dash_table.DataTable(
            data=d[cols].to_dict('records'),
            columns=[{'name':c,'id':c} for c in cols],
            style_table={'overflowX':'auto'},
            style_header={'backgroundColor':C['blue2'] if has_helper else '#889DB5','color':'white','fontWeight':'bold','textAlign':'center','fontSize':'11px'},
            style_cell={'textAlign':'center','fontSize':'12px','padding':'7px 10px','border':'1px solid #D6E8F7'},
            style_cell_conditional=[
                {'if':{'column_id':'Case Owner'},'textAlign':'left'},
                {'if':{'column_id':'Account'},'textAlign':'left'},
            ],
            style_data_conditional=[
                {'if':{'filter_query':'{Outlier} = "🔴 Yes"'},'backgroundColor':'#FFCCCC','fontWeight':'bold'},
                {'if':{'row_index':'odd'},'backgroundColor':'#EAF4FF' if has_helper else C['stripe']},
            ],
            sort_action='native',
            page_size=20,
        )

    # ── CHARTS ────────────────────────────────────────────────────
    # Metric comparison bar chart
    metric_fig = go.Figure()
    labels = [ML[m] for m in METRICS]
    metric_fig.add_trace(go.Bar(name='This Week Median', x=labels,
        y=[round(df3[m].median(),1) for m in METRICS], marker_color=C['teal'], text=[f"{round(df3[m].median(),1)}d" for m in METRICS], textposition='outside'))
    metric_fig.add_trace(go.Bar(name='12m Median', x=labels,
        y=[MED[m] for m in METRICS], marker_color='#888780', text=[f"{MED[m]}d" for m in METRICS], textposition='outside'))
    metric_fig.add_trace(go.Bar(name='UCL', x=labels,
        y=[UCL[m] for m in METRICS], marker_color=C['red'], text=[f"{UCL[m]}d" for m in METRICS], textposition='outside'))
    metric_fig.update_layout(barmode='group', title='This Week vs 12m Median & UCL',
        plot_bgcolor='white', paper_bgcolor='white', height=320,
        legend=dict(orientation='h', y=-0.2), margin=dict(t=40,b=60,l=40,r=20),
        font=dict(family='Arial', size=11))
    metric_fig.update_yaxes(title='Days', gridcolor='#EEE')

    # Monthly trend chart
    trend_fig = go.Figure()
    trend_fig.add_trace(go.Bar(name='No Helper', x=monthly['Month'], y=monthly['No_Helper'],
        marker_color='#B8CCE4', hovertemplate='%{x}<br>No Helper: %{y}<extra></extra>'))
    trend_fig.add_trace(go.Bar(name='With Helper', x=monthly['Month'], y=monthly['With_Helper'],
        marker_color=C['blue2'], hovertemplate='%{x}<br>With Helper: %{y}<extra></extra>'))
    trend_fig.add_trace(go.Scatter(name='Avg TTR No Helper', x=monthly['Month'], y=monthly['Avg_NoHelper_TTR'].round(1),
        yaxis='y2', mode='lines+markers', line=dict(color=C['blue'],width=2),
        hovertemplate='%{x}<br>Avg TTR No Helper: %{y:.1f}d<extra></extra>'))
    trend_fig.add_trace(go.Scatter(name='Avg TTR With Helper', x=monthly['Month'], y=monthly['Avg_Helper_Parent_TTR'].round(1),
        yaxis='y2', mode='lines+markers', line=dict(color=C['red'],width=2),
        hovertemplate='%{x}<br>Avg TTR With Helper: %{y:.1f}d<extra></extra>'))
    trend_fig.update_layout(
        barmode='stack', title='Monthly Volume & Avg Resolution Time',
        plot_bgcolor='white', paper_bgcolor='white', height=380,
        yaxis=dict(title='Case Count', gridcolor='#EEE'),
        yaxis2=dict(title='Avg TTR (Days)', overlaying='y', side='right', gridcolor='#EEE'),
        legend=dict(orientation='h', y=-0.25), margin=dict(t=40,b=80,l=50,r=50),
        font=dict(family='Arial', size=11), hovermode='x unified')

    # Ownership chart
    own_pivot = own_mo.pivot(index='Month', columns='Case Owner', values='Count').fillna(0)
    own_colors = ['#1F4E79','#ED7D31','#70AD47','#FFC000','#4472C4','#FF0000','#A9D18E','#BF9000','#833C00']
    own_fig = go.Figure()
    for i, owner in enumerate(own_pivot.columns):
        own_fig.add_trace(go.Scatter(
            name=owner, x=own_pivot.index, y=own_pivot[owner],
            mode='lines+markers', line=dict(color=own_colors[i % len(own_colors)], width=2),
            marker=dict(size=6), hovertemplate=f'{owner}<br>%{{x}}: %{{y}} cases<extra></extra>'))
    own_fig.add_vline(x='2026-05', line_dash='dash', line_color=C['amber'], line_width=2,
                      annotation_text='★ Initiative', annotation_position='top right',
                      annotation_font_color=C['amber'], annotation_font_size=11)
    own_fig.update_layout(
        title='Helper Case Ownership by Month (★ = Initiative 18 May 2026)',
        plot_bgcolor='white', paper_bgcolor='white', height=380,
        yaxis=dict(title='Cases Closed', gridcolor='#EEE'),
        legend=dict(orientation='h', y=-0.3, font=dict(size=10)),
        margin=dict(t=40,b=100,l=50,r=20), font=dict(family='Arial', size=11))

    # ── TABS ──────────────────────────────────────────────────────
    dashboard = html.Div([
        # Title bar
        html.Div([
            html.H2(f"7-Day Case Closure Report — {d['wk_min']} to {d['wk_max']}",
                    style={'color':C['blue'],'margin':0,'fontWeight':700,'fontSize':'1.4rem'}),
            html.P(f"{len(df3)} helper cases · {len(pw)} parent cases · Benchmarks: {d['bench_n']} cases from {d['bench_label']} · Parent UCL = {UCL['Parent_TTR_Days']}d",
                   style={'color':C['grey'],'margin':'4px 0 0 0','fontSize':'0.85rem'}),
        ], style={'marginBottom':'20px'}),

        # KPI strip
        kpi_row,

        # Tabs
        dbc.Tabs([
            dbc.Tab(label='📊 Weekly Snapshot', tab_id='tab-snapshot', children=[
                html.Div([
                    html.H5('Metric Comparison — This Week vs 12-Month Benchmark',
                            style={'color':C['blue'],'fontWeight':700,'marginBottom':'12px','marginTop':'20px'}),
                    bench_table,
                    html.Hr(style={'borderColor':'#D6E8F7','margin':'24px 0'}),
                    dbc.Row([
                        dbc.Col([
                            dcc.Graph(figure=metric_fig, config={'displayModeBar':False}),
                        ], md=12),
                    ]),
                    html.Hr(style={'borderColor':'#D6E8F7','margin':'24px 0'}),
                    html.Div([
                        dbc.Row([
                            dbc.Col(html.H5('Case Detail — This Week',
                                    style={'color':C['blue'],'fontWeight':700}), md=8),
                            dbc.Col(dbc.ButtonGroup([
                                dbc.Button('All Cases', id='filter-all', size='sm', outline=True, color='primary', active=True),
                                dbc.Button('Outliers Only', id='filter-outliers', size='sm', outline=True, color='danger'),
                                dbc.Button('Open Parents', id='filter-open', size='sm', outline=True, color='warning'),
                            ]), md=4, className='text-end'),
                        ], className='align-items-center mb-3'),
                        html.Div(id='case-detail-container', children=detail_table),
                    ]),
                    html.P(f"Parent UCL={UCL['Parent_TTR_Days']}d (all {d['df1_count']:,} parent cases) · Helper UCL={UCL['Helper_TTR_Days']}d · Time to File UCL={UCL['Time_to_File']}d · H→P Gap UCL={UCL['HP_Gap']}d",
                           style={'fontSize':'0.75rem','color':C['grey'],'fontStyle':'italic','marginTop':'12px'}),
                ]),
            ]),

            dbc.Tab(label='👨‍👩‍👧 Parent Cases Closed', tab_id='tab-parents', children=[
                html.Div([
                    dbc.Row([
                        dbc.Col(dbc.Card(dbc.CardBody([
                            html.P('With Helper', style={'fontSize':'0.75rem','color':C['grey'],'margin':0,'fontWeight':600}),
                            html.H3(str(len(pw_with)), style={'color':C['blue2'],'margin':0,'fontWeight':700}),
                            html.P(f"Avg {pw_with['Parent_TTR_Days'].mean():.1f}d · Med {pw_with['Parent_TTR_Days'].median():.1f}d" if len(pw_with)>0 else 'No cases',
                                   style={'fontSize':'0.8rem','color':C['grey'],'margin':0}),
                        ]), style={**CARD_STYLE,'borderLeft':f'4px solid {C["blue2"]}'}), md=3),
                        dbc.Col(dbc.Card(dbc.CardBody([
                            html.P('Without Helper', style={'fontSize':'0.75rem','color':C['grey'],'margin':0,'fontWeight':600}),
                            html.H3(str(len(pw_wo)), style={'color':'#889DB5','margin':0,'fontWeight':700}),
                            html.P(f"Avg {pw_wo['Parent_TTR_Days'].mean():.1f}d · Med {pw_wo['Parent_TTR_Days'].median():.1f}d" if len(pw_wo)>0 else 'No cases',
                                   style={'fontSize':'0.8rem','color':C['grey'],'margin':0}),
                        ]), style={**CARD_STYLE,'borderLeft':'4px solid #889DB5'}), md=3),
                        dbc.Col(dbc.Card(dbc.CardBody([
                            html.P('Outliers (>UCL)', style={'fontSize':'0.75rem','color':C['grey'],'margin':0,'fontWeight':600}),
                            html.H3(str(int(pw['Is_Outlier'].sum())), style={'color':C['red'] if pw['Is_Outlier'].sum()>0 else C['green'],'margin':0,'fontWeight':700}),
                            html.P(f"UCL = {UCL['Parent_TTR_Days']}d", style={'fontSize':'0.8rem','color':C['grey'],'margin':0}),
                        ]), style={**CARD_STYLE,'borderLeft':f'4px solid {C["red"]}'}), md=3),
                        dbc.Col(dbc.Card(dbc.CardBody([
                            html.P('Total Closed', style={'fontSize':'0.75rem','color':C['grey'],'margin':0,'fontWeight':600}),
                            html.H3(str(len(pw)), style={'color':C['blue'],'margin':0,'fontWeight':700}),
                            html.P('This week', style={'fontSize':'0.8rem','color':C['grey'],'margin':0}),
                        ]), style={**CARD_STYLE,'borderLeft':f'4px solid {C["blue"]}'}), md=3),
                    ], className='g-3 mt-2'),
                    html.H5(f'With Helper ({len(pw_with)} cases)',
                            style={'color':'white','background':C['blue2'],'padding':'10px 16px','borderRadius':'6px','fontWeight':600,'marginTop':'8px'}),
                    make_parent_table(pw_with.sort_values('Parent_TTR_Days', ascending=False), True),
                    html.H5(f'Without Helper ({len(pw_wo)} cases)',
                            style={'color':'white','background':'#889DB5','padding':'10px 16px','borderRadius':'6px','fontWeight':600,'marginTop':'20px'}),
                    make_parent_table(pw_wo.sort_values('Parent_TTR_Days', ascending=False), False),
                    html.P(f"Source: File 1 filtered to this week. Parent outlier = TTR > {UCL['Parent_TTR_Days']}d.",
                           style={'fontSize':'0.75rem','color':C['grey'],'fontStyle':'italic','marginTop':'12px'}),
                ]),
            ]),

            dbc.Tab(label='📈 12 Month Trend', tab_id='tab-trend', children=[
                html.Div([
                    dcc.Graph(figure=trend_fig, config={'displayModeBar':True,
                        'modeBarButtonsToRemove':['select2d','lasso2d']}),
                ], style={'marginTop':'16px'}),
            ]),

            dbc.Tab(label='👥 Ownership', tab_id='tab-ownership', children=[
                html.Div([
                    dcc.Graph(figure=own_fig, config={'displayModeBar':True,
                        'modeBarButtonsToRemove':['select2d','lasso2d']}),
                    html.P('Click legend entries to show/hide individual engineers. Double-click to isolate one engineer.',
                           style={'fontSize':'0.8rem','color':C['grey'],'fontStyle':'italic','textAlign':'center'}),
                ], style={'marginTop':'16px'}),
            ]),

            dbc.Tab(label='📋 Benchmarks', tab_id='tab-benchmarks', children=[
                html.Div([
                    html.H5('IQR Benchmark Reference', style={'color':C['blue'],'fontWeight':700,'marginTop':'16px'}),
                    html.P(f"Parent UCL from all {d['df1_count']:,} parent cases · All other UCLs from {d['bench_n']} helper cases · UCL = Q3 + 1.5 × IQR",
                           style={'fontSize':'0.85rem','color':C['grey']}),
                    dash_table.DataTable(
                        data=[{'Metric':ML[m],'UCL (days)':UCL[m],'12m Median':MED[m],'12m Avg':AVG[m]} for m in ['Parent_TTR_Days','Helper_TTR_Days','Time_to_File','HP_Gap']],
                        columns=[{'name':c,'id':c} for c in ['Metric','UCL (days)','12m Median','12m Avg']],
                        style_header={'backgroundColor':C['blue'],'color':'white','fontWeight':'bold','textAlign':'center'},
                        style_cell={'textAlign':'center','fontSize':'13px','padding':'10px 14px','border':'1px solid #D6E8F7'},
                        style_cell_conditional=[{'if':{'column_id':'Metric'},'textAlign':'left','fontWeight':'bold'}],
                        style_data_conditional=[
                            {'if':{'column_id':'UCL (days)'},'backgroundColor':C['warn'],'fontWeight':'bold','color':C['red']},
                            {'if':{'row_index':'odd'},'backgroundColor':C['stripe']},
                        ]),
                ]),
            ]),
        ], id='main-tabs', active_tab='tab-snapshot',
           style={'marginTop':'4px'},
           className='nav-tabs'),
    ])

    return None, dashboard, {'display':'block'}, html.Span('✅ Report generated successfully', style={'color':C['green']})


# ─────────────────────────────────────────────────────────────────
# FILTER BUTTONS CALLBACK
# ─────────────────────────────────────────────────────────────────
@app.callback(
    Output('case-detail-container','children'),
    Output('filter-all','active'),
    Output('filter-outliers','active'),
    Output('filter-open','active'),
    Input('filter-all','n_clicks'),
    Input('filter-outliers','n_clicks'),
    Input('filter-open','n_clicks'),
    State('upload-f1','contents'),
    State('upload-f2','contents'),
    State('upload-f3','contents'),
    prevent_initial_call=True)
def filter_cases(n_all, n_out, n_open, f1, f2, f3):
    ctx = callback_context
    if not ctx.triggered or not f1 or not f2 or not f3:
        return dash.no_update, True, False, False

    triggered = ctx.triggered[0]['prop_id'].split('.')[0]

    try:
        d   = process_data(parse_upload(f1), parse_upload(f2), parse_upload(f3))
        df3 = d['df3']
        UCL = d['UCL']
        ML  = d['ML']
    except:
        return dash.no_update, True, False, False

    if triggered == 'filter-outliers':
        df3 = df3[df3['Is Outlier']]
        active = (False, True, False)
    elif triggered == 'filter-open':
        open_statuses = ['Waiting on Customer','Waiting on Analyst','Open Dev Item']
        df3 = df3[df3['Parent Case: Status'].isin(open_statuses)]
        active = (False, False, True)
    else:
        active = (True, False, False)

    df3_disp = df3.sort_values('Date/Time Closed').copy()
    df3_disp['Parent Case'] = df3_disp['Parent Case'].apply(lambda x: str(int(x)) if pd.notna(x) else '')
    df3_disp['Closed']      = df3_disp['Date/Time Closed'].dt.strftime('%d/%m/%Y %H:%M')
    df3_disp['Parent Age']  = df3_disp['Parent_TTR_Days'].apply(lambda x: f"{x:.1f}d" if pd.notna(x) else '—')
    df3_disp['Helper Age']  = df3_disp['Helper_TTR_Days'].apply(lambda x: f"{x:.1f}d" if pd.notna(x) else '—')
    df3_disp['Time to File']= df3_disp['Time_to_File'].apply(lambda x: f"{x:.1f}d" if pd.notna(x) else '—')
    df3_disp['H→P Gap']     = df3_disp['HP_Gap'].apply(lambda x: f"{x:.1f}d" if pd.notna(x) else '—')
    df3_disp['Outlier']     = df3_disp['Outlier Flags'].apply(lambda x: x if x else '—')
    df3_disp['Dev Item']    = df3_disp['Parent Case: Dev Item Number'].apply(lambda x: str(int(x)) if pd.notna(x) else '—')

    case_cols = ['Case Number','Parent Case','Case Owner','Case : Parent Case : Owner FullName',
                 'Closed','Parent Age','Helper Age','Time to File','H→P Gap','Parent Case: Status','Dev Item','Outlier']
    col_labels = {'Case Number':'Helper Case','Case : Parent Case : Owner FullName':'Parent Owner','Parent Case: Status':'Status'}

    if len(df3_disp) == 0:
        msg = 'No outlier cases this week.' if triggered=='filter-outliers' else 'No cases with open parents.'
        table = html.P(msg, style={'color':C['grey'],'fontStyle':'italic','padding':'12px'})
    else:
        table = dash_table.DataTable(
            data=df3_disp[case_cols].to_dict('records'),
            columns=[{'name':col_labels.get(c,c),'id':c} for c in case_cols],
            style_table={'overflowX':'auto'},
            style_header={'backgroundColor':C['blue'],'color':'white','fontWeight':'bold','textAlign':'center','fontSize':'11px'},
            style_cell={'textAlign':'center','fontSize':'12px','padding':'7px 10px','border':'1px solid #D6E8F7','whiteSpace':'normal'},
            style_cell_conditional=[
                {'if':{'column_id':'Case Owner'},'textAlign':'left'},
                {'if':{'column_id':'Case : Parent Case : Owner FullName'},'textAlign':'left'},
            ],
            style_data_conditional=[
                {'if':{'filter_query':'{Outlier} != "—"'},'backgroundColor':'#FFCCCC','fontWeight':'bold'},
                {'if':{'row_index':'odd'},'backgroundColor':C['stripe']},
            ],
            filter_action='native', sort_action='native', page_size=20)

    return table, *active


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=8050)
