import os,sys,tempfile
from datetime import date
_TMP=tempfile.mkdtemp(prefix='upload-e2e-')
os.environ.update(JWT_SECRET='e2e-secret',DATABASE_URL='sqlite:///'+_TMP+'/e2e.db',SEED_DEMO='false',REDIS_URL='redis://localhost:6399/0')
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..'))

from fastapi.testclient import TestClient
from sqlalchemy import select
from src.config.database import Base,engine,SessionLocal
from src.models import User,Survey,Transect,SpeciesCount,UploadBatch,UploadItem,AuditLog
from src.utils.security import hash_password

from src.main import app
PASS=0;FAIL=0
def check(n,c,d=''):
 global PASS,FAIL
 if c:PASS+=1;print('  PASS',n)
 else:FAIL+=1;print('  FAIL',n,d)

with TestClient(app) as client:
 with SessionLocal() as db:
  db.add_all([User(email='admin@songji.demo',name='顾芩',role='admin',password_hash=hash_password('Songji2026!')),
              User(email='viewer@songji.demo',name='季苔',role='viewer',password_hash=hash_password('Songji2026!'))])
  sv=Survey(name='秋季样线调查',survey_date=date(2026,10,14),filename='sj.csv',description='E2E期')
  db.add(sv);db.commit();SID=sv.id
 print('== E2E-1. 真实登录后整批回传 ==')
 r=client.post('/auth/login',json={'email':'admin@songji.demo','password':'Songji2026!'})
 check('登录200',r.status_code==200,r.text);token=r.json()['token'];H={'Authorization':'Bearer '+token}
 r=client.post('/auth/login',json={'email':'viewer@songji.demo','password':'Songji2026!'});vt=r.json()['token'];VH={'Authorization':'Bearer '+vt}

 def it(ref,*pairs,name=None,habitat='林缘'):return {'reference':ref,'name':name or ('样线-'+ref),'habitat':habitat,'counts':[{'species':s,'count':c} for s,c in pairs]}
 teamA={'batch_ref':'E2E-A','survey_id':SID,'source':'甲组平板','items':[it('SJ-01',('S01',10),('S02',20),name='甲版01'),it('SJ-02',('S03',5),name='甲版02')]}
 teamB={'batch_ref':'E2E-B','survey_id':SID,'source':'乙组平板','items':[
  it('SJ-01',('S01',18),('S02',20),name='乙版01'),
  it('SJ-03',('S04',7),name='乙版03'),
  {'reference':'SJ-BAD','name':'坏','habitat':'x','counts':[{'species':'SXX','count':1}]},
  {'reference':'SJ-02','name':'甲版02','habitat':'林缘','counts':[{'species':'S03','count':5}]}]}

 print('== E2E-2. 交错回传：甲先乙后，同编号不覆盖、坏行不拖垮整批 ==')
 a=client.post('/uploads',json=teamA,headers=H).json()
 check('甲组2条全接收',a['summary']['accepted']==2,str(a['summary']))
 b=client.post('/uploads',json=teamB,headers=H).json()
 check('乙组批次200未整体失败',b is not None)
 check('乙组1接收（SJ-03新线）',b['summary']['accepted']==1,str(b['summary']))
 check('乙组1冲突（SJ-01）',b['summary']['conflict']==1,str(b['summary']))
 check('乙组1重复（SJ-02同内容）',b['summary']['duplicate']==1,str(b['summary']))
 check('乙组1坏行拒收',b['summary']['rejected']==1,str(b['summary']))
 check('乙组批次待处理',b['status']=='open')
 live=next(t for t in client.get('/transects',headers=H).json() if t['reference']=='SJ-01')
 check('SJ-01保留甲组计数未被乙组覆盖',live['counts']['S01']==10 and live['name']=='甲版01',str(live))

 print('== E2E-3. 相同回传重发：计数与处理记录一致 ==')
 b2=client.post('/uploads',json=teamB,headers=H).json()
 check('重发标记redelivered',b2.get('redelivered') is True)
 check('重发不新增明细行',len(b2['items'])==4)
 b3=client.post('/uploads',json=teamB,headers=H).json()
 check('第三次回传redeliveries=2',b3['redeliveries']==2)
 with SessionLocal() as db:
  n_tr=db.query(Transect).count();n_sc=db.query(SpeciesCount).count();n_b=db.query(UploadBatch).count();n_i=db.query(UploadItem).count()
 check('样线仍3条',n_tr==3,str(n_tr));check('计数行未膨胀',n_sc==4,str(n_sc))
 check('批次仍2个',n_b==2,str(n_b));check('明细仍6条',n_i==6,str(n_i))

 print('== E2E-4. 页面查回传明细并处理冲突 ==')
 lst=client.get('/uploads',headers=H).json();check('批次列表可查',len(lst)==2)
 detail=client.get(f"/uploads/{b['id']}",headers=H).json()
 conf=next(i for i in detail['items'] if i['status']=='conflict')
 check('明细含差异与快照',conf['diff']['counts']['S01']=={'from':10,'to':18} and conf['existing_snapshot']['revision']==1)
 check('viewer不能处理',client.post(f"/upload-items/{conf['id']}/resolution",json={'decision':'overwrite'},headers=VH).status_code==403)
 res=client.post(f"/upload-items/{conf['id']}/resolution",json={'decision':'overwrite','note':'田野电话复核乙组为准'},headers=H)
 check('admin确认覆盖200',res.status_code==200,res.text)
 done=next(i for i in res.json()['items'] if i['id']==conf['id'])
 check('处理记录含处理人与说明',done['resolved_by']=='admin@songji.demo' and '乙组为准' in done['reason'])
 check('批次结清',res.json()['status']=='closed')
 live=next(t for t in client.get('/transects',headers=H).json() if t['reference']=='SJ-01')
 check('覆盖生效且修订号=2',live['counts']['S01']==18 and live['name']=='乙版01' and live['revision']==2,str(live))

 print('== E2E-5. 确认期间源数据再变：重新核对路径 ==')
 c=client.post('/uploads',json={'batch_ref':'E2E-C','survey_id':SID,'items':[it('SJ-01',('S01',99),name='丙版01')]},headers=H).json()
 cid=next(i['id'] for i in c['items'] if i['status']=='conflict')
 with SessionLocal() as db:
  t=db.scalar(select(Transect).where(Transect.reference=='SJ-01'));t.revision=3;t.content_hash='drift';db.commit()
 r=client.post(f'/upload-items/{cid}/resolution',json={'decision':'overwrite'},headers=H)
 check('漂移时处理被拒',r.status_code==409 and '重新核对' in r.json()['detail'])
 d=client.get(f"/uploads/{c['id']}",headers=H).json()
 ci=next(i for i in d['items'] if i['id']==cid)
 check('明细显示源数据已漂移且需核对',ci['drifted'] is True and ci['recheck_required'] is True)
 r2=client.post(f'/upload-items/{cid}/resolution',json={'decision':'overwrite'},headers=H)
 check('重新核对后处理成功',r2.status_code==200,r2.text)

 print('== E2E-6. 审计留痕完整 ==')
 logs=client.get('/audit',headers=H).json()
 acts=[a['action'] for a in logs]
 for expect in ('auth.login','upload.batch','upload.redelivery','upload.conflict.resolved','upload.conflict.recheck'):
  check(f'留痕含 {expect}',expect in acts,str(sorted(set(acts))))

print(f'\nE2E结果：{PASS} 通过 / {FAIL} 失败')
sys.exit(1 if FAIL else 0)
