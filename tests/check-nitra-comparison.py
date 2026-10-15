#!/usr/bin/env python3
"""Differential correctness and isolated performance of native/side recognition.

No compiler source is patched by this harness. Both engines consume artifacts
from one shared native grammar compilation. Mismatches remain failures; timing
ratios are published only for workloads which passed differential checks.
"""
import argparse, hashlib, json, os, pathlib, platform, random, shutil, statistics
import subprocess, sys, tempfile, time, ast, copy, re

HERE=pathlib.Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--toolchain',type=pathlib.Path,required=True)
p.add_argument('--references',type=pathlib.Path,required=True)
p.add_argument('--native-core',type=pathlib.Path)
p.add_argument('--output',type=pathlib.Path,default=HERE/'coreclr-verification/nitra-comparison.json')
p.add_argument('--seed',type=int,default=17011)
p.add_argument('--repeats',type=int,default=3,help='fresh processes per engine per benchmark workload')
p.add_argument('--timeout',type=float,default=30,help='hard timeout per isolated worker in seconds; 0 waits for completion')
p.add_argument('--profile',choices=['smoke','standard','stress'],default='standard')
p.add_argument('--side-workers',type=int,help='override internal filter parallelism')
p.add_argument('--side-node-minimum',type=int,help='override ready transition dispatch threshold')
p.add_argument('--side-minimum',type=int,help='override minimum candidates per filter worker')
p.add_argument('--side-legacy',action='store_true',help='exercise previous recognizer for differential controls')
p.add_argument('--prepare-only',action='store_true')
p.add_argument('--no-benchmarks',action='store_true',help='complete correctness and backend checks without repeated timing workers')
p.add_argument('--case-pattern',help='run only case names matching this regular expression; selection is recorded')
p.add_argument('--reuse',type=pathlib.Path,help='reuse a previously prepared harness directory')
a=p.parse_args()
if a.repeats<1 or a.timeout<0:p.error('repeats must be positive; timeout must be nonnegative')
refs=a.references.resolve();toolchain=a.toolchain.resolve();native=(a.native_core or a.toolchain).resolve()
w=a.reuse.resolve() if a.reuse else pathlib.Path(tempfile.mkdtemp(prefix='nemerle-nitra-comparison-'))
w.mkdir(exist_ok=True); print('Comparison artifacts:',w,flush=True)
env=os.environ.copy();env.setdefault('DOTNET_CLI_HOME',str(w/'dotnet-home'));env.update(DOTNET_TieredCompilation='0',DOTNET_gcServer='0')
for option,setting in [(a.side_workers,'NITRA_FILTER_WORKERS'),(a.side_minimum,'NITRA_FILTER_MINIMUM'),(a.side_node_minimum,'NITRA_NODE_MINIMUM')]:
    if option is not None:
        if option<1:p.error('filter worker settings must be positive')
        env[setting]=str(option)
    else:env.pop(setting,None)
if a.side_legacy:env['NITRA_FILTER_LEGACY']='1'
else:env.pop('NITRA_FILTER_LEGACY',None)
# No simultaneous workers: CPU/memory contention must not favor either engine.
def run_build(name,command):
    with (w/(name+'.log')).open('w') as log:
        r=subprocess.run(list(map(str,command)),cwd=w,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
    if r.returncode:raise RuntimeError((w/(name+'.log')).read_text())
if not a.reuse:
    for root in [native,toolchain]:
        for f in root.iterdir():
            if f.is_file() and f.suffix in {'.dll','.exe','.json','.nitrametadata'}:shutil.copy2(f,w/f.name)
    if hashlib.sha256((w/'Nemerle.Compiler.dll').read_bytes()).digest()!=hashlib.sha256((toolchain/'Nemerle.Compiler.dll').read_bytes()).digest():
        raise RuntimeError('comparison compiler does not match selected toolchain')
    runtime_rows=[s.split() for s in subprocess.check_output(['dotnet','--list-runtimes'],text=True).splitlines() if s.startswith('Microsoft.NETCore.App ')]
    row=max(runtime_rows,key=lambda r:tuple(map(int,r[1].split('.'))));runtime=pathlib.Path(row[2].strip('[]'))/row[1]
    common=['dotnet',w/'ncc.exe','-no-color','-source-root:'+str(HERE/'nitra-comparison'),'-target-references:'+str(refs)]
    reference_names=['Nemerle.Compiler','Integrated.Nitra.Runtime','Integrated.DotNetLang','Integrated.Nitra.Grammar']
    command=common+[HERE/'nitra-comparison/Comparison.nitra','-macros:'+str(w/'Integrated.Nitra.Compiler.dll'),'-target:library','-out:'+str(w/'Comparison.dll')]
    command+=['-r:'+str(w/(n+'.dll')) for n in reference_names]
    command+=['-r:'+str(runtime/(n+'.dll')) for n in ['System.Collections.Immutable','System.Linq','System.Xml.XDocument','System.Xml.ReaderWriter','System.Xml.XmlDocument']]
    version,folder=subprocess.check_output(['dotnet','--list-sdks'],text=True).splitlines()[-1].split(' ',1)
    csc=pathlib.Path(folder.strip('[]'))/version/'Roslyn/bincore/csc.dll'
    rsp=w/'worker.rsp';rsp.write_text('\n'.join(['-nologo','-nostdlib+','-target:exe','-out:"'+str(w/'Worker.dll')+'"']
        +['-r:"'+str(f)+'"' for f in sorted(refs.glob('*.dll'))]
        +['-r:"'+str(w/(n+'.dll'))+'"' for n in ['Nemerle',*reference_names]]
        +['"'+str(HERE/'nitra-comparison/Worker.cs')+'"']))
    run_build('worker-build',['dotnet',csc,'@'+str(rsp)])
    shutil.copy2(w/'ncc.runtimeconfig.json',w/'Worker.runtimeconfig.json')
    command += [HERE/'nitra-comparison/Comparison.n','-r:'+str(w/'Worker.dll')]
    run_build('fixture-build',command)
prepared_inputs={str(f.relative_to(HERE)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [HERE/'nitra-comparison/Worker.cs',HERE/'nitra-comparison/Comparison.nitra',HERE/'nitra-comparison/Comparison.n']}
manifest=w/'HARNESS.json'
if a.reuse:
    if not manifest.exists() or json.loads(manifest.read_text())!=prepared_inputs:
        raise SystemExit('Prepared harness is stale or has no source manifest; rebuild without --reuse')
else:
    manifest.write_text(json.dumps(prepared_inputs,indent=2)+'\n')
    snapshot=w/'harness-sources';snapshot.mkdir(exist_ok=True)
    for source in [HERE/'nitra-comparison/Worker.cs',HERE/'nitra-comparison/Comparison.nitra',HERE/'nitra-comparison/Comparison.n',pathlib.Path(__file__).resolve()]:shutil.copy2(source,snapshot/source.name)
if hashlib.sha256((w/'Nemerle.Compiler.dll').read_bytes()).digest()!=hashlib.sha256((toolchain/'Nemerle.Compiler.dll').read_bytes()).digest():
    raise SystemExit('prepared comparison compiler does not match selected toolchain')
if a.prepare_only:
    print('Prepared:',w,flush=True);sys.exit(0)

rng=random.Random(a.seed);cases=[]
def case(name,module,text,expected='accepted',mapping=None,benchmark=False):
    cases.append(dict(name=name,Module=module if module=='NitraSyntax' else 'Comparison.'+module,Rule=(module if module=='NitraSyntax' else 'Comparison.'+module)+'.Start',Text=text,expected=expected,mapping=mapping,benchmark=benchmark))
case('literal','Arithmetic','7',mapping='7',benchmark=True)
case('left-associativity','Arithmetic','7-7-7')
case('precedence','Arithmetic','7-7*7')
case('parentheses','Arithmetic','(7-7)*7')
case('right-associativity','RightAssociative','7-7-7')
case('whitespace','Arithmetic',' 7 +\n 7 * 7\t')
case('empty','Arithmetic','','rejected')
case('missing-operand','Arithmetic','7+','rejected')
case('wrong-token','Arithmetic','q','rejected')
case('trailing-garbage','Arithmetic','7 q','rejected')
case('unclosed','Arithmetic','(7+7','rejected')
case('list-empty','Lists','[]',mapping='0')
case('list-optional','Lists','[tag x y z,x,x y z]',mapping='3')
case('list-absent','Lists','[x,x]',mapping='2')
case('list-leading-separator','Lists','[,x]','rejected')
case('list-trailing-separator','Lists','[x,]','rejected')
case('list-incomplete-option','Lists','[x y]','rejected')
case('sql-basic','Sql','SELECT a,b FROM table',mapping='2')
case('sql-filter','Sql','SELECT a FROM t WHERE x=y',mapping='1')
case('sql-missing-table','Sql','SELECT a FROM','rejected')
case('sql-bad-column','Sql','SELECT , FROM t','rejected')
case('lookahead','Lookahead','begin123end',mapping='3')
case('lookahead-subtraction','Lookahead','begin102end','rejected')
case('lookahead-negative','Lookahead','beginend','rejected')
case('lookahead-anchor','Lookahead','begun12end','rejected')
case('overlap-short','Overlap','a!',mapping='1')
case('overlap-long','Overlap','ab!',mapping='2')
case('overlap-invalid','Overlap','abc!','rejected')
case('ambiguous','Ambiguity','x','ambiguous')
case('ambiguity-invalid','Ambiguity','z','rejected')
# Definitions exercise the native declaration recognizer as well as user input.
case('definition-fixture','NitraSyntax',(HERE/'nitra-comparison/Comparison.nitra').read_text())
case('definition-missing-brace','NitraSyntax','syntax module X { syntax A = "x";','rejected')
case('definition-invalid','NitraSyntax','syntax module { ??? }','rejected')
if a.profile!='smoke':
    for i in range(12):
        terms=['7' for _ in range(rng.randint(2,8))];text=terms[0]
        for term in terms[1:]:text+=rng.choice(['+','-','*'])+term
        case('generated-expression-'+str(i),'Arithmetic',text)
        case('mutated-expression-'+str(i),'Arithmetic',text+rng.choice(['+','*',')','?']),'rejected')
    sizes=[8,32,128] if a.profile=='standard' else [8,32,128,512,2048]
else:sizes=[8]
for size in sizes:
    case('chain-'+str(size),'Arithmetic','+'.join(['7']*size),benchmark=True)
    case('list-'+str(size),'Lists','['+','.join(['x']*size)+']',mapping=str(size),benchmark=True)
    case('sql-'+str(size),'Sql','SELECT '+','.join(['a']*size)+' FROM t',mapping=str(size),benchmark=True)
    case('near-miss-'+str(size),'Arithmetic','+'.join(['7']*size)+'+','rejected',benchmark=True)
for depth in ([4] if a.profile=='smoke' else [4,16,64] if a.profile=='standard' else [4,16,64,256,1024]):
    case('nesting-'+str(depth),'Arithmetic','('*depth+'7'+')'*depth,benchmark=True)

if a.case_pattern:
    try: selection=re.compile(a.case_pattern)
    except re.error as error:p.error(str(error))
    cases=[c for c in cases if selection.search(c['name'])]
    if not cases:p.error('case pattern matched no workloads')

report={'seed':a.seed,'profile':a.profile,'case_pattern':a.case_pattern,'work':str(w),'protocol':{
    'same_compiled_grammar_for_both':True,'side_filter_settings':{'maximum_workers':a.side_workers,'minimum_candidates':a.side_minimum,'minimum_node_work':a.side_node_minimum,'legacy':a.side_legacy},'compiler_context':'same parse-only compiler initialization for mapping types; measured separately','native_recovery':'disabled by strict rejection callback; never treat recovered input as accepted',
    'workers':'one isolated process per engine/case; sequential execution; order randomized with recorded seed',
    'benchmarks_enabled':not a.no_benchmarks,'warmups':2,'samples_per_process':5,'iterations_per_sample':3,'fresh_process_repeats':a.repeats,'timeout_seconds':a.timeout or None,
    'engine_runtime':'both engines are managed CLR assemblies launched with the same dotnet host; native means original Nitra machinery, not native C or AOT',
    'timed_work':'source snapshot + recognition/root construction + forced full native-field snapshot + mapping/prettyprint',
    'lazy_fields':'native fields forced before comparing full-tree cost; root-only times are not a speed comparison',
    'peak_memory':'whole-worker peak RSS includes runtime, setup, JIT and snapshots; allocations measured on worker thread',
    'tiered_compilation':env['DOTNET_TieredCompilation'],'gc_server':env['DOTNET_gcServer'],'recovery_and_incremental_editing':'recovery is fail-fast; IDE recovery and incremental editing not benchmarked',
    'ratios':'only for correctness-matched cases; side/native, smaller is better; no overall speedup claim'},
    'machine':{'platform':platform.platform(),'cpu':platform.processor(),'logical_cpus':os.cpu_count(),'load_average':os.getloadavg() if hasattr(os,'getloadavg') else None,'affinity':sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,'dotnet':subprocess.check_output(['dotnet','--info'],text=True)},
    'artifacts':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(w.glob('*.dll'))},
    'harness_sha256':{str(f.relative_to(HERE)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [pathlib.Path(__file__).resolve(),HERE/'nitra-comparison/Worker.cs']},
    'fixture_sha256':hashlib.sha256((HERE/'nitra-comparison/Comparison.nitra').read_bytes()).hexdigest(),
    'cases':[],'benchmarks':[],'failures':[]}
a.output=a.output.resolve();a.output.parent.mkdir(parents=True,exist_ok=True)
def save():a.output.write_text(json.dumps(report,indent=2)+'\n')
def worker(c,engine,benchmark=False,repeat=0):
    stem=c['name']+'-'+engine+('-bench'+str(repeat) if benchmark else '-check')
    request={k:c[k] for k in ['Module','Rule','Text']};request['Benchmark']=benchmark;request['Backend']=not benchmark;request['References']=str(refs)
    path=w/(stem+'.json');path.write_text(json.dumps(request));started=time.perf_counter()
    try:
        r=subprocess.run(['dotnet',str(w/'Worker.dll'),str(w/'Comparison.dll'),engine,str(path)],cwd=w,env=env,capture_output=True,text=True,timeout=a.timeout or None)
        (w/(stem+'.stdout')).write_text(r.stdout);(w/(stem+'.stderr')).write_text(r.stderr)
        rows=[line for line in r.stdout.splitlines() if line.startswith('{')]
        data=json.loads(rows[-1]) if rows else {'status':'worker_crash','error':r.stderr[-4000:]}
        data['exit_code']=r.returncode
    except subprocess.TimeoutExpired as error:
        data={'status':'timeout','error':'hard worker timeout','exit_code':None}
        for suffix,value in [('stdout',error.stdout),('stderr',error.stderr)]:
            (w/(stem+'.'+suffix)).write_bytes(value if isinstance(value,bytes) else (value or '').encode())
    data['wall_seconds']=time.perf_counter()-started;data['request']=str(path);return data

def compare(c,results):
    n,s=results['native'],results['side'];reasons=[]
    for engine,r in results.items():
        if r['status']!=c['expected']:reasons.append(engine+' status '+r['status']+'; expected '+c['expected'])
        if not r.get('recovery_passed',True):reasons.append(engine+' failed accepted/rejected/accepted recovery check')
        if r.get('exit_code')!=0:reasons.append(engine+' worker exit '+str(r.get('exit_code')))
        if c['mapping'] is not None and r.get('mapping')!=c['mapping']:reasons.append(engine+' unexpected mapping')
    if n['status']!=s['status']:reasons.append('acceptance/ambiguity mismatch')
    if n['status']==s['status']=='accepted':
        if n['tree_sha256']!=s['tree_sha256']:reasons.append('native typed-field tree mismatch')
        if n.get('mapping')!=s.get('mapping'):reasons.append('lowered Nemerle expression mismatch')
        if n['end']!=s['end']:reasons.append('consumed boundary mismatch')
    return reasons
# Complete correctness first; a failing case can never produce a speed ratio.
for c in cases:
    order=['native','side'];rng.shuffle(order);results={engine:worker(c,engine) for engine in order}
    reasons=compare(c,results);row={**c,'engine_order':order,'results':results,'passed':not reasons,'failures':reasons};report['cases'].append(row)
    if reasons:report['failures'].append({'case':c['name'],'phase':'correctness','reasons':reasons})
    print(('FAIL' if reasons else 'PASS')+': '+c['name']+(' — '+'; '.join(reasons) if reasons else ''),flush=True);save()
# Verify the comparator itself detects each class of mismatch, using a real pair.
control=next((r for r in report['cases'] if r['passed'] and r['expected']=='accepted' and r['results']['native'].get('mapping') is not None),None)
report['comparator_controls']={}
if control:
    for key,value in [('status','rejected'),('tree_sha256','deliberately-corrupted'),('mapping','deliberately-corrupted'),('end',-1)]:
        changed=copy.deepcopy(control['results']);changed['side'][key]=value
        caught=bool(compare(control,changed));report['comparator_controls'][key]=caught
        if not caught:report['failures'].append({'phase':'comparator-control','field':key})
    again=worker(control,'native');reasons=compare(control,{'native':control['results']['native'],'side':again})
    report['native_repeat_control']={'passed':not reasons,'results':again,'failures':reasons}
    if reasons:report['failures'].append({'phase':'native-repeat-control','reasons':reasons})

def expected_value(c):
    if c['mapping'] is not None:return int(c['mapping'])
    if c['Module']=='Comparison.RightAssociative':return 7 if c['Text'].count('-')%2==0 else 0
    if c['Module']!='Comparison.Arithmetic':return None
    def calculate(n):
        if isinstance(n,ast.Constant) and n.value==7:return 7
        if isinstance(n,ast.BinOp):
            left,right=calculate(n.left),calculate(n.right)
            if isinstance(n.op,ast.Add):return left+right
            if isinstance(n.op,ast.Sub):return left-right
            if isinstance(n.op,ast.Mult):return left*right
        raise ValueError('unsupported independent arithmetic oracle')
    text=''.join(c['Text'].split())
    # Python's parser caps parentheses below our stress inputs; these fixtures
    # contain only one literal wrapped in balanced grouping.
    if re.fullmatch(r'\(+7\)+',text) and text.count('(')==text.count(')'):return 7
    # A pure sum has an independent closed-form oracle and does not need to
    # inherit Python AST construction/evaluation recursion limits.
    if re.fullmatch(r'7(?:\+7)*',text):return 7*(text.count('+')+1)
    return calculate(ast.parse(text,mode='eval').body)

# Direct AST outputs are compiled inside each correctness worker through Replay.
backend_errors=[];executed=0
for c in report['cases']:
    if c['expected']!='accepted' or c['results']['native'].get('mapping') is None:continue
    expected=expected_value(c)
    for engine,r in c['results'].items():
        if r.get('backend_value')!=expected or r.get('backend_error'):
            backend_errors.append({'case':c['name'],'engine':engine,'expected':expected,'actual':r.get('backend_value'),'error':r.get('backend_error')})
            c['passed']=False;c['failures'].append('direct AST backend mismatch')
        else:executed+=1
report['backend']={'passed':not backend_errors,'executed_outputs':executed,'mode':'actual mapped PExpr injected by Replay macro under caller compiler context','errors':backend_errors}
if backend_errors:report['failures'].append({'phase':'backend','errors':backend_errors})
save();print('BACKEND: '+str(report['backend']['passed']),flush=True)

for row in report['cases']:
    if a.no_benchmarks or not row['benchmark']:continue
    if not row['passed']:
        report['benchmarks'].append({'case':row['name'],'skipped':'correctness failed'});continue
    measurements={'native':[],'side':[]};orders=[];failed=False
    for repeat in range(a.repeats):
        order=['native','side'];rng.shuffle(order);orders.append(order)
        for engine in order:
            data=worker(row,engine,True,repeat);measurements[engine].append(data)
            original=row['results'][engine]
            if data['status']!=original['status'] or data.get('tree_sha256')!=original.get('tree_sha256') or data.get('mapping')!=original.get('mapping') or data.get('exit_code')!=0:
                failed=True;report['failures'].append({'case':row['name'],'phase':'benchmark','engine':engine,'status':data['status']})
    b={'case':row['name'],'characters':len(row['Text']),'orders':orders,'results':measurements,'passed':not failed}
    if not failed:
        b['summary']={}
        for engine,rows in measurements.items():
            times=[statistics.median(x['total_ms'] for x in r['samples']) for r in rows]
            allocations=[statistics.median(x['allocated_bytes'] for x in r['samples']) for r in rows]
            b['summary'][engine]={'process_median_ms':statistics.median(times),'process_min_ms':min(times),'process_max_ms':max(times),'process_medians_ms':times,'median_allocated_bytes':statistics.median(allocations),'peak_working_set_bytes':max(r['peak_working_set_bytes'] for r in rows)}
        b['side_over_native_time']=b['summary']['side']['process_median_ms']/b['summary']['native']['process_median_ms']
        b['side_over_native_allocations']=b['summary']['side']['median_allocated_bytes']/b['summary']['native']['median_allocated_bytes']
    report['benchmarks'].append(b);print(('FAIL' if failed else 'BENCH')+': '+row['name'],flush=True);save()
report['summary']={'cases':len(cases),'passed':sum(r['passed'] for r in report['cases']),'failed':sum(not r['passed'] for r in report['cases']),'benchmark_workloads':len(report['benchmarks']),'failure_records':len(report['failures']),'full_nitra_equivalence_proven':False}
save();print(json.dumps(report['summary'],indent=2));print('Report:',a.output,flush=True)
sys.exit(1 if report['failures'] else 0)
