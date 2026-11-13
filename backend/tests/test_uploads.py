import os,sys,tempfile,json
from datetime import date
os.environ['JWT_SECRET']='test-secret'
_TMP=tempfile.mkdtemp(prefix='upload-test-')
os.environ['DATABASE_URL']='sqlite:///'+_TMP+'/test.db'
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..'))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from src.config.database import Base,engine,SessionLocal
from src.models import *
from src.routes import auth,surveys,transects,audit,uploads
from src.utils.security import hash_password,issue_token
from src.constants.species import SPECIES

app=FastAPI()
for r in (auth,surveys,transects,audit,uploads):app.include_router(r.router)
client=TestClient(app)

PASS=0;FAIL=0
def check(name,cond,detail=''):
 global PASS,FAIL
 if cond:PASS+=1;print(f'  PASS {name}')
 else:FAIL+=1;print(f'  FAIL {name} {detail}')

with SessionLocal() as db:
 Base.metadata.create_all(engine)
 admin=User(email='admin@songji.demo',name='顾芩',role='admin',password_hash=hash_password('pw'))
 viewer=User(email='viewer@songji.demo',name='季苔',role='viewer',password_hash=hash_password('pw'))
 db.add_all([admin,viewer]);db.commit()
 sv=Survey(name='秋季样线调查',survey_date=date(2026,10,14),filename='sj.csv',description='测试期')
 db.add(sv);db.commit();SURVEY=sv.id;ADMIN=admin.id;VIEWER=viewer.id
 admin_token=issue_token(admin);viewer_token=issue_token(viewer)

def auth(t):return {'Authorization':'Bearer '+t}
def counts(*pairs):return [{'species':s,'count':c} for s,c in pairs]
def item(ref,name='样线',habitat='阔叶林缘',*pairs):return {'reference':ref,'name':name,'habitat':habitat,'counts':counts(*pairs)}

print('== 1. 整批回传：新样线/冲突/坏行混合，保留可接收记录 ==')
payload={'batch_ref':'B-001','survey_id':SURVEY,'source':'field-tablet-A','items':[
 item('SJ-N1','新样线1','林缘',('S01',5),('S02',3)),
 item('SJ-N2','新样线2','溪边',('S03',0)),
 {'reference':'SJ-BAD','name':'坏行','habitat':'草地','counts':[{'species':'S99','count':2}]},
 {'reference':'SJ-BAD2','name':'坏行2','habitat':'草地','counts':[{'species':'S01','count':-4}]},
 'not-an-object',
 item('SJ-N1','批次内重复','林缘',('S01',9)),
]}
r=client.post('/uploads',json=payload,headers=auth(admin_token))
check('回传返回200',r.status_code==200,r.text)
b=r.json()
sm=b['summary']
check('总数6',sm['total']==6,str(sm))
check('接收2条新样线',sm['accepted']==2,str(sm))
check('拒收4条（3坏行+批内重复）',sm['rejected']==4,str(sm))
check('无冲突无重复',sm['conflict']==0 and sm['duplicate']==0,str(sm))
check('批次状态closed',b['status']=='closed',b['status'])
rejected=[i for i in b['items'] if i['status']=='rejected']
check('拒收逐项有原因',all(i['reason'] for i in rejected),json.dumps(rejected,ensure_ascii=False))
check('未知物种原因明确',any('未知物种' in i['reason'] for i in rejected))
check('负数原因明确',any('负' in i['reason'] for i in rejected))
check('批内重复原因明确',any('批次内' in i['reason'] for i in rejected))
r2=client.get(f"/transects?survey_id={SURVEY}" if False else '/transects',headers=auth(admin_token))
refs={t['reference'] for t in r2.json()}
check('坏行未建档、新样线已建档',refs=={'SJ-N1','SJ-N2'},str(refs))

print('== 2. 相同回传重发：不增计数、不增修订号、redeliveries+1 ==')
before=client.get('/transects',headers=auth(admin_token)).json()
n1_before=next(t for t in before if t['reference']=='SJ-N1')
r=client.post('/uploads',json=payload,headers=auth(admin_token))
check('重发返回200',r.status_code==200,r.text)
b2=r.json()
check('标记redelivered',b2.get('redelivered') is True)
check('重发次数=1',b2['redeliveries']==1,str(b2['redeliveries']))
check('明细未新增（仍6条）',len(b2['items'])==6)
after=client.get('/transects',headers=auth(admin_token)).json()
n1_after=next(t for t in after if t['reference']=='SJ-N1')
check('计数未变',n1_after['counts']==n1_before['counts'])
with SessionLocal() as db:
 t=db.scalar(select(Transect).where(Transect.reference=='SJ-N1'))
 check('修订号仍为1',t.revision==1,str(t.revision))
r=client.post('/uploads',json=payload,headers=auth(admin_token))
check('再次重发次数=2',r.json()['redeliveries']==2)
check('批次总数仍6、样线仍2',len(client.get('/transects',headers=auth(admin_token)).json())==2)

print('== 3. 同批次号不同内容：拒绝 ==')
tweak=json.loads(json.dumps(payload));tweak['items'][0]['counts'][0]['count']=99
r=client.post('/uploads',json=tweak,headers=auth(admin_token))
check('批次号复用冲突409',r.status_code==409,r.text)

print('== 4. 交错回传：两组对同一期同编号样线，旧副本不覆盖新计数 ==')
pA={'batch_ref':'B-A','survey_id':SURVEY,'source':'team-A','items':[item('SJ-X','甲组样线','林缘',('S01',10),('S02',20))]}
pB={'batch_ref':'B-B','survey_id':SURVEY,'source':'team-B','items':[item('SJ-X','乙组改名','溪边',('S01',30),('S03',7))]}
rA=client.post('/uploads',json=pA,headers=auth(admin_token));check('A组先到接收',rA.status_code==200 and rA.json()['summary']['accepted']==1,rA.text)
rB=client.post('/uploads',json=pB,headers=auth(admin_token));check('B组后到200不整批失败',rB.status_code==200,rB.text)
bB=rB.json();check('B组产生冲突而非覆盖',bB['summary']['conflict']==1,str(bB['summary']))
check('冲突批次open',bB['status']=='open')
conflict_item=next(i for i in bB['items'] if i['status']=='conflict')
check('保留旧快照',conflict_item['existing_snapshot']['counts'].get('S01')==10)
check('差异含计数变化',conflict_item['diff']['counts']['S01']=={'from':10,'to':30},json.dumps(conflict_item['diff'],ensure_ascii=False))
check('差异含元数据变化',conflict_item['diff']['meta']['name']=={'from':'甲组样线','to':'乙组改名'})
live=next(t for t in client.get('/transects',headers=auth(admin_token)).json() if t['reference']=='SJ-X')
check('现行计数仍是先到的A组（未被覆盖）',live['counts'].get('S01')==10 and live['name']=='甲组样线',json.dumps(live,ensure_ascii=False))
check('新冲突不误报漂移',conflict_item['drifted'] is False,str(conflict_item['drifted']))

print('== 5. 冲突处理：keep 与 overwrite ==')
iid=conflict_item['id']
r=client.post(f'/upload-items/{iid}/resolution',json={'decision':'keep','note':'田野复核以甲组为准'},headers=auth(admin_token))
check('keep返回200',r.status_code==200,r.text)
bb=r.json()
it=next(i for i in bb['items'] if i['id']==iid)
check('明细变为resolved',it['status']=='resolved' and it['resolution']=='keep')
check('批次关闭',bb['status']=='closed')
live=next(t for t in client.get('/transects',headers=auth(admin_token)).json() if t['reference']=='SJ-X')
check('keep后计数仍为A组',live['counts'].get('S01')==10)
r=client.post(f'/upload-items/{iid}/resolution',json={'decision':'overwrite'},headers=auth(admin_token))
check('已处理明细再操作409',r.status_code==409)

pC={'batch_ref':'B-C','survey_id':SURVEY,'source':'team-B','items':[item('SJ-X','乙组改名','溪边',('S01',30),('S03',7))]}
rC=client.post('/uploads',json=pC,headers=auth(admin_token));bC=rC.json()
cid=next(i['id'] for i in bC['items'] if i['status']=='conflict')
r=client.post(f'/upload-items/{cid}/resolution',json={'decision':'overwrite','note':'乙组补录经确认'},headers=auth(admin_token))
check('overwrite返回200',r.status_code==200,r.text)
it=next(i for i in r.json()['items'] if i['id']==cid)
check('overwrite已记录',it['resolution']=='overwrite' and '修订号升至2' in it['reason'],it.get('reason',''))
live=next(t for t in client.get('/transects',headers=auth(admin_token)).json() if t['reference']=='SJ-X')
check('计数已覆盖为乙组',live['counts'].get('S01')==30 and live['counts'].get('S03',0)==7 and live['name']=='乙组改名',json.dumps(live,ensure_ascii=False))
with SessionLocal() as db:
 t=db.scalar(select(Transect).where(Transect.reference=='SJ-X'))
 check('修订号升至2',t.revision==2,str(t.revision))
 check('内容指纹已更新',bool(t.content_hash))

print('== 6. 确认期间源数据又变化：必须重新核对 ==')
pD={'batch_ref':'B-D','survey_id':SURVEY,'source':'team-A','items':[item('SJ-X','丁组版本','草地',('S01',55))]}
bD=client.post('/uploads',json=pD,headers=auth(admin_token)).json()
did=next(i['id'] for i in bD['items'] if i['status']=='conflict')
with SessionLocal() as db:
 t=db.scalar(select(Transect).where(Transect.reference=='SJ-X'))
 t.name='田野现场又修订';t.revision+=1;t.content_hash='changed-'+str(t.revision);db.commit()
r=client.post(f'/upload-items/{did}/resolution',json={'decision':'overwrite'},headers=auth(admin_token))
check('源变后处理被拒409',r.status_code==409,r.text)
check('提示重新核对','重新核对' in r.json()['detail'])
with SessionLocal() as db:
 ui=db.get(UploadItem,did)
 check('recheck_required已标记',ui.recheck_required is True)
 t=db.scalar(select(Transect).where(Transect.reference=='SJ-X'))
 check('被拒后现行数据未被覆盖',t.name=='田野现场又修订')
r=client.post(f'/upload-items/{did}/resolution',json={'decision':'overwrite'},headers=auth(admin_token))
check('重新核对后可处理',r.status_code==200,r.text)
live=next(t for t in client.get('/transects',headers=auth(admin_token)).json() if t['reference']=='SJ-X')
check('覆盖后S01=55',live['counts'].get('S01')==55)

print('== 7. 重复回传与修订计数一致性（综合） ==')
pE={'batch_ref':'B-E','survey_id':SURVEY,'source':'team-A','items':[item('SJ-N1','新样线1','林缘',('S01',5),('S02',3))]}
bE=client.post('/uploads',json=pE,headers=auth(admin_token)).json()
check('与现行一致判duplicate',bE['summary']['duplicate']==1,str(bE['summary']))
client.post('/uploads',json=pE,headers=auth(admin_token))
bE2=client.post('/uploads',json=pE,headers=auth(admin_token)).json()
check('同一回传三发redeliveries=2',bE2['redeliveries']==2)
with SessionLocal() as db:
 t=db.scalar(select(Transect).where(Transect.reference=='SJ-N1'))
 check('SJ-N1修订号始终1',t.revision==1)
 n=len(db.scalars(select(SpeciesCount).where(SpeciesCount.transect_id==t.id)).all())
 check('SJ-N1计数行未膨胀',n==2,str(n))

print('== 8. 页面查询：批次列表、明细、漂移标记 ==')
r=client.get('/uploads',headers=auth(admin_token));check('批次列表200',r.status_code==200)
ids=[x['id'] for x in r.json()];check('列表含全部批次（B-001/B-A/B-B/B-C/B-D/B-E）',len(ids)==6,str(len(ids)))
pF={'batch_ref':'B-F','survey_id':SURVEY,'source':'team-A','items':[item('SJ-N2','再改N2','溪边',('S03',11))]}
bF=client.post('/uploads',json=pF,headers=auth(admin_token)).json()
fid=next(i['id'] for i in bF['items'] if i['status']=='conflict')
with SessionLocal() as db:
 t=db.scalar(select(Transect).where(Transect.reference=='SJ-N2'));t.content_hash='drifted-mark';db.commit()
detail=client.get(f"/uploads/{bF['id']}",headers=auth(admin_token)).json()
fi=next(i for i in detail['items'] if i['id']==fid)
check('明细带drifted=true',fi['drifted'] is True and fi['current_revision']==1,json.dumps(fi,ensure_ascii=False))

print('== 9. 权限：viewer不可回传与处理冲突，未登录401 ==')
r=client.post('/uploads',json=pA,headers=auth(viewer_token));check('viewer回传403',r.status_code==403)
r=client.post(f'/upload-items/{fid}/resolution',json={'decision':'keep'},headers=auth(viewer_token));check('viewer处理403',r.status_code==403)
r=client.get('/uploads');check('未登录401',r.status_code==401)
r=client.post('/uploads',json=pA);check('未登录写入401',r.status_code==401)

print('== 10. 审计留痕 ==')
logs=client.get('/audit',headers=auth(admin_token)).json()
actions={a['action'] for a in logs}
check('有批次回传留痕','upload.batch' in actions)
check('有重发留痕','upload.redelivery' in actions)
check('有冲突处理留痕','upload.conflict.resolved' in actions)
check('有重新核对留痕','upload.conflict.recheck' in actions)

print('== 11. 边界：坏行类型全覆盖 ==')
payload={'batch_ref':'B-G','survey_id':SURVEY,'items':[
 {'reference':'','name':'x','habitat':'y','counts':[{'species':'S01','count':1}]},
 {'reference':'OK-NAME','name':'x','habitat':'y','counts':[]},
 {'reference':'OK-FLOAT','name':'x','habitat':'y','counts':[{'species':'S01','count':1.5}]},
 {'reference':'OK-BOOL','name':'x','habitat':'y','counts':[{'species':'S01','count':True}]},
 {'reference':'OK-DUP','name':'x','habitat':'y','counts':[{'species':'S01','count':1},{'species':'S01','count':2}]},
]}
r=client.post('/uploads',json=payload,headers=auth(admin_token));check('混合坏行批次200',r.status_code==200,r.text)
rej=[i['reason'] for i in r.json()['items'] if i['status']=='rejected']
check('5条全拒收',len(rej)==5,str(rej))
check('空编号被识别',any('编号' in x for x in rej))
check('空计数被识别',any('计数须' in x for x in rej))
check('小数被识别',any('整数' in x for x in rej))
check('布尔被识别',any('整数' in x for x in rej))
check('物种重复被识别',any('不可重复' in x for x in rej))

print('== 12. 不存在调查期/批次 ==')
r=client.post('/uploads',json={'batch_ref':'B-X','survey_id':99999,'items':[item('Z')]},headers=auth(admin_token))
check('调查期不存在404',r.status_code==404)
r=client.get('/uploads/99999',headers=auth(admin_token));check('批次不存在404',r.status_code==404)

print(f'\n结果：{PASS} 通过 / {FAIL} 失败')
sys.exit(1 if FAIL else 0)
